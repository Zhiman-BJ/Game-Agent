import importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('prepare',ROOT/'scripts/prepare_batch.py');prepare=importlib.util.module_from_spec(s);s.loader.exec_module(prepare)
class Portability(unittest.TestCase):
 def test_prepare_relocated_work_order_and_pinned_source(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);repo=r/'source';repo.mkdir();(repo/'project.godot').write_text('config_version=5\n')
   for args in [['init','-q'],['add','.'],['-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','source']]:subprocess.run(['git','-C',str(repo),*args],check=True)
   sha=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
   godot=r/'fake-godot';godot.write_text('#!/bin/sh\necho 4.4.1.stable.official.49a5bc7b6\n');godot.chmod(0o700)
   cfg={'model':'test-model','reasoning_effort':'xhigh','godot_binary':str(godot),'codex_binary':'/usr/bin/true','private_root':str(r/'private'),'providers':{'provider_a':{'base_url':'http://127.0.0.1:18989/a/v1','proxy_token_file':str(r/'private/a.token')}},'sources':[{'repository_id':'test/game','source_repo':str(repo),'source_revision':sha,'candidate_count':2}]}
   p=r/'config.json';p.write_text(json.dumps(cfg));b=prepare.prepare(p,r/'new-batch');result=json.loads((b/'batch_config.json').read_text())
   self.assertEqual(len(result['lanes']),2);self.assertEqual(result['lanes'][1]['design_dependency_task_id'],'new-batch_0001');self.assertFalse((b/'preflight/approval.json').exists())
   check='import sys;sys.path.insert(0,"tools");from host import validate_config;import json;validate_config(json.load(open("batch_config.json")));from scheduler import BatchScheduler;BatchScheduler(json.load(open("batch_config.json")))'
   completed=subprocess.run([sys.executable,'-c',check],cwd=b,capture_output=True,text=True)
   self.assertEqual(completed.returncode,0,completed.stderr)
   launch=subprocess.run([sys.executable,str(b/'launch.py')],cwd=b,capture_output=True,text=True)
   self.assertNotEqual(launch.returncode,0)
   self.assertIn('Native provider preflight not complete',launch.stderr)
   self.assertFalse((b/'jobs').exists())
   with self.assertRaises(ValueError):prepare.prepare(p,b)
   cfg['sources'][0]['source_revision']='0'*40;p.write_text(json.dumps(cfg))
   with self.assertRaises(ValueError):prepare.prepare(p,r/'bad-batch')
if __name__=='__main__':unittest.main()
