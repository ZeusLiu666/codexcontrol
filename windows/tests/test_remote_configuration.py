import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codexcontrol_windows.token_usage import RemoteTokenUsageMirror, configured_ssh_hosts


class RemoteConfigurationTests(unittest.TestCase):
    def test_unconfigured_sync_never_runs_ssh_or_creates_state(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict('os.environ', {}, clear=True):
            root = Path(temporary)
            mirror = RemoteTokenUsageMirror(root / 'state.json', root / 'cache')
            with patch('codexcontrol_windows.token_usage.subprocess.run') as run:
                self.assertEqual(mirror.sync([], None), [])
                run.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

    def test_configured_hosts_are_trimmed_deduplicated_and_validated(self):
        self.assertEqual(
            configured_ssh_hosts('build-server, user@compute.example,build-server, -oProxyCommand=bad, bad host, $(bad), [::1]'),
            ['build-server', 'user@compute.example', '[::1]'],
        )

    def test_environment_is_opt_in_and_explicit_empty_hosts_override_it(self):
        with patch.dict('os.environ', {'CODEXCONTROL_SSH_HOSTS': 'build-server'}):
            self.assertEqual(RemoteTokenUsageMirror().hosts, ['build-server'])
            self.assertEqual(RemoteTokenUsageMirror(hosts=[]).hosts, [])


if __name__ == '__main__':
    unittest.main()
