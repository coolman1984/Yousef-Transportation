"""The office web port (F04): foreign Host names are refused (DNS rebinding), normal addresses of the PC keep working,
the number of open connections is bounded, and bad requests fail safely. Direct HTTP calls against a real server."""
import http.client
import json
import socket
import time
import unittest

from harness import Server


def raw(server, method, path, host, body=None, headers=None):
    """One request with a chosen Host header; returns (status, parsed json or text)."""
    c = http.client.HTTPConnection('127.0.0.1', server.port, timeout=10)
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
