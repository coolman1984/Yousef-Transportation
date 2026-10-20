"""Unit tests: crypto, journal rules (chain, forks, duplicates, gaps, authority), fold rules, node identity safety."""
import json
import os
import shutil
import sqlite3
import tempfile
import unittest

import engine_domain
from cluster import Cluster, Peer, enroll_op  # noqa: F401 (sets sys.path, registers the engine test entities)
import ed25519  # noqa: E402
import tlscert  # noqa: E402
from journal import canonical, chash  # noqa: E402
from node import Node  # noqa: E402
from store import BadRequest, Conflict  # noqa: E402

RFC8032 = [
    ('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60', 'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
     'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
    ('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb', '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
     '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'),
    ('c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7', 'fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025', 'af82',
     '6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a'),
]


class CryptoTest(unittest.TestCase):
    def test_rfc8032_vectors(self):
        for sk, pk, msg, sig in RFC8032:
            sk, pk, msg, sig = map(bytes.fromhex, (sk, pk, msg, sig))
            self.assertEqual(ed25519.public_key(sk), pk)
            self.assertEqual(ed25519.sign(sk, msg), sig)
            self.assertTrue(ed25519.verify(pk, msg, sig))

    def test_rejects_tampering(self):
        sk = ed25519.generate()
        pk = ed25519.public_key(sk)
        sig = ed25519.sign(sk, b'hello')
        self.assertFalse(ed25519.verify(pk, b'hellO', sig))
        for i in (0, 31, 32, 63):
            bad = bytearray(sig)
            bad[i] ^= 1
            self.assertFalse(ed25519.verify(pk, b'hello', bytes(bad)))
        self.assertFalse(ed25519.verify(pk, b'hello', b'\x00' * 64))
        self.assertFalse(ed25519.verify(b'\x01' * 32, b'hello', sig))

    def test_certificate_handshake(self):
        import socket
        import ssl
        import threading
        seed = ed25519.generate()
        cert, key, fp = tlscert.make_cert(seed, 'x', 7)
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, 'c'), 'w').write(cert)
            open(os.path.join(d, 'k'), 'w').write(key)
            sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            sctx.load_cert_chain(os.path.join(d, 'c'), os.path.join(d, 'k'))
            srv = socket.socket()
            srv.bind(('127.0.0.1', 0))
            srv.listen(1)

            def serve():
                s, _ = srv.accept()
                t = sctx.wrap_socket(s, server_side=True)
                t.sendall(b'ok')
                t.close()
            threading.Thread(target=serve, daemon=True).start()
            cctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            cctx.check_hostname = False
            cctx.verify_mode = ssl.CERT_NONE
            t = cctx.wrap_socket(socket.create_connection(srv.getsockname()))
            self.assertEqual(tlscert.fingerprint_der(t.getpeercert(True)), fp)
            self.assertEqual(t.recv(2), b'ok')
            self.assertIn(t.version(), ('TLSv1.3', 'TLSv1.2'))
            t.close()
        finally:
            shutil.rmtree(d)


class JournalRulesTest(unittest.TestCase):
    def setUp(self):
        self.c = Cluster(3)
        self.a, self.b, self.x = self.c.peers

    def tearDown(self):
        self.c.close()

    def area(self, peer, aid, **kw):
        return peer.commit('t', [{'e': 'areas', 'id': aid, 'op': 'put', 'row': {'name': aid, **kw}}])

    def test_duplicates_and_out_of_order(self):
        for i in range(5):
            self.area(self.a, f'a{i}')
        recs, _ = self.a.journal.changes_since(self.b.journal.vv())
        fp_before = self.b.store.fingerprint()
        acc, deferred, _ = self.b.receive(recs[2:])  # the first ones are missing: everything waits
        self.assertEqual((len(acc), deferred), (0, len(recs) - 2))
        acc, deferred, _ = self.b.receive(list(reversed(recs)))  # complete but newest first: put in order and taken
        self.assertEqual((len(acc), deferred), (len(recs), 0))
        for _ in range(6):
            self.b.receive(list(reversed(recs)) + recs)  # duplicates in every delivery
        self.assertEqual(self.b.store.fingerprint(), self.a.store.fingerprint())
        self.assertNotEqual(fp_before, self.b.store.fingerprint())
        n = self.b.journal.stats()['changes']
        self.b.receive(recs * 10)
        self.assertEqual(self.b.journal.stats()['changes'], n, 'receiving again changes nothing')

    def test_forged_admin_change_rejected_everywhere(self):
        # pc1 (not the administrator PC) makes itself an administrator with its own key
        evil = self.b.journal.build('data', [], actor='x')  # noqa: F841 - only to reserve nothing
        env_ops = [{'e': 'users', 'id': 'u-evil', 'op': 'insert',
                    's': {'username': 'evil', 'full_name': 'Evil', 'pw_hash': 'x', 'perms': ['users.manage'], 'active': True}}]
        with self.b.journal.lock:
            rec = self.b.journal.build('admin', env_ops, actor='evil')  # no authority key: signed only by pc1
            rec['asig'] = rec['sig']  # pretend
            self.b.journal.append_local(rec)
        acc, _, _ = self.c.deliver(self.b, self.a)
        self.assertEqual([r['status'] for r in acc], ['rejected'])
        self.assertTrue(any(al['kind'] == 'rejected' for al in self.a.journal.alerts()))
        # the chain continues: later honest changes from pc1 still arrive
        self.area(self.b, 'after')
        self.c.converge()
        self.assertIn('after', {x['id'] for x in self.a.state()['areas']})

    def test_account_change_only_own_password(self):
        with self.b.journal.lock:
            rec = self.b.journal.build('account', [{'e': 'users', 'id': 'someone-else', 'op': 'update', 's': {'pw_hash': 'x'}}], actor_id='me')
            self.b.journal.append_local(rec)
            ok = self.b.journal.build('account', [{'e': 'users', 'id': 'me', 'op': 'update', 's': {'pw_hash': 'y', 'must_change': False}}], actor_id='me')
            self.b.journal.append_local(ok)
            perms = self.b.journal.build('account', [{'e': 'users', 'id': 'me', 'op': 'update', 's': {'perms': ['users.manage']}}], actor_id='me')
            self.b.journal.append_local(perms)
        acc, _, _ = self.c.deliver(self.b, self.a)
        # without a proof signed with the old password's key nothing is accepted - not even for one's own account
        self.assertEqual([r['status'] for r in acc], ['rejected', 'rejected', 'rejected'])
        self.assertIn('proof', acc[1]['note'])

    def test_data_change_cannot_touch_accounts(self):
        with self.b.journal.lock:
            rec = self.b.journal.build('data', [{'e': 'nodes', 'id': 'n', 'op': 'insert', 's': {'pub': 'aa'}}])
            self.b.journal.append_local(rec)
        acc, _, _ = self.c.deliver(self.b, self.a)
        self.assertEqual(acc[0]['status'], 'rejected')

    def test_bad_signature_refused(self):
        self.area(self.b, 'sig')
        recs, _ = self.b.journal.changes_since(self.a.journal.vv())
        forged = [dict(r) for r in recs]
        env = json.loads(forged[-1]['b'])
        env['label'] = 'changed by a relay'
        forged[-1]['b'] = canonical(env)
        acc, _, problems = self.a.receive(forged)
        self.assertEqual(len(acc), len(recs) - 1)
        self.assertTrue(problems)
        self.assertTrue(any(al['kind'] == 'signature' for al in self.a.journal.alerts()))

    def test_fork_detected(self):
        self.area(self.b, 'f1')
        self.c.converge()
        # simulate a copied data folder: same identity writes a different change with the same number
        with self.b.journal.lock:
            cseq, h, node = self.b.journal.heads[self.b.node.replica]
            rec = self.b.journal.build('data', [{'e': 'areas', 'id': 'x', 'op': 'insert', 's': {'name': 'x'}}])
        env = dict(rec['env'])
        env['cseq'] = cseq
        env['prev'] = self.b.journal.hash_at(self.b.node.replica, cseq - 1) if cseq > 1 else '0' * 64
        body = canonical(env)
        h2 = chash(body)
        forged = {'b': body, 's': self.b.node.sign(bytes.fromhex(h2)).hex()}
        self.a.receive([forged])
        self.assertTrue(any(al['kind'] == 'fork' for al in self.a.journal.alerts()))

    def test_gap_waits_and_causal_order(self):
        self.area(self.a, 'g1')
        self.c.deliver(self.a, self.b)
        a1 = next(x for x in self.b.state()['areas'] if x['id'] == 'g1')
        self.b.commit('edit', [{'e': 'areas', 'id': 'g1', 'op': 'put', 'ver': a1['ver'], 'row': {'name': 'g1', 'description': 'by b'}}])
        # x receives b's edit before a's insert: it must wait (deps), then apply both
        recs_b, _ = self.b.journal.changes_since(self.x.journal.vv())
        only_b = [r for r in recs_b if json.loads(r['b'])['origin'] == self.b.node.replica]
        acc, deferred, _ = self.x.receive(only_b)
        self.assertEqual(len(acc), 0)
        self.assertEqual(deferred, 1)
        self.c.converge()
        self.assertEqual(next(x for x in self.x.state()['areas'] if x['id'] == 'g1')['description'], 'by b')


class FoldRulesTest(unittest.TestCase):
    def setUp(self):
        self.c = Cluster(2)
        self.a, self.b = self.c.peers

    def tearDown(self):
        self.c.close()

    def get(self, peer, entity, rid):
        st = peer.state()
        if entity == 'areas':
            return next((x for x in st['areas'] if x['id'] == rid), None)
        return next((x for a in st['areas'] for x in a[entity] if x['id'] == rid), None)

    def put(self, peer, entity, rid, ver=None, **row):
        return peer.commit('t', [{'e': entity, 'id': rid, 'op': 'put', 'ver': ver, 'row': row}])

    def test_inspection_dates_latest_wins(self):
        self.put(self.a, 'areas', 'i', name='i')
        self.c.converge()
        a0, b0 = self.get(self.a, 'areas', 'i'), self.get(self.b, 'areas', 'i')
        self.put(self.a, 'areas', 'i', a0['ver'], name='i', lastInspection='2026-09-20', nextInspection='2026-10-20', inspectedBy='A')
        self.put(self.b, 'areas', 'i', b0['ver'], name='i', lastInspection='2026-09-10', nextInspection='2026-10-10', inspectedBy='B')
        self.c.converge()
        for p in self.c.peers:
            x = self.get(p, 'areas', 'i')
            self.assertEqual((x['lastInspection'], x['nextInspection'], x['inspectedBy']), ('2026-09-20', '2026-10-20', 'A'))

    def test_maintenance_done_wins(self):
        self.put(self.a, 'areas', 'm', name='m')
        self.put(self.a, 'maintenance', 'm1', areaId='m', status='Scheduled', details='x')
        self.c.converge()
        ma, mb = self.get(self.a, 'maintenance', 'm1'), self.get(self.b, 'maintenance', 'm1')
        self.put(self.b, 'maintenance', 'm1', mb['ver'], areaId='m', status='Done', details='x', notes='fixed', doneDate='2026-09-26')
        self.put(self.a, 'maintenance', 'm1', ma['ver'], areaId='m', status='In Progress', details='x', notes='started')
        self.c.converge()
        for p in self.c.peers:
            x = self.get(p, 'maintenance', 'm1')
            self.assertEqual((x['status'], x.get('notes'), x.get('doneDate')), ('Done', 'fixed', '2026-09-26'))

    def test_negative_stock_flagged(self):
        self.put(self.a, 'areas', 'n', name='n')
        self.put(self.a, 'inventory', 'n:tv', areaId='n', item='tv', qty=2)
        self.c.converge()
        ia, ib = self.get(self.a, 'inventory', 'n:tv'), self.get(self.b, 'inventory', 'n:tv')
        self.put(self.a, 'inventory', 'n:tv', ia['ver'], areaId='n', item='tv', qty=0)
        self.put(self.b, 'inventory', 'n:tv', ib['ver'], areaId='n', item='tv', qty=0)
        self.c.converge()
        self.assertEqual(self.get(self.a, 'inventory', 'n:tv')['qty'], -2)
        self.assertIn('negative', {x['kind'] for x in self.a.store.conflicts()})

    def test_no_resurrection_by_old_edit(self):
        self.put(self.a, 'areas', 'z', name='z')
        self.c.converge()
        za, zb = self.get(self.a, 'areas', 'z'), self.get(self.b, 'areas', 'z')
        self.a.commit('del', [{'e': 'areas', 'id': 'z', 'op': 'del', 'ver': za['ver']}])
        self.put(self.b, 'areas', 'z', zb['ver'], name='z', description='offline edit')
        self.c.converge()
        for p in self.c.peers:
            self.assertIsNone(self.get(p, 'areas', 'z'))
        # recycle bin restore brings it back including the offline edit
        txn = self.a.store.trash()[0]['txn']
        self.a.store.restore_txn('u', 'ip', txn)
        self.c.converge()
        self.assertEqual(self.get(self.b, 'areas', 'z')['description'], 'offline edit')

    def test_optimistic_version_still_protects_local_edits(self):
        self.put(self.a, 'areas', 'v', name='v')
        v = self.get(self.a, 'areas', 'v')
        self.put(self.a, 'areas', 'v', v['ver'], name='v2')
        with self.assertRaises(Conflict):
            self.put(self.a, 'areas', 'v', v['ver'], name='v3')


class ReviewFindingsTest(unittest.TestCase):
    """Regression tests for the independent review findings."""

    def setUp(self):
        self.c = Cluster(3)
        self.a, self.b, self.x = self.c.peers

    def tearDown(self):
        self.c.close()

    def area(self, peer, aid):
        return next((x for x in peer.state()['areas'] if x['id'] == aid), None)

    def put(self, peer, aid, ver=None, **row):
        return peer.commit('t', [{'e': 'areas', 'id': aid, 'op': 'put', 'ver': ver, 'row': {'name': aid, **row}}])

    def test_local_save_between_receive_and_fold(self):
        """A change received (journal) but not yet folded must not count as 'seen' by a local save."""
        self.put(self.a, 'r')
        self.c.converge()
        ra, rb = self.area(self.a, 'r'), self.area(self.b, 'r')
        self.put(self.a, 'r', ra['ver'], lastInspection='2026-02-01', nextInspection='2026-03-01')
        recs, _ = self.a.journal.changes_since(self.b.journal.vv())
        self.b.journal.receive(recs, 'a')              # arrives, not folded yet
        self.put(self.b, 'r', rb['ver'], lastInspection='2026-09-01', nextInspection='2026-10-01')
        self.b.store.fold_pending()
        self.c.converge()
        fps = self.c.fingerprints()
        self.assertEqual(len(set(fps)), 1)
        for p in self.c.peers:
            self.assertEqual(self.area(p, 'r')['lastInspection'], '2026-09-01')
            self.assertIn(('r', 'conflict'), {(k['id'], k['kind']) for k in p.store.conflicts()})

    def test_impossible_change_is_refused_everywhere_and_sync_continues(self):
        with self.b.journal.lock:
            rec = self.b.journal.build('data', [{'e': 'inventory', 'id': 'q', 'op': 'insert', 's': {'item': 'x'}, 'n': {'qty': 10 ** 30}}])
            self.b.journal.append_local(rec)
        self.put(self.b, 'after-bad')
        self.c.converge()
        for p in self.c.peers:
            self.assertIsNotNone(self.area(p, 'after-bad'))
        self.assertEqual(self.a.journal.conn.execute("SELECT status FROM changes WHERE id=?", (rec['env']['id'],)).fetchone()[0], 'rejected')

    def test_follower_fields_travel_with_leader(self):
        self.put(self.a, 'f', inspectedBy='Ann', lastInspection='2026-01-01')
        self.c.converge()
        fa, fb = self.area(self.a, 'f'), self.area(self.b, 'f')
        self.put(self.a, 'f', fa['ver'], inspectedBy='Ann', lastInspection='2026-09-20')   # inspectedBy unchanged
        self.put(self.b, 'f', fb['ver'], inspectedBy='Bob', lastInspection='2026-09-10')
        self.c.converge()
        for p in self.c.peers:
            x = self.area(p, 'f')
            self.assertEqual((x['lastInspection'], x['inspectedBy']), ('2026-09-20', 'Ann'))

    def test_row_kept_after_weak_restore_delete_does_not_vanish_on_edit(self):
        import sqlite3 as sq
        self.put(self.a, 'w')
        self.c.converge()
        # a backup without 'w' is restored on A while B edits 'w'
        bk = os.path.join(self.c.root, 'bk.db')
        sq.connect(bk).execute('CREATE TABLE areas (id TEXT, deleted INTEGER, name TEXT)').connection.commit()
        wb = self.area(self.b, 'w')
        self.a.store.restore_from(bk, 'u', 'ip', 'restore')
        self.put(self.b, 'w', wb['ver'], description='edited on B')
        self.c.converge()
        self.assertIsNotNone(self.area(self.a, 'w'))
        w = self.area(self.x, 'w')
        self.put(self.x, 'w', w['ver'], description='edited later on X')
        self.c.converge()
        for p in self.c.peers:
            self.assertEqual(self.area(p, 'w')['description'], 'edited later on X')

    def test_fingerprint_cache_follows_flag_changes(self):
        self.put(self.a, 'g')
        self.c.converge()
        ga, gb = self.area(self.a, 'g'), self.area(self.b, 'g')
        self.put(self.a, 'g', ga['ver'], description='A')
        self.put(self.b, 'g', gb['ver'], description='B')
        self.c.converge()
        for p in self.c.peers:
            cached = p.store.fingerprint()
            p.store._fp = (None, None)
            self.assertEqual(cached, p.store.fingerprint())


class NodeSafetyTest(unittest.TestCase):
    def test_copied_folder_detected(self):
        d = tempfile.mkdtemp()
        try:
            os.environ['TO_MACHINE_ID'] = 'pc-one'
            Node(d).create('one')
            self.assertFalse(Node(d).moved)
            os.environ['TO_MACHINE_ID'] = 'pc-two'
            self.assertTrue(Node(d).moved)
        finally:
            os.environ.pop('TO_MACHINE_ID', None)
            shutil.rmtree(d)

    def test_rolled_back_journal_gets_new_epoch(self):
        self._assert_rolled_back_journal_gets_new_epoch()

    def test_rolled_back_journal_gets_new_epoch_without_written_note(self):
        from unittest.mock import patch
        with patch.object(Node, 'record_written', side_effect=OSError('note unavailable')):
            self._assert_rolled_back_journal_gets_new_epoch()

    def _assert_rolled_back_journal_gets_new_epoch(self):
        from system import System
        d = tempfile.mkdtemp()
        try:
            s = System(d, {}, os.path.join(d, 'uploads'), os.path.join(d, 'bk'), log=lambda m: None)
            s.auth.setup('boss', 'The Boss', 'Strong-pass1', '127.0.0.1')
            s.store.commit('u', 'ip', 'a', [{'e': 'areas', 'id': 'a', 'op': 'put', 'row': {'name': 'a'}}])
            name = s.backups.create('manual')
            replica = s.node.replica
            s.store.commit('u', 'ip', 'b', [{'e': 'areas', 'id': 'b', 'op': 'put', 'row': {'name': 'b'}}])
            lost_head = s.journal.vv()[replica]
            lost_records, _ = s.journal.changes_since({replica: lost_head - 1})
            s.close()
            shutil.copy(os.path.join(d, 'bk', 'db', 'journal' + name[2:]), os.path.join(d, 'journal.db'))
            for suffix in ('-wal', '-shm'):
                if os.path.exists(os.path.join(d, 'journal.db' + suffix)):
                    os.remove(os.path.join(d, 'journal.db' + suffix))
            s = System(d, {}, os.path.join(d, 'uploads'), os.path.join(d, 'bk'), log=lambda m: None)
            self.assertNotEqual(s.node.replica, replica)
            self.assertLess(s.journal.vv().get(replica, 0), lost_head, 'recovery must not reuse the lost sequence')
            accepted, deferred, problems = s.journal.receive(lost_records, 'old-peer')
            self.assertEqual(problems, [])
            self.assertTrue(accepted)
            s.store.fold_pending()
            self.assertTrue(any(a['kind'] == 'rollback' for a in s.journal.alerts()))
            # 'b' was only in the tables, not in the restored journal: it is kept and saved again as a new change
            self.assertIn('b', {a['id'] for a in engine_domain.nested_state(s.store)['areas']})
            self.assertTrue(any('"b"' in r[0] for r in s.journal.conn.execute("SELECT body FROM changes WHERE kind='data'")))
            s.store.commit('u', 'ip', 'c', [{'e': 'areas', 'id': 'c', 'op': 'put', 'row': {'name': 'c'}}])
            self.assertTrue(s.journal.verify(True)['ok'])
            s.close()
        finally:
            shutil.rmtree(d)


class ToolsTest(unittest.TestCase):
    def test_rebuild_gives_identical_data(self):
        """Disaster recovery: trips.db re-created from the history is exactly the same data."""
        import subprocess
        import sys
        from system import System
        d = tempfile.mkdtemp()
        try:
            data = os.path.join(d, 'data')
            sy = System(data, {}, os.path.join(d, 'uploads'), os.path.join(d, 'bk'), log=lambda m: None)
            sy.auth.setup('boss', 'The Boss', 'Strong-pass1', '127.0.0.1')
            for i in range(5):
                sy.store.commit('u', 'ip', f'a{i}', [{'e': 'areas', 'id': f'a{i}', 'op': 'put', 'row': {'name': f'a{i}'}},
                                                     {'e': 'inventory', 'id': f'a{i}:tv', 'op': 'put', 'row': {'areaId': f'a{i}', 'item': 'tv', 'qty': i}}])
            sy.close()
            cfg = os.path.join(d, 'config.json')
            json.dump({'data_dir': data, 'backup_dir': os.path.join(d, 'bk')}, open(cfg, 'w'))
            env = dict(os.environ, TO_CONFIG=cfg)
            tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server', 'nodectl.py')
            fp1 = subprocess.run([sys.executable, tool, 'status'], env=env, capture_output=True, text=True).stdout.split('fingerprint:')[1].strip()
            out = subprocess.run([sys.executable, tool, 'rebuild'], env=env, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            fp2 = subprocess.run([sys.executable, tool, 'status'], env=env, capture_output=True, text=True).stdout.split('fingerprint:')[1].strip()
            self.assertEqual(fp1, fp2)
            self.assertEqual(subprocess.run([sys.executable, tool, 'verify'], env=env, capture_output=True).returncode, 0)
        finally:
            shutil.rmtree(d)

    @unittest.skipUnless(os.name == 'nt', 'an open SQLite file can only block a rename on Windows')
    def test_rebuild_refuses_while_database_is_open(self):
        """F06: rebuild must not half-move files when the running app still holds trips.db."""
        import sqlite3
        import subprocess
        import sys
        from system import System
        d = tempfile.mkdtemp()
        try:
            data = os.path.join(d, 'data')
            sy = System(data, {}, os.path.join(d, 'uploads'), os.path.join(d, 'bk'), log=lambda m: None)
            sy.auth.setup('boss', 'The Boss', 'Strong-pass1', '127.0.0.1')
            sy.close()
            cfg = os.path.join(d, 'config.json')
            with open(cfg, 'w') as f:
                json.dump({'data_dir': data, 'backup_dir': os.path.join(d, 'bk')}, f)
            tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server', 'nodectl.py')
            dbs = lambda: sorted(n for n in os.listdir(data) if n.endswith('.db') or '.broken-' in n)  # program.lock is created by the tool itself
            before = dbs()
            holder = sqlite3.connect(os.path.join(data, 'trips.db'))  # stands in for the running app
            try:
                out = subprocess.run([sys.executable, tool, 'rebuild'], env=dict(os.environ, TO_CONFIG=cfg), capture_output=True, text=True)
            finally:
                holder.close()
            self.assertEqual(out.returncode, 1, out.stderr)
            self.assertIn('Nothing was changed', out.stdout)
            self.assertEqual(dbs(), before)
        finally:
            shutil.rmtree(d)

    def test_key_export_protection(self):
        import nodectl
        secret = os.urandom(32)
        box = nodectl.seal(secret, 'a long passphrase 1', {'cluster': 'c'})
        self.assertEqual(nodectl.unseal(box, 'a long passphrase 1'), secret)
        with self.assertRaises(ValueError):
            nodectl.unseal(box, 'a long passphrase 2')
        box['ct'] = ('00' if box['ct'][:2] != '00' else '11') + box['ct'][2:]
        with self.assertRaises(ValueError):
            nodectl.unseal(box, 'a long passphrase 1')




class Review231Test(unittest.TestCase):
    """Automatic review after 2.3.0: PC changes signed on two PCs (administrator + backup) end the same everywhere,
    and network drives are refused for the second backup folder."""

    def roster_after(self, envs):
        from journal import Journal
        c = sqlite3.connect(':memory:')
        c.row_factory = sqlite3.Row
        c.execute('CREATE TABLE nodes (id TEXT PRIMARY KEY, name TEXT, pub TEXT, cert_fp TEXT, address TEXT, status TEXT, role TEXT, '
                  'enrolled_at TEXT, enrolled_by TEXT, revoked_at TEXT, revoked_by TEXT, updated_at TEXT, updated_by TEXT, '
                  'revoked_change TEXT, vers TEXT)')
        for env in envs:
            Journal._fold_roster(c, env)
        return {k: v for k, v in dict(c.execute('SELECT * FROM nodes WHERE id=?', ('pc3',)).fetchone()).items()
                if k not in ('vers', 'updated_at', 'updated_by')}

    def test_roster_same_in_any_order(self):
        def env(origin, cseq, hlc, s):
            return {'origin': origin, 'cseq': cseq, 'hlc': hlc, 'ts': '2026-09-27T10:00:00', 'actor': 'Admin',
                    'ops': [{'e': 'nodes', 'id': 'pc3', 'op': 'update', 's': s}]}
        base = env('admin', 1, 100, {'name': 'Store', 'address': '10.0.0.3:8443', 'status': 'active', 'role': 'member'})
        a = env('admin', 2, 205, {'name': 'Store room', 'address': '10.0.0.30:8443'})
        b = env('backup', 7, 210, {'name': 'Stock PC', 'role': 'backup'})
        r = env('backup', 8, 150, {'status': 'revoked', 'revoked_at': 'x', 'revoked_by': 'Deputy'})
        one = self.roster_after([base, a, b, r])
        self.assertEqual(one, self.roster_after([base, r, b, a]))
        self.assertEqual(one, self.roster_after([b, r, a, base]))
        self.assertEqual((one['name'], one['address'], one['role'], one['status']), ('Stock PC', '10.0.0.30:8443', 'backup', 'revoked'))
        late = env('admin', 3, 999, {'status': 'active'})  # a removal is final
        self.assertEqual(self.roster_after([base, r, late])['status'], 'revoked')
        # the same PC removed on two PCs at the same time: same result in both orders, both removals remembered
        r2 = env('admin', 4, 140, {'status': 'revoked', 'revoked_at': 'y', 'revoked_by': 'Admin'})
        x, y = self.roster_after([base, r, r2]), self.roster_after([base, r2, r])
        self.assertEqual(x, y)
        self.assertEqual((x['revoked_by'], x['revoked_change']), ('Admin', 'admin#4 backup#8'))

    def test_upgrade_rebuilds_the_pc_list(self):
        """A 2.3.0 database has no field versions: the PC list is folded again from the history once."""
        from journal import Journal
        from store import ENTITIES
        cl = Cluster(2)
        try:
            a = cl.peers[0]
            pc1 = cl.peers[1].node.id
            a.journal.write('admin', [{'e': 'nodes', 'id': pc1, 'op': 'update', 'noaudit': True, 's': {'name': 'Store room'}}],
                            actor='admin', label='rename', authority=True)
            a.journal.conn.execute("UPDATE nodes SET name='wrong', vers=NULL")
            a.journal.conn.execute('ALTER TABLE nodes DROP COLUMN vers')
            a.journal.conn.close()
            j = Journal(a.dir, a.node, ENTITIES.keys())
            self.assertEqual(j.roster()[pc1]['name'], 'Store room')
            self.assertTrue(j.roster()[pc1]['vers'])
            j.conn.close()
        finally:
            shutil.rmtree(cl.root, ignore_errors=True)

    def test_network_folders_refused(self):
        import backup
        self.assertTrue(backup.network_folder('\\\\fileserver\\share'))
        self.assertTrue(backup.network_folder('//fileserver/share'))
        self.assertTrue(backup.network_folder('Z:\\TripOrders', drive_type=lambda root: backup.DRIVE_REMOTE))
        self.assertFalse(backup.network_folder('E:\\TripOrders', drive_type=lambda root: 2))  # USB drive
        self.assertFalse(backup.network_folder('/media/usb/TripOrders'))


class QuietPcTest(unittest.TestCase):
    """The administrator PC warns about a PC that has not shared its data for several days (once a day), not about others."""

    def test_quiet_pc_warning(self):
        import types
        from datetime import datetime, timedelta
        import sync
        old = (datetime.now() - timedelta(days=5)).isoformat(timespec='seconds')
        new = datetime.now().isoformat(timespec='seconds')
        alerts = []
        status = {'b': {'last_seen': old}, 'c': {'last_seen': new}, 'd': {'last_seen': old}}
        meta = {}
        fake = types.SimpleNamespace(
            QUIET_DAYS=3, node=types.SimpleNamespace(id='a'), peer_status=lambda pid: status.get(pid, {}),
            journal=types.SimpleNamespace(alert=lambda *a, **k: alerts.append((a, k)), meta=lambda k, d=None: meta.get(k, d),
                                          set_meta=lambda k, v: meta.__setitem__(k, v), roster=lambda: {
                'a': {'status': 'active', 'name': 'Admin'}, 'b': {'status': 'active', 'name': 'Store PC'},
                'c': {'status': 'active', 'name': 'HR PC'}, 'd': {'status': 'revoked', 'name': 'Old PC'}}))
        sync.SyncService._quiet_pcs(fake)
        sync.SyncService._quiet_pcs(fake)  # the same day: not again (also after a restart: remembered in the journal)
        self.assertEqual(len(alerts), 1)
        self.assertIn('Store PC', alerts[0][0][1])
        self.assertEqual(alerts[0][1]['key'], 'quiet|b')


class SecondReviewTest(unittest.TestCase):
    """Regressions of the second whole-code review."""

    def test_saved_change_survives_a_failing_note_file(self):
        root = tempfile.mkdtemp()
        try:
            p = Peer(root, 'pc')

            def broken(*a, **k):
                raise OSError('disk full')
            p.node.record_written = broken
            real_alert = p.journal.alert

            def alert_also_fails(*a, **k):
                real_alert(*a, **k)
                raise sqlite3.OperationalError('disk full')
            p.journal.alert = alert_also_fails
            p.commit('add', [{'e': 'areas', 'id': 'A1', 'op': 'put', 'row': {'id': 'A1', 'name': 'One'}}])  # must not raise
            self.assertEqual([a['name'] for a in p.state()['areas']], ['One'])
            self.assertTrue(any(a['kind'] == 'disk' for a in p.journal.alerts()))
            p.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_fold_all_keeps_going(self):
        import types
        import sync
        calls = []

        class Bad:
            def fold_pending(self):
                calls.append('bad')
                raise sqlite3.OperationalError('database is locked')

        class Good:
            def fold_pending(self):
                calls.append('good')
        fake = types.SimpleNamespace(auth=Bad(), store=Good(), log=lambda m: calls.append('log'))
        sync.SyncService.fold_all(fake)
        self.assertEqual(calls, ['bad', 'log', 'good'])

    def test_future_clock_is_not_kept(self):
        import time as _t
        import journal
        c = journal.HLC(0)
        far = int((_t.time() + 30 * 86400) * 1000) << 16
        root = tempfile.mkdtemp()
        try:
            p = Peer(root, 'pc')
            p.commit('x', [{'e': 'areas', 'id': 'A1', 'op': 'put', 'row': {'id': 'A1', 'name': 'One'}}])
            p.journal.conn.execute('UPDATE changes SET hlc=?', (far,))
            p.journal.conn.commit() if p.journal.conn.in_transaction else None
            j2 = journal.Journal(p.dir, p.node, p.journal.business)
            self.assertLess(j2.clock.last >> 16, (_t.time() + 2 * 3600) * 1000)
            j2.conn.close()
            p.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)
        self.assertTrue(c.now() > 0)


class AuditListColumnsTest(unittest.TestCase):
    """Narrow activity-list columns. A missing list still returns the full row, including stored text."""

    FIELDS = ('id', 'ts', 'user', 'node', 'label', 'entity', 'op', 'entity_id')
    HIDDEN = ('changes', 'before', 'after', 'ip', 'user_id', 'lsn', 'origin', 'cseq', 'txn', 'scope_id', 'kind')
    MARKER = 'hidden-column-marker'

    def setUp(self):
        import journal
        self.journal = journal
        self.root = tempfile.mkdtemp(prefix='to-audit-cols-')
        self.peer = Peer(self.root, 'pc')
        self.j = self.peer.journal
        self.node = self.peer.node.id
        self.j.conn.execute('INSERT INTO nodes (id, name, status) VALUES (?,?,?)', (self.node, 'Office PC', 'active'))

    def tearDown(self):
        self.peer.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def add(self, **kw):
        row = {
            'origin': 'o', 'cseq': 1, 'node': self.node, 'kind': 'data', 'ts': '2026-10-16T09:00:00',
            'txn': 't', 'user': 'clerk', 'user_id': 'uid', 'ip': '203.0.113.9', 'label': 'Closed trip 26-A-00001',
            'entity': 'trips', 'entity_id': 'trip1', 'scope_id': 'cat1', 'op': 'update',
            'changes': '{}', 'before': None, 'after': None,
        }
        row.update(kw)
        cols = list(row)
        self.j.conn.execute(
            'INSERT INTO audit (' + ','.join(cols) + ') VALUES (' + ','.join('?' * len(cols)) + ')',
            [row[c] for c in cols])
        return self.j.conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    def assert_hidden(self, payload):
        if self.MARKER in json.dumps(payload, ensure_ascii=False):
            raise AssertionError('projected audit response included a hidden column')

    def assert_kept(self, payload):
        if self.MARKER not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError('full audit response did not keep the stored column')

    def test_whitelist_is_exact_and_the_screen_requests_only_that_list(self):
        self.assertEqual(self.journal.AUDIT_LIST_COLUMNS, self.FIELDS)
        for name in self.HIDDEN:
            self.assertNotIn(name, self.journal.AUDIT_LIST_COLUMNS)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'js', 'views', 'activity.js'), encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn("'" + ','.join(self.FIELDS) + "'", src)
        self.assertIn('&fields=', src)
        self.assertNotIn(','.join(self.FIELDS) + ',changes', src)

    def test_unknown_duplicate_and_hidden_columns_are_refused(self):
        self.add(changes='{"v":"%s"}' % self.MARKER)
        before = self.j.query('audit')['total']
        for raw in ('before', 'after', 'changes', 'ip', 'user_id', '*', 'id,before', 'id,id', 'id,', ',', '',
                    'id;DROP TABLE audit', 'ID', 'node_name', 'id ts'):
            with self.assertRaises(BadRequest):
                self.j.query('audit', columns=raw)
            self.assertEqual(self.j.query('audit')['total'], before)
        with self.assertRaises(BadRequest):
            self.j.query('activity', columns='id,ts,user,node,label,entity,op,entity_id')
        with self.assertRaises(BadRequest):
            self.j.query('security', columns=self.FIELDS)
        self.assertIsNone(self.journal.log_list_columns({}))
        self.assertIsNone(self.journal.log_list_columns({'limit': '200'}))
        with self.assertRaises(BadRequest):
            self.journal.log_list_columns({'fields': ''})
        with self.assertRaises(BadRequest):
            self.journal.log_list_columns({'fields': 'id', 'columns': 'label'})
        with self.assertRaises(BadRequest):
            self.journal.log_list_columns({'columns': 'before'})
        self.assertEqual(self.journal.log_list_columns({'fields': 'id, label', 'columns': 'id, label'}), ('id', 'label'))
        self.assertEqual(self.journal.log_list_columns({'columns': ','.join(self.FIELDS)}), self.FIELDS)
        self.assert_kept(self.j.query('audit'))

    def test_default_row_stays_full_and_projection_drops_stored_text(self):
        self.add(changes='{"note":"%s"}' % self.MARKER, before='{"was":"old"}', after='{"now":"new"}')
        full = self.j.query('audit')
        row = full['rows'][0]
        for key in ('changes', 'before', 'after', 'ip', 'user_id', 'label', 'node_name'):
            self.assertIn(key, row)
        self.assert_kept(row)
        projected = self.j.query('audit', columns=self.FIELDS)
        shown = projected['rows'][0]
        self.assertEqual(set(shown), set(self.FIELDS))
        self.assertNotIn('node_name', shown)
        self.assertEqual(shown['node'], self.node)
        self.assertTrue(any(n.get('id') == self.node and n.get('name') == 'Office PC' for n in projected['nodes']))
        self.assertEqual(shown['label'], 'Closed trip 26-A-00001')
        self.assert_hidden(projected)
        self.assertEqual(projected['total'], full['total'])
        self.assertEqual(set(projected), {'total', 'rows', 'users', 'nodes'})
        narrow = self.j.query('audit', columns=('id', 'label'))
        self.assertEqual(set(narrow['rows'][0]), {'id', 'label'})
        self.assert_hidden(narrow)
        self.j.conn.execute(
            'INSERT INTO activity (node, ts, user, ip, type, action, target, page, detail) VALUES (?,?,?,?,?,?,?,?,?)',
            (self.node, '2026-10-16T09:00:00', 'clerk', '203.0.113.9', 'view', 'Opened', 'trips', 'trips', self.MARKER))
        activity = self.j.query('activity')
        self.assertIn('detail', activity['rows'][0])
        self.assert_kept(activity['rows'][0])
        with self.assertRaises(BadRequest):
            self.j.query('activity', columns='id')

    def test_search_still_matches_stored_text_and_count_ignores_the_column_list(self):
        label_id = self.add(label='label-token', entity='trips', entity_id='e-label', ts='2026-10-16T09:00:00', changes='{}')
        entity_id = self.add(label='plain', entity='entity-token', entity_id='e-entity', ts='2026-10-16T09:00:01', changes='{}')
        eid = self.add(label='plain', entity='trips', entity_id='entity-id-token', ts='2026-10-16T09:00:02', changes='{}')
        changes_id = self.add(label='plain', entity='trips', entity_id='e-changes', ts='2026-10-16T09:00:03',
                               changes='{"v":"%s"}' % self.MARKER)
        before_id = self.add(label='plain', entity='trips', entity_id='e-before', ts='2026-10-16T09:00:04',
                              before='{"v":"marker-before"}', changes='{}')
        after_id = self.add(label='plain', entity='trips', entity_id='e-after', ts='2026-10-16T09:00:05',
                             after='{"v":"marker-after"}', changes='{}')
        for needle, rid in (('label-token', label_id), ('entity-token', entity_id), ('entity-id-token', eid),
                            (self.MARKER, changes_id), ('marker-before', before_id), ('marker-after', after_id)):
            full = self.j.query('audit', q=needle)
            projected = self.j.query('audit', q=needle, columns=self.FIELDS)
            self.assertEqual(full['total'], 1)
            self.assertEqual(projected['total'], 1)
            self.assertEqual(full['rows'][0]['id'], rid)
            self.assertEqual(projected['rows'][0]['id'], rid)
        hit = self.j.query('audit', q=self.MARKER, columns=self.FIELDS)
        self.assert_hidden(hit)
        self.assert_kept(self.j.query('audit', q=self.MARKER))
        self.assert_hidden(self.j.query('audit', q='marker-before', columns=('id', 'label')))
        self.assert_hidden(self.j.query('audit', q='marker-after', columns=('id', 'entity_id')))
        limited = self.j.query('audit', limit=1, columns=self.FIELDS)
        self.assertEqual(len(limited['rows']), 1)
        self.assertEqual(limited['total'], 6)
        self.assertEqual(self.j.query('audit', limit=1)['total'], 6)
        same = self.j.query('audit', q='plain')
        projected_same = self.j.query('audit', q='plain', columns=('id', 'ts'))
        self.assertEqual([r['id'] for r in projected_same['rows']], [r['id'] for r in same['rows']])
        self.assertGreater(same['rows'][0]['id'], same['rows'][-1]['id'])

    def test_scope_and_business_filters_still_apply_when_columns_are_narrow(self):
        self.add(entity='trips', entity_id='t-cat1', scope_id='cat1', label='in cat')
        self.add(entity='trips', entity_id='t-cat2', scope_id='cat2', label='other cat', ts='2026-10-16T10:00:00')
        self.add(entity='users', entity_id='u1', scope_id=None, label='Add user', ts='2026-10-16T11:00:00',
                 changes='{"name":"%s"}' % self.MARKER)
        admin = self.j.query('audit', columns=self.FIELDS)
        business = self.j.query('audit', columns=self.FIELDS, business_only=True)
        scoped = self.j.query('audit', columns=self.FIELDS, scopes=['cat1'])
        self.assertEqual(admin['total'], 3)
        self.assertEqual(business['total'], 2)
        self.assertTrue(all(row['entity'] != 'users' for row in business['rows']))
        self.assertEqual(scoped['total'], 1)
        self.assertEqual(scoped['rows'][0]['entity_id'], 't-cat1')
        self.assertNotIn('scope_id', scoped['rows'][0])
        self.assert_hidden(business)
        self.assert_hidden(admin)
        self.assertEqual(self.j.query('audit', business_only=True)['total'], business['total'])
        self.assertEqual(self.j.query('audit', scopes=['cat1'])['total'], scoped['total'])
        self.assertTrue(any(row['entity'] == 'users' for row in admin['rows']))


class ActivityRetryTest(unittest.TestCase):
    def test_failed_activity_flush_keeps_events_for_retry(self):
        from unittest.mock import patch
        c = Cluster(1)
        self.addCleanup(c.close)
        journal = c.peers[0].journal
        journal.log_activity('bench', 'local', [{'type': 'view', 'target': 'synthetic'}])
        with patch.object(journal, 'write', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                journal.flush_activity()
        self.assertEqual(len(journal._activity), 1)
        journal.flush_activity()
        self.assertEqual(journal._activity, [])
        self.assertEqual(journal.conn.execute("SELECT COUNT(*) FROM activity WHERE target='synthetic'").fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
