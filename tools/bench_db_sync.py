#!/usr/bin/env python3
"""Local-only DB/sync benchmark; stdlib + node:sqlite. Also runs on main 0333689.

Workload and identifiers are fixed; timings and temporary credentials are not.
No installed configuration is opened. D1 fixtures are seeded directly, while all
measured office requests use the real worker through gateway/dev/server.js.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'server'), str(ROOT / 'tests')]
from system import System
import gateway_client as G
from harness import ADMIN, Server, free_port, make_authority, pair, wait_until


def timed(fn):
    start = time.perf_counter()
    value = fn()
    return (time.perf_counter() - start) * 1000, value


def summary(values):
    return {'median_ms': round(statistics.median(values), 3),
            'min_ms': round(min(values), 3), 'max_ms': round(max(values), 3)}


def put(entity, rid, row):
    return {'e': entity, 'id': rid, 'op': 'put', 'row': row}


def bench_local(folder, cycles):
    data = folder / 'office'
    uploads = data / 'uploads'
    uploads.mkdir(parents=True)
    system = System(str(data), {}, str(uploads), str(folder / 'backup'), log=lambda *a: None)
    store = system.store
    statements = [0]
    def trace(sql):
        statements[0] += 1
    store.conn.set_trace_callback(trace)
    system.journal.conn.set_trace_callback(trace)
    date = G.domain.business_now().date().isoformat()
    ops = []
    for i in range(100):
        for entity, row in [('drivers', {'name': f'Driver {i}'}), ('vehicles', {'plate': f'CAR {i}'}),
                            ('people', {'name': f'Person {i}'}), ('tripCategories', {'name': f'Category {i}'})]:
            ops.append(put(entity, f'{entity}-{i}', row))
    for i in range(2000):
        row = {'no': f'BENCH-{i:04}', 'date': date, 'status': 'sent', 'driverId': f'drivers-{i % 100}',
               'vehicleId': f'vehicles-{i % 100}', 'requesterId': f'people-{i % 100}',
               'categoryId': f'tripCategories-{i % 100}', 'destination': 'Synthetic destination'}
        if i < 300:
            row.update(linkHash=hashlib.sha256(f'link-{i}'.encode()).hexdigest(),
                       linkExpiry='2099-01-01T00:00:00Z')
        ops.append(put('trips', f'trip-{i}', row))
        ops.append(put('tripPassengers', f'pax-{i}', {'tripId': f'trip-{i}', 'personId': f'people-{i % 100}'}))
    commit_ms, queries = [], []
    for i in range(0, len(ops), 100):
        statements[0] = 0
        ms, _ = timed(lambda: store.commit('Benchmark', 'local', 'Synthetic fixture', ops[i:i + 100]))
        commit_ms.append(ms)
        queries.append(statements[0])
    result = {'trips': 2000, 'list_rows': 400, 'passengers': 2000, 'commit_batch_size': 100,
              'commit': summary(commit_ms), 'commit_sql_total': sum(queries)}
    loads, counts = [], []
    for _ in range(cycles):
        statements[0] = 0
        ms, state = timed(store.state)
        assert len(state['trips']) == 2000
        loads.append(ms)
        counts.append(statements[0])
    result['state_load'] = summary(loads)
    result['state_sql_per_load'] = counts
    return system, statements, result


def bench_gateway(folder, system, statements, cycles):
    # The wrapper instruments only this temporary local process. No runtime edits.
    db, metrics = folder / 'gateway.sqlite', folder / 'metrics.json'
    module = (ROOT / 'gateway/dev/server.js').as_uri()
    js = """
import {writeFileSync} from 'node:fs';
const {makeEnv, serve} = await import(process.env.BENCH_MODULE);
const env = makeEnv();
let sql = 0, requests = 0;
const prepare = env.DB.db.prepare.bind(env.DB.db);
env.DB.db.prepare = (...args) => { sql++; return prepare(...args); };
const server = await serve(env, Number(process.env.PORT));
server.on('request', (_req, res) => { requests++; res.on('finish', () =>
  writeFileSync(process.env.BENCH_METRICS, JSON.stringify({requests, sql}))); });
console.log('READY');
"""
    env = {**os.environ, 'OFFICE_SECRET': secrets.token_hex(32), 'MASTER_KEY': '',
           'GATEWAY_DB': str(db), 'PORT': str(free_port()), 'BENCH_MODULE': module,
           'BENCH_METRICS': str(metrics)}
    proc = subprocess.Popen(['node', '--no-warnings', '--input-type=module', '-e', js],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if proc.stdout.readline().strip() != 'READY':
            raise RuntimeError('Local gateway did not start: ' + proc.stderr.read()[:500])
        cfg = G.Secrets(str(folder / 'synthetic-secrets.json'))
        cfg.data = {'url': 'http://127.0.0.1:' + env['PORT'], 'officeSecret': env['OFFICE_SECRET'],
                    'linkSecret': 'synthetic-link-secret'}
        def save_file(data, ext):
            sha = hashlib.sha256(data).hexdigest()
            (folder / (sha + ext)).write_bytes(data)
            return '/files/' + sha + ext, sha
        sync = G.GatewaySync(system.store, system.journal, system.node.id, cfg, save_file)
        def run_cycle(label):
            before = json.loads(metrics.read_text()) if metrics.exists() else {'sql': 0, 'requests': 0}
            statements[0] = 0
            ms, _ = timed(sync.cycle)
            # finish listener runs before the client reads the complete response.
            after = json.loads(metrics.read_text())
            return {'phase': label, 'ms': round(ms, 3), 'http_requests': after['requests'] - before['requests'],
                    'd1_statements': after['sql'] - before['sql'], 'sqlite_statements': statements[0]}
        results = [run_cycle('initial_publish')]
        photo = b'\xff\xd8' + bytes(range(256)) * 16
        now = int(time.time())
        with sqlite3.connect(db) as c:
            for i in range(50):
                th = hashlib.sha256(f'link-{i}'.encode()).hexdigest()
                uid, puid = str(uuid.UUID(int=i + 1, version=4)), str(uuid.UUID(int=i + 1001, version=4))
                c.execute('INSERT INTO events(uuid,token_hash,trip_id,type,body,device_id,phone_at,recv_at,second,tenant) VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (uid, th, f'trip-{i}', 'start', json.dumps({'data': {'startKm': 1000 + i}}), 'bench-device', date_now(), now, 0, 'legacy'))
                c.execute('INSERT INTO photos(uuid,token_hash,trip_id,kind,fallback,event_uuid,sha256,size,data,recv_at,tenant) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          (puid, th, f'trip-{i}', 'start_odo', 0, uid, hashlib.sha256(photo).hexdigest(), len(photo), photo, now, 'legacy'))
        results.append(run_cycle('50_events_50_photos'))
        assert sync.client().status()['events'] == 0
        assert sync.client().status()['photos'] == 0
        results += [run_cycle('idle_' + str(i + 1)) for i in range(cycles)]
        sync = G.GatewaySync(system.store, system.journal, system.node.id, cfg, save_file)
        results.append(run_cycle('restart'))
        return results
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
        proc.stderr.close()


def date_now():
    return G.domain.business_now().isoformat(timespec='seconds')


def bench_lan():
    servers = []
    try:
        for i in range(3):
            servers.append(Server('bench-' + str(i)))
            servers[-1].start()
        admin = make_authority(servers[0])
        clients = [admin] + [pair(admin, servers[0], s) for s in servers[1:]]
        for client in clients[1:]:
            client.login(*ADMIN)
        start = time.perf_counter()
        for i, client in enumerate(clients):
            client.post('/api/commit', {'label': 'Benchmark LAN', 'ops': [
                put('trips', f'lan-{i}-{j}', {'no': f'LAN-{i}-{j}', 'date': '2026-10-20', 'notes': 'Synthetic'}) for j in range(20)]})
        def converged():
            states = [c.get('/api/state') for c in clients]
            return all(len([t for t in s['trips'] if t['id'].startswith('lan-')]) == 60 for s in states)
        wait_until(converged, 60, step=0.1, what='three-node convergence')
        return {'nodes': 3, 'trips': 60, 'convergence_ms': round((time.perf_counter() - start) * 1000, 3)}
    finally:
        for srv in reversed(servers):
            srv.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, default=5)
    parser.add_argument('--skip-lan', action='store_true')
    args = parser.parse_args()
    if args.cycles < 1:
        parser.error('--cycles must be positive')
    with tempfile.TemporaryDirectory(prefix='to-dbsync-bench-') as tmp:
        folder = Path(tmp)
        system, statements, local = bench_local(folder, args.cycles)
        try:
            result = {'local': local, 'gateway': bench_gateway(folder, system, statements, args.cycles)}
        finally:
            system.close()
        result['lan'] = {'skipped': True} if args.skip_lan else bench_lan()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
