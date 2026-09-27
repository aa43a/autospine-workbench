from contextlib import redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_transverse_timeline_screen import run, validate_times


class TimelineScreenTests(unittest.TestCase):
    def test_rejects_wrong_source_modified_duplicate_and_nonfinite_times(self):
        times=[0.,.5,1.]
        report=dict(parent_artifact_sha256='parent',slot='leg',
                    times_sha256=sha256(canonical_bytes(times)).hexdigest())
        validate_times(report,times,'parent','leg')
        for values in ([0.,.6,1.],[0.,.5,.5],[0.,float('nan')],[]):
            with self.assertRaises(ValueError):validate_times(report,values,'parent','leg')
        with self.assertRaises(ValueError):validate_times(report,times,'other','leg')

    def test_checks_every_time_in_batches_and_keeps_late_failure(self):
        times=[i/256 for i in range(257)];batches=[]
        def prepare(document,slot,batch,rings):batches.append(batch);return batch
        def screen(batch,gains):
            return dict(trials=[dict(gain=g,failures=[{'time':1.}] if 1. in batch else []) for g in gains])
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);output=root/'output.json'
            (root/'validation-times.json').write_bytes(canonical_bytes(times))
            (root/'report.json').write_bytes(canonical_bytes(dict(parent_artifact_sha256='parent',
                slot='leg',times_sha256=sha256(canonical_bytes(times)).hexdigest())))
            with patch('m4_transverse_timeline_screen.AnimatedStore') as store, \
                 patch('m4_transverse_timeline_screen.prepare_poses',side_effect=prepare), \
                 patch('m4_transverse_timeline_screen.screen',side_effect=screen),redirect_stdout(io.StringIO()):
                store.return_value.read.return_value={'skeleton.json':b'{}'}
                run(root,'parent','leg',root,output)
            result=json.loads(output.read_bytes())
            self.assertEqual([len(b) for b in batches],[256,1])
            self.assertEqual(result['times'],times)
            self.assertEqual(result['unexcluded_gains'],[])
            self.assertIsNone(result['suggested_gain'])
            self.assertFalse(result['selected'])
            self.assertEqual(result['trials'][0]['failures'],[{'time':1.}])
