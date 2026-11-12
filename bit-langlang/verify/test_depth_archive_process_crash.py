import json
import select
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .depth_event_archive import inspect


CHILD='''
import os,signal,sys
from pathlib import Path
import verify.depth_event_archive as a
root=Path(sys.argv[1]);mode=sys.argv[2];a.init(root);w=a.NewSessionWriter(root)
w.append("first","2026-10-30T00:00:00Z");w.append("second","2026-10-30T00:00:01Z")
if mode=="partial":
    def interrupted(path,raw):
        with open(path,"xb") as f:
            f.write(raw[:20]);f.flush();os.fsync(f.fileno())
        print("READY",flush=True);signal.pause()
    a.write_new=interrupted
    w.append("third","2026-10-30T00:00:02Z")
else:
    w.append("third","2026-10-30T00:00:02Z")
    print("READY",flush=True);signal.pause()
'''


class ArchiveProcessCrashTests(unittest.TestCase):
    def test_killed_after_durable_record_and_during_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mode in ('unsealed','partial'):
                root=Path(tmp)/mode
                proc=subprocess.Popen([sys.executable,'-c',CHILD,str(root),mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    ready,_,_=select.select([proc.stdout],[],[],10)
                    self.assertTrue(ready,'test child did not reach interruption point')
                    self.assertEqual(proc.stdout.readline().strip(),'READY')
                finally:
                    if proc.poll() is None:proc.kill()
                    proc.communicate(timeout=10)
                self.assertNotEqual(proc.returncode,0)
                result=inspect(root)
                if mode=='unsealed':
                    self.assertEqual(result['status'],'INCOMPLETE_UNSEALED',result)
                    self.assertEqual([x['wire_text'] for x in result['records']],['first','second','third'])
                else:
                    self.assertEqual(result['status'],'INVALID',result)
                    self.assertEqual(result['valid_prefix'],2)
                    self.assertEqual([x['wire_text'] for x in result['records']],['first','second'])
                self.assertFalse((root/'seal.json').exists())


if __name__=='__main__':unittest.main()
