"""Factory access gate (Apps-Factory packages/af-access, controls IAM-08..IAM-12, learned from BAMS).

The permission list, the menu's page table (js/shell.js) and the ready-made profiles keep the factory rules: one administrator
group shown apart, a locked profile with every right, every page opened by a known permission, every permission, group and
profile named in both languages, every profile usable, and a personal link never carries an administrator right."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
import afaccess  # noqa: E402
import auth  # noqa: E402

PAIR = re.compile(r"""'([\w.\-]+)':\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""")
ROUTE = re.compile(r"\{ id: '([\w-]+)', icon: '[\w-]+', group: '\w+', perm: (null|'[\w.]+'|\[[^\]]*\])")


def read(*path):
    with open(os.path.join(ROOT, *path), encoding='utf-8') as f:
        return f.read()


def words(lang):
    return {k: a or b for k, a, b in PAIR.findall(read('js', 'i18n', lang + '.js'))}


def slug(group):  # the same key js/views/access.js builds for a group title
    return '_'.join(re.sub(r'[^a-z]+', ' ', group.lower()).split()[:2])


def catalogue(ar, en=None):
    """English words: the dictionary's when it has the key (that is what the screen shows), else the server's label."""
    en = en if en is not None else words('en')
    pick = lambda key, fallback: en[key] if key in en else fallback  # noqa: E731
    groups = []
    for i, (g, ps) in enumerate(auth.PERMISSIONS):
        admin = g == auth.ADMIN_GROUP
        groups.append({'id': slug(g), 'admin': admin, 'labels': {'en': pick('permgroup.' + slug(g), g), 'ar': ar.get('permgroup.' + slug(g), '')},
                       'permissions': [{'id': p, 'kind': 'page' if i == 0 else 'admin' if admin else 'action',
                                        'labels': {'en': pick('perm.' + p, label), 'ar': ar.get('perm.' + p, '')}} for p, label in ps]})
    shell = read('js', 'shell.js')
    pages = {pid: '*' if perm == 'null' else re.findall(r"'([\w.]+)'", perm) for pid, perm in ROUTE.findall(shell)}
    every = set(re.findall(r"^\s*\{ id: '([\w-]+)', icon:", shell, re.M))  # every menu entry, however its fields are written
    assert every == set(pages), f'menu routes the gate could not read: {sorted(every - set(pages))}'
    profiles = [{'id': pid, 'locked': pid == auth.LOCKED_PROFILE, 'labels': {'en': pick('prof.' + pid, name), 'ar': ar.get('prof.' + pid, '')},
                 'perms': list(auth.ALL if pid == auth.LOCKED_PROFILE else perms)} for pid, name, perms in auth.BUILTIN_PROFILES]
    return {'product': os.path.basename(ROOT), 'languages': ['en', 'ar'], 'manage': 'users.manage', 'groups': groups,
            'pages': pages, 'profiles': profiles}


class AccessGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ar = words('ar')
        cls.cat = catalogue(cls.ar)

    def test_catalogue_passes_the_factory_gate(self):
        self.assertGreater(len(self.cat['pages']), 10)
        self.assertEqual([str(f) for f in afaccess.check(self.cat)], [])

    def test_gate_catches_a_missing_arabic_word(self):
        first = auth.PERMISSIONS[1][1][0][0]
        cat = catalogue({k: v for k, v in self.ar.items() if k != 'perm.' + first})
        self.assertIn('label-missing', {f.code for f in afaccess.errors(cat)})

    def test_server_and_gate_agree_on_administrator_rights(self):
        self.assertEqual(afaccess.admin_perms(self.cat), auth.ADMIN_PERMS)
        for p in sorted(auth.ADMIN_PERMS):
            self.assertFalse(auth.Auth.link_allowed({'perms': ['overview.view', p]}), p)  # a link never carries one
        self.assertTrue(auth.Auth.link_allowed({'perms': list(auth.WORK)}))
        self.assertEqual(afaccess.admin_safety([], [{'id': 'x', 'perms': [p], 'link': True} for p in ['users.manage']], 'y',
                                               auth.ADMIN_PERMS), ['link-admin'])

    def test_gate_catches_an_empty_english_word(self):
        en = words('en')
        first = auth.PERMISSIONS[1][1][0][0]
        en['perm.' + first] = ''
        self.assertIn('label-missing', {f.code for f in afaccess.errors(catalogue(self.ar, en))})

    def test_english_and_arabic_have_the_same_permission_words(self):
        en = words('en')
        keys = lambda d: {k for k in d if k.startswith(('perm.', 'permgroup.', 'prof.', 'acc.matrix'))}  # noqa: E731
        self.assertEqual(sorted(keys(self.ar) ^ keys(en)), [])


if __name__ == '__main__':
    unittest.main()
