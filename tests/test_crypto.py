"""I10: signing and key export use the maintained `cryptography` library when it is installed; the pure-Python reference stays only as the
fallback of the portable copy and is cross-checked here (RFC 8032 vectors, both directions). The key-export file is versioned and
authenticated; files of the older version stay readable."""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
import ed25519  # noqa: E402
import nodectl  # noqa: E402

# RFC 8032 section 7.1, tests 1 and 2
VECTORS = [
    ('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60', 'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
     'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
    ('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb', '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
     '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'),
]


class PureReference(unittest.TestCase):
    def test_rfc_8032_vectors_with_the_reference(self):
        for seed, pub, msg, sig in VECTORS:
            seed, pub, msg, sig = (bytes.fromhex(x) for x in (seed, pub, msg, sig))
            self.assertEqual(ed25519._py_public_key(seed), pub)
            self.assertEqual(ed25519._py_sign(seed, msg), sig)
            self.assertTrue(ed25519._py_verify(pub, msg, sig))


@unittest.skipUnless(ed25519.BACKEND == 'cryptography', 'the cryptography package is not installed')
class Maintained(unittest.TestCase):
    def test_the_program_uses_the_maintained_library(self):
        self.assertEqual(ed25519.BACKEND, 'cryptography')

    def test_rfc_8032_vectors_and_both_directions(self):
        for seed, pub, msg, sig in VECTORS:
            seed, pub, msg, sig = (bytes.fromhex(x) for x in (seed, pub, msg, sig))
            self.assertEqual(ed25519.public_key(seed), pub)
            self.assertEqual(ed25519.sign(seed, msg), sig)
            self.assertTrue(ed25519.verify(pub, msg, sig))
            self.assertTrue(ed25519._py_verify(pub, msg, sig))
            self.assertFalse(ed25519.verify(pub, msg + b'x', sig))
            self.assertFalse(ed25519.verify(pub, msg, sig[:-1] + bytes([sig[-1] ^ 1])))
            self.assertFalse(ed25519.verify(pub[:-1], msg, sig))

    def test_random_keys_sign_and_verify_across_the_two_implementations(self):
        for i in range(5):
            seed = os.urandom(32)
            msg = os.urandom(40 + i)
            self.assertEqual(ed25519.public_key(seed), ed25519._py_public_key(seed))
            self.assertTrue(ed25519._py_verify(ed25519.public_key(seed), msg, ed25519.sign(seed, msg)))
            self.assertTrue(ed25519.verify(ed25519.public_key(seed), msg, ed25519._py_sign(seed, msg)))

    def test_junk_never_raises(self):
        for pub, msg, sig in ((b'', b'', b''), (b'x' * 32, b'm', b'y' * 64), (None, b'm', b's' * 64)):
            self.assertFalse(ed25519.verify(pub, msg, sig))

    def test_the_pure_fallback_can_be_forced(self):
        r = subprocess.run([sys.executable, '-c', 'import sys; sys.path.insert(0, %r); import ed25519; print(ed25519.BACKEND)' % os.path.join(ROOT, 'server')],
                           env=dict(os.environ, TO_PURE_ED25519='1'), capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), 'pure-python')


class KeyFile(unittest.TestCase):
    PW = 'a long passphrase 123'
    SECRET = bytes(range(32))
    META = {'cluster': 'c1', 'authority_pub': 'ab' * 32, 'exported': '2026-10-11', 'from': 'OFFICE-PC'}

    @unittest.skipUnless(nodectl._aead(), 'the cryptography package is not installed')
    def test_a_new_file_is_authenticated_version_2(self):
        box = nodectl.seal(self.SECRET, self.PW, self.META)
        self.assertEqual((box['v'], box['aead']), (2, 'chacha20poly1305'))
        self.assertNotIn(self.SECRET.hex(), json.dumps(box))
        self.assertEqual(nodectl.unseal(box, self.PW), self.SECRET)
        with self.assertRaises(ValueError):
            nodectl.unseal(box, 'the wrong passphrase')
        for field, value in (('cluster', 'c2'), ('authority_pub', 'cd' * 32), ('from', 'OTHER-PC'), ('v', 1)):
            with self.assertRaises(ValueError, msg=field):
                nodectl.unseal({**box, field: value}, self.PW)               # a changed header makes the file unreadable
        with self.assertRaises(ValueError):
            nodectl.unseal({**box, 'ct': box['ct'][:-2] + ('00' if not box['ct'].endswith('00') else '11')}, self.PW)

    def test_an_older_version_1_file_still_opens(self):
        import hashlib
        import hmac
        salt, nonce = b's' * 16, b'n' * 16
        ke, km = nodectl._keys(self.PW, salt)
        ct = bytes(a ^ b for a, b in zip(self.SECRET, nodectl._stream(ke, nonce, len(self.SECRET))))
        old = {'v': 1, 'kdf': 'scrypt-n32768-r8-p1', 'salt': salt.hex(), 'nonce': nonce.hex(), 'ct': ct.hex(),
               'tag': hmac.new(km, salt + nonce + ct, hashlib.sha256).hexdigest(), **self.META}
        self.assertEqual(nodectl.unseal(old, self.PW), self.SECRET)
        with self.assertRaises(ValueError):
            nodectl.unseal({**old, 'ct': '00' * 32}, self.PW)

    def test_a_file_from_the_future_is_refused_politely(self):
        with self.assertRaises(ValueError):
            nodectl.unseal({'v': 9, 'salt': '00', 'nonce': '00'}, self.PW)


if __name__ == '__main__':
    unittest.main()
