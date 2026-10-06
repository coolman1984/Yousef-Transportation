"""The office web port (F04): foreign Host names are refused (DNS rebinding), normal addresses of the PC keep working,
the number of open connections is bounded, and bad requests fail safely. Direct HTTP calls against a real server."""
import http.client
import json
import os
import socket
import sys
import time
import unittest

from harness import Server

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import netpolicy  # noqa: E402


def raw(server, method, path, host, body=None, headers=None, source=None):
    """One request with a chosen Host header (and optionally a chosen source address); returns (status, parsed json or text)."""
    c = http.client.HTTPConnection('127.0.0.1', server.port, timeout=10, source_address=(source, 0) if source else None)
    try:
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        if host is not None:
            c.putheader('Host', host)
        data = None if body is None else json.dumps(body).encode()
        for k, v in {'Content-Type': 'application/json', **(headers or {})}.items():
            c.putheader(k, v)
        if data is not None:
            c.putheader('Content-Length', str(len(data)))
        c.endheaders(data)
        r = c.getresponse()
        text = r.read().decode('utf-8', 'replace')
        try:
            return r.status, json.loads(text)
        except ValueError:
            return r.status, text
    finally:
        c.close()


class HostCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('net', extra_cfg={'allowed_hosts': ['trips.office.example']}).start()

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_a_a_web_site_that_points_its_name_at_this_pc_is_refused(self):
        """DNS rebinding: the browser on this PC talks to 127.0.0.1 but sends the attacker's name, so it would count as 'local'."""
        for host in ('evil.example.com', f'evil.example.com:{self.S.port}', 'attacker.io', 'localhost.evil.com', '127.0.0.1.evil.com'):
            st, j = raw(self.S, 'GET', '/api/auth/status', host)
            self.assertEqual(st, 403, host)
            self.assertIn('address', str(j).lower())

    def test_b_the_first_administrator_cannot_be_created_through_a_foreign_name(self):
        st, j = raw(self.S, 'POST', '/api/auth/setup', 'evil.example.com', {'username': 'mallory', 'full_name': 'Mal', 'password': 'Quarter-pass77'})
        self.assertEqual(st, 403, j)
        self.assertFalse(self.S.client().get('/api/auth/status')['hasUsers'], 'nobody was created')

    def test_c_every_normal_address_of_the_pc_still_works(self):
        import socket as s
        names = ['localhost', f'localhost:{self.S.port}', '127.0.0.1', f'127.0.0.1:{self.S.port}', f'[::1]:{self.S.port}', '192.168.1.20:8090', '10.0.0.5',
                 'office-pc', 'office-pc:8090', 'OFFICE-PC', 'accounts-pc.local:8090', 'trips.office.example', 'Trips.Office.Example:8090', s.gethostname()]
        for host in names:
            st, j = raw(self.S, 'GET', '/api/auth/status', host)
            self.assertEqual(st, 200, f'{host}: {j}')

    def test_d_no_host_or_a_broken_one_is_refused(self):
        for host in (None, '', ' ', 'bad host name', 'a' * 300, 'evil.com\r\nX-Injected: 1'):
            try:
                st, _ = raw(self.S, 'GET', '/api/auth/status', host)
            except (http.client.HTTPException, ValueError, OSError):
                continue                                                  # the client itself refused to send it
            self.assertIn(st, (400, 403), repr(host))

    def test_e_pages_and_files_are_covered_too(self):
        for path in ('/', '/index.html', '/js/app.js', '/css/base.css'):
            self.assertEqual(raw(self.S, 'GET', path, 'evil.example.com')[0], 403, path)
            self.assertEqual(raw(self.S, 'GET', path, 'localhost')[0] in (200, 304), True, path)

    def test_f_bad_lengths_fail_safely(self):
        st, _ = raw(self.S, 'POST', '/api/auth/login', 'localhost', None, {'Content-Length': 'abc'})
        self.assertEqual(st, 400)
        st, j = raw(self.S, 'POST', '/api/auth/login', 'localhost', None, {'Content-Length': str(10 ** 12)})
        self.assertEqual(st, 400, j)
        st, _ = raw(self.S, 'POST', '/api/auth/login', 'localhost', None, {'Content-Length': '-5'})
        self.assertEqual(st, 400)
        self.assertEqual(self.S.client().get('/api/auth/status')['hasUsers'], False, 'the server is still fine')


class PeerRuleTest(unittest.TestCase):
    def test_a_private_networks_and_this_pc_are_allowed_the_internet_is_not(self):
        for ip in ('127.0.0.1', '::1', '::ffff:127.0.0.1', '192.168.1.20', '10.20.30.40', '172.16.5.5', '172.31.255.254', '169.254.10.1', '100.64.1.1',
                   'fe80::1%eth0', 'fd12:3456::1', '::ffff:192.168.1.5'):
            self.assertTrue(netpolicy.peer_allowed(ip), ip)
        for ip in ('8.8.8.8', '41.33.10.5', '172.32.0.1', '172.15.255.255', '100.128.0.1', '2001:db8::1', '2606:4700::1111', '::ffff:8.8.8.8', 'not an ip', '', None):
            self.assertFalse(netpolicy.peer_allowed(ip), ip)

    def test_b_a_configured_list_replaces_the_private_ranges_but_not_this_pc(self):
        nets, bad = netpolicy.parse_networks(['192.168.1.0/24', ' 10.20.0.0/16 ', 'nonsense', '192.168.7.9', 42])
        self.assertEqual(bad, ['nonsense', '42'])
        self.assertEqual(len(nets), 3, 'a single address is a network of one')
        for ip in ('192.168.1.77', '10.20.5.5', '192.168.7.9', '127.0.0.1', '::1'):
            self.assertTrue(netpolicy.peer_allowed(ip, nets), ip)
        for ip in ('192.168.2.1', '10.21.0.1', '172.16.0.1', '8.8.8.8', 'fd00::1'):
            self.assertFalse(netpolicy.peer_allowed(ip, nets), ip)
        self.assertEqual(netpolicy.parse_networks('junk'), ([], []))


class PeerServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 127.0.0.2 is "another address" for the server: allowed by default (private), refused when the list names other networks
        cls.default = Server('netdef').start()
        cls.narrow = Server('netnarrow', extra_cfg={'allowed_networks': ['10.99.0.0/16', 'garbage']}).start()
        cls.junk = Server('netjunk', extra_cfg={'allowed_networks': ['garbage']}).start()

    @classmethod
    def tearDownClass(cls):
        for s in (cls.default, cls.narrow, cls.junk):
            s.cleanup()

    def test_c_by_default_every_private_address_connects(self):
        self.assertEqual(raw(self.default, 'GET', '/api/auth/status', 'localhost', source='127.0.0.2')[0], 200)

    def test_d_a_listed_network_list_refuses_everybody_else_but_never_this_pc(self):
        st, j = raw(self.narrow, 'GET', '/api/auth/status', 'localhost', source='127.0.0.2')
        self.assertEqual(st, 403)
        self.assertIn('office network', str(j))
        st, j = raw(self.narrow, 'POST', '/api/auth/setup', 'localhost', {'username': 'x', 'full_name': 'X', 'password': 'Quarter-pass77'}, source='127.0.0.2')
        self.assertEqual(st, 403, 'nothing can be changed from a refused address')
        self.assertEqual(raw(self.narrow, 'GET', '/api/auth/status', 'localhost')[0], 200, 'this PC itself always gets in')
        self.assertFalse(self.narrow.client().get('/api/auth/status')['hasUsers'])

    def test_e_a_list_with_nothing_usable_does_not_lock_everybody_out(self):
        self.assertEqual(raw(self.junk, 'GET', '/api/auth/status', 'localhost', source='127.0.0.2')[0], 200)


class ConnectionLimitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('netcap', extra_cfg={'max_connections': 3, 'idle_timeout_seconds': 3}).start()

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_g_too_many_open_connections_get_a_polite_503_and_the_server_recovers(self):
        held = []
        try:
            for _ in range(3):                                            # idle sockets that never send a request
                s = socket.create_connection(('127.0.0.1', self.S.port), timeout=5)
                held.append(s)
            time.sleep(0.3)
            st, _ = raw(self.S, 'GET', '/api/auth/status', 'localhost')
            self.assertEqual(st, 503)
        finally:
            for s in held:
                s.close()
        deadline = time.time() + 10
        while time.time() < deadline:                                     # the silent ones are dropped and normal service resumes
            try:
                if raw(self.S, 'GET', '/api/auth/status', 'localhost')[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.3)
        self.fail('the server did not recover after the idle connections closed')

    def test_h_a_silent_connection_is_closed_after_the_idle_timeout(self):
        s = socket.create_connection(('127.0.0.1', self.S.port), timeout=10)
        try:
            t0 = time.time()
            data = s.recv(10)                                             # the server closes it; recv returns b''
            self.assertEqual(data, b'')
            self.assertLess(time.time() - t0, 8)
        finally:
            s.close()


if __name__ == '__main__':
    unittest.main()
