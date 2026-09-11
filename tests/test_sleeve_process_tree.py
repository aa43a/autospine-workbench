import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from autospine_workbench.automation.sleeve_process_tree import SleeveProcessTree


class SleeveProcessTreeTests(unittest.TestCase):
    def test_gated_tree_stops_descendants_and_leaves_other_process_alive(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);script=root/'worker.py';heartbeat=root/'heartbeat'
            child="import pathlib,time; p=pathlib.Path(%r);\nwhile True: p.write_text(str(time.time())); time.sleep(.03)" % str(heartbeat)
            script.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",'+repr(child)+'])\ntime.sleep(30)')
            other=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
            try:
                with SleeveProcessTree([sys.executable,'-u',str(script)],stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,text=True) as tree:
                    time.sleep(.1);self.assertFalse(heartbeat.exists())
                    tree.release();deadline=time.monotonic()+5
                    while not heartbeat.exists() and time.monotonic()<deadline:time.sleep(.03)
                    self.assertTrue(heartbeat.exists())
                    tree.terminate();tree.process.wait(timeout=5)
                    time.sleep(.2);before=heartbeat.read_text();time.sleep(.15)
                    self.assertEqual(before,heartbeat.read_text())
                    self.assertIsNone(other.poll())
            finally:other.terminate();other.wait(timeout=5)

