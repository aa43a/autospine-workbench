import json
import tempfile
import unittest
from pathlib import Path

from m4_additive_interval_repair import run


class IntervalRepairPrerequisiteTests(unittest.TestCase):
    def test_projection_failure_stops_before_candidate_access_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);job='motion-'+'a'*32
            folder=state/'jobs/motion-intake-v1'/job;folder.mkdir(parents=True)
            (folder/'result.json').write_text(json.dumps({'result':{'issues':[
                {'stage':'projection','reason_code':'character_length_projection_collapsed'}]}}))
            output=state/'output'
            with self.assertRaisesRegex(ValueError,'projection_failed'):
                run(state,job,'arm',output,temporal=True)
            self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
