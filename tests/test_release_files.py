"""B6 (the part code can prove): CI runs every test module, including the access gate, and exercises the INSTALLED product on Windows
(silent install, folder protection, firewall rule private/domain only, this-PC-only install without a rule, core journey, update over it, N-1 update, uninstall keeps data)."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = open(os.path.join(ROOT, '.github', 'workflows', 'build.yml'), encoding='utf-8').read()


class WorkflowTest(unittest.TestCase):
    def test_every_test_module_runs_in_ci(self):
        line = next(l for l in WORKFLOW.splitlines() if 'python -m unittest' in l)
        listed = set(line.split('unittest', 1)[1].split())
        here = {f[:-3] for f in os.listdir(os.path.join(ROOT, 'tests')) if f.startswith('test_') and f.endswith('.py')}
        self.assertEqual(sorted(here - listed), [], 'a test module that CI never runs')
        self.assertIn('test_access_gate', listed)

    def test_the_installed_product_is_exercised_on_windows(self):
        for needle in ('/VERYSILENT', 'journey_exe.py first', 'journey_exe.py after', 'journey_exe.py legacy', 'icacls', 'firewall show rule',
                       'unins000.exe', 'RELEASE-PROOF', 'installer_sha256', 'source_commit', '/TASKS=thispconly'):
            self.assertIn(needle, WORKFLOW, needle)
        self.assertIn("'No rules match') { throw 'the default install must add", WORKFLOW)  # the default install must HAVE the rule
        self.assertNotIn('Start-Process -FilePath $setup.FullName -ArgumentList \'/VERYSILENT\',\'/SUPPRESSMSGBOXES\',\'/NORESTART\' -Wait', WORKFLOW)
        self.assertIn("'data was not written", WORKFLOW)

    def test_the_journey_tool_covers_the_core_steps(self):
        src = open(os.path.join(ROOT, 'tools', 'journey_exe.py'), encoding='utf-8').read()
        for needle in ('/api/auth/setup', 'expect=402', '/api/licence/activate', '/api/trips/new', '/api/backups', 'proc.kill()', 'exactly once'):
            self.assertIn(needle, src, needle)

    def test_build_ships_the_guide_and_the_taxonomy(self):
        self.assertIn("'guide'", open(os.path.join(ROOT, 'tools', 'make_assets.py'), encoding='utf-8').read())
        build = open(os.path.join(ROOT, 'tools', 'build_windows.py'), encoding='utf-8').read()
        self.assertIn('aftelemetry_events.json', build)

    def test_vendored_factory_parts_carry_their_header(self):
        for name in ('afguide.py', 'afconsent.py', 'aftelemetry.py', 'afcodes.py'):
            head = open(os.path.join(ROOT, 'server', name), encoding='utf-8').read(400)
            self.assertRegex(head, r'Vendored from Apps-Factory packages/af-', name)
        for name in ('af-guide.js', 'af-consent.js', 'af-telemetry.js'):
            self.assertRegex(open(os.path.join(ROOT, 'js', 'vendor', name), encoding='utf-8').read(300), r'Vendored from Apps-Factory', name)


if __name__ == '__main__':
    unittest.main()
