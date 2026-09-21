"""Sandbox probes use synthetic sentinels only; no credentials or cloud."""
import os
from pathlib import Path
import unittest

@unittest.skipUnless(os.environ.get('TWB_PROBE_RUN'), 'explicit private sandbox probe root required')
class SandboxTests(unittest.TestCase):
    def test_active_sandbox_denies_canary_effects(self):
        from things_workbench import native_runtime
        self.assertTrue(hasattr(native_runtime,'probe'), 'active sandbox probe missing')
        root=Path(os.environ['TWB_PROBE_RUN']); root.mkdir(mode=0o700)
        runtime=native_runtime.build(Path('/Applications/Things3.app'),root/'runtime')
        result=native_runtime.probe(runtime,root/'probe')
        for key in ('read_denied','write_denied','fork_denied','tcp_denied','udp_denied','credential_policy_denied','appleevent_policy_denied','allowed_write'):
            self.assertTrue(result[key],key)
