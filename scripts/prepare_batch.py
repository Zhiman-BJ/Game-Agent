#!/usr/bin/env python3
"""Allocate pinned repositories once and materialize an isolated Scale work order."""
import argparse,json,os,re,shutil,subprocess
from pathlib import Path
TEMPLATE=Path(__file__).resolve().parents[1]/'pipeline'
def dump(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def prepare(config_path,output):
 config_path=Path(config_path).resolve();cfg=json.loads(config_path.read_text());output=Path(output).resolve()
 if output.exists():raise ValueError('Output must be a new directory')
 for key in ['model','reasoning_effort','godot_binary','codex_binary','providers','sources']:
  if not cfg.get(key):raise ValueError('Missing '+key)
 for key in ['godot_binary','codex_binary']:
  cfg[key]=str(Path(os.path.expandvars(cfg[key])).expanduser().resolve())
  if not Path(cfg[key]).is_file():raise ValueError('Missing executable: '+key)
 version=subprocess.check_output([cfg['godot_binary'],'--version'],text=True,timeout=20).strip()
 if version!='4.4.1.stable.official.49a5bc7b6':raise ValueError('Requires Godot 4.4.1: '+version)
 sources=cfg.pop('sources');repos=set()
 for s in sources:
  if s['repository_id'] in repos:raise ValueError('Duplicate repository allocation')
  repos.add(s['repository_id']);s['source_repo']=str(Path(os.path.expandvars(s['source_repo'])).expanduser().resolve())
  head=subprocess.check_output(['git','-C',s['source_repo'],'rev-parse','HEAD'],text=True).strip()
  if head!=s['source_revision']:raise ValueError('Pinned revision mismatch')
  if subprocess.check_output(['git','-C',s['source_repo'],'status','--porcelain'],text=True).strip():raise ValueError('Source must be clean')
  if not 1<=s['candidate_count']<=10:raise ValueError('Candidate count must be 1..10; quota is not quality')
  if not (Path(s['source_repo'])/s.get('project_subdir','.')/'project.godot').is_file():raise ValueError('Missing selected Godot project')
 if sum(s['candidate_count'] for s in sources)>128:raise ValueError('At most 128 candidates per work order')
 providers=cfg['providers'];cap=int(cfg.get('api_concurrency_per_provider',16))
 if not 1<=cap<=64:raise ValueError('Provider cap must be 1..64')
 for key,p in providers.items():
  if not re.fullmatch(r'provider_[abc]',key):raise ValueError('Invalid provider name')
  if not re.fullmatch(r'http://127\.0\.0\.1:\d+/[A-Za-z0-9_-]+/v1/?',p['base_url']):raise ValueError('Use host-owned local relay endpoint')
  p['proxy_token_file']=str(Path(os.path.expandvars(p['proxy_token_file'])).expanduser().resolve())
  p.update(initial_concurrency=cap,max_concurrency=cap)
 shutil.copytree(TEMPLATE,output,ignore=shutil.ignore_patterns('__pycache__'))
 defaults=dict(max_transport_retries=2,max_checkpoint_resume_attempts=1,max_revision_rounds=10,max_pre_gate_repairs=10,host_verify_timeout_seconds=600,native_worker_threads=2,render_worker_threads=2,author_turn_timeout_seconds=14400,author_max_turns=12,review_max_rounds=6,review_concurrency=4,review_infra_retries=1,godot_slots=32,stage_timeout_seconds={'design':7200,'construction':14400,'review':7200})
 cfg={**defaults,**cfg};cfg.update(batch_id=output.name,skill_path=str(output/'skills/godot-task-construction'),api_concurrency_per_provider=cap,private_root=str(Path(os.path.expandvars(cfg['private_root'])).expanduser().resolve()),source_claim_root=str(output/'planning/source_claims'),repository_brief_root=str(output/'planning/repository_briefs'),shared_admission_root=str(output/'admission'),godot_slot_dir=str(output/'godot_slots'),library_path=cfg.get('library_path',''))
 lanes=[]
 for s in sources:
  prefix=cfg.get('task_prefix',re.sub(r'[^A-Za-z0-9_-]','_',output.name))
  if not re.fullmatch(r'[A-Za-z0-9_-]+',prefix):raise ValueError('Invalid task_prefix')
  ids=[f'{prefix}_{len(lanes)+i+1:04d}' for i in range(s['candidate_count'])]
  brief=output/'planning/repository_briefs'/(s['repository_id'].replace('/','__')+'.json')
  dump(brief,{**s,'task_ids':ids,'historical_goals':s.get('historical_goals',[]),'benchmark_goals':s.get('benchmark_goals',[]),'runtime_evidence':'NOT_RUN; author must exercise actual gameplay','feature_candidates':s.get('feature_candidates',[])})
  for slot,tid in enumerate(ids,1):
   run=output/'runs'/tid;run.mkdir(parents=True)
   lane=dict(task_id=tid,provider=list(providers)[len(lanes)%len(providers)],repository_id=s['repository_id'],source_repo=s['source_repo'],source_revision=s['source_revision'],project_subdir=s.get('project_subdir','.'),source_slot=slot,source_task_count=len(ids),max_tasks=1,runtime_evidence_level='NOT_RUN',design_dependency_task_id=ids[slot-2] if slot>1 else None,sibling_task_ids=ids,run_root=str(run),context=str(run/'run_context.json'))
   ctx={**lane,'run_id':output.name+'__'+tid,'upstream_root':None,'godot_binary':cfg['godot_binary'],'godot_version':version,'runtime_profile':'Linux; software rendering; private Xvfb; process-level Godot slots','instruction_language':cfg.get('instruction_language','en'),'timeouts_seconds':{'import':120,'smoke':60,'validation':120,'render_validation':360},'stability_runs':3,'max_revision_rounds':cfg['max_revision_rounds'],'existing_task_registry':str(output/'existing_task_registry.json'),'quality_profile':str(output/'skills/godot-task-construction/references/quality-baseline.md'),'validation_runner':str(output/'runtime/runner.py'),'validation_grade':str(output/'runtime/grade.py'),'validation_gate_contract':str(output/'pipeline_tools/BATCH_GATE_CONTRACT.md'),'project_template':None,'difficulty_calibration':'NOT_RUN','teacher_trajectories':'NOT_COLLECTED','source_summary':str(brief)}
   dump(run/'run_context.json',ctx);(run/'DIRECT_CONTEXT.md').write_text(f'Construct one complete feature in this run only. Read run_context.json, {brief}, and {output}/prompts/README.md. Exercise pinned upstream gameplay; prefer verified feature ablation, otherwise justify an extension. Do not force the repository quota.\n');lanes.append(lane)
 cfg.update(lanes=lanes,initial_candidate_count=len(lanes),target_qualified_tasks=len(lanes))
 dump(output/'batch_config.json',cfg);dump(output/'control.json',{'pause_new':False,'providers':{k:{'concurrency':cap} for k in providers}})
 dump(output/'execution_scope.json',{'schema_version':1,'mode':'allowlist','selected_task_ids':[x['task_id'] for x in lanes],'deferred_task_ids':[],'retained_accepted_task_ids':[]})
 dump(output/'selection_notes.json',{x['task_id']:{'basis':'Explicit source allocation; independent task quality still required'} for x in lanes});dump(output/'existing_task_registry.json',{'entries':cfg.pop('historical_tasks',[])})
 (output/'planning/source_claims').mkdir();print(json.dumps({'batch':str(output),'candidates':len(lanes),'providers':len(providers),'model_requests':0}))
 return output
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args();prepare(a.config,a.output)
