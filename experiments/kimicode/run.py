#!/usr/bin/env python3
"""Solve exported public projects in Bubblewrap; never mount references or graders."""
import argparse,collections,concurrent.futures,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'third_party/gamedevbench'))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def one(args,tid):
 out=args.output/tid;out.mkdir(parents=True,exist_ok=False)
 src=args.dataset/'tasks'/tid;workspace=out/'workspace'
 shutil.copytree(src/'start',workspace,ignore=shutil.ignore_patterns('.git','.godot','__pycache__'))
 instruction=(src/'instruction.md').read_text();cfg=workspace/'task_config.json';data=json.loads(cfg.read_text()) if cfg.exists() else {};data.update(task_id=tid,instruction=instruction);dump(cfg,data)
 hashes={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest() for p in workspace.rglob('*') if p.is_file()};dump(out/'input_hashes.json',hashes)
 # One process per solve isolates the provider proxy override and model environment.
 command=[sys.executable,__file__,'--dataset',str(args.dataset),'--output',str(args.output),'--model',args.model,'--family',args.family,'--godot',args.godot,'--kimi',args.kimi,'--timeout',str(args.timeout),'--worker',tid]
 with (out/'worker.log').open('w') as log:r=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=args.timeout+180)
 return {'id':tid,'worker_exit':r.returncode}
def worker(a):
 from gamedevbench.src import confinement
 from model_proxy import ModelProxy
 out=a.output/a.worker;key=os.environ.pop('SOLVER_API_KEY');url=os.environ.pop('SOLVER_BASE_URL')
 os.environ.update(K3_API_KEY='host-proxy-placeholder',K3_BASE_URL='http://model.local/v1',GAMEDEVBENCH_KIMI_CLI=a.kimi,KIMI_SESSION_ATTEMPTS='1',GODOT_EXEC_PATH=a.godot,CUDA_VISIBLE_DEVICES='',NVIDIA_VISIBLE_DEVICES='void')
 confinement.ProviderProxy=lambda socket_path,allowed_hosts:ModelProxy(socket_path,allowed_hosts,credential=key,model=a.model,upstream=url,family=a.family,evidence=out/'provider')
 r=confinement.run_confined_solver(workspace=out/'workspace',agent='kimi-code',model=a.model,debug=False,use_mcp=False,timeout_seconds=a.timeout,use_runtime_video=False,effort=None,godot_path=a.godot,additional_provider_hosts=['model.local'],checkpoint_dir=out/'checkpoint')
 dump(out/'solver_result.json',r.result.to_dict());dump(out/'confinement.json',r.metadata);(out/'wire.jsonl').write_text(r.result.stdout)
 counts=collections.Counter()
 for line in r.result.stdout.splitlines():
  try:e=json.loads(line)
  except ValueError:continue
  if e.get('method')=='event':counts[(e.get('params') or {}).get('type','unknown')]+=1
 dump(out/'trajectory_counts.json',dict(counts))
 return 0 if r.result.success else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--tasks',nargs='+');p.add_argument('--model',required=True);p.add_argument('--family',choices=['k3','qwen'],default='k3');p.add_argument('--godot',required=True);p.add_argument('--kimi',required=True);p.add_argument('--parallel',type=int,default=1);p.add_argument('--timeout',type=int,default=7200);p.add_argument('--worker');a=p.parse_args();a.dataset=a.dataset.resolve();a.output=a.output.resolve()
 if a.worker:raise SystemExit(worker(a))
 if not a.tasks or not 1<=a.parallel<=64:p.error('Specify tasks and parallel 1..64')
 known={x['id'] for x in json.loads((a.dataset/'catalog.json').read_text())['tasks']}
 if len(a.tasks)!=len(set(a.tasks)) or not set(a.tasks)<=known:p.error('Unknown or duplicate task IDs')
 if not os.environ.get('SOLVER_API_KEY') or not os.environ.get('SOLVER_BASE_URL'):p.error('Set SOLVER_API_KEY and SOLVER_BASE_URL')
 if sys.platform!='linux' or not shutil.which('bwrap'):p.error('Linux and Bubblewrap required')
 a.output.mkdir(parents=True,exist_ok=False)
 dump(a.output/'protocol.json',{'tasks':a.tasks,'model':a.model,'agent':'kimi-code','attempts':1,'parallel':a.parallel,'timeout_seconds':a.timeout,'evaluation':'Separate canonical validator; solver success is not task PASS'})
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.parallel) as pool:
  results=list(pool.map(lambda t:one(a,t),a.tasks))
 dump(a.output/'summary.json',results)
