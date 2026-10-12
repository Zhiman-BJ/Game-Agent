#!/usr/bin/env python3
"""Fail-closed artifact qualification. Human semantics/visual review remain explicit evidence."""
from pathlib import Path
import json,hashlib,sys,argparse,datetime
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
from runner import hashes,digest
from grade import combine

def audit_result(record, manifest, mode, expected, behavior):
 """Check recorded runner protocol; this does not establish semantic test validity."""
 errors=[]
 def require(ok,msg):
  if not ok:errors.append(msg)
 require(record.get('mode')==mode,'wrong mode')
 require(record.get('status')==expected,'expected '+expected)
 for field in ('task_id','spec_revision','validator_revision','godot_version'):
  require(record.get(field)==manifest.get(field),'mismatched '+field)
 required=manifest['baseline_checks'] if mode=='baseline' else manifest['checks']
 checks=record['checks'];ids=[c['check_id'] for c in checks]
 require(bool(required),'empty required checks')
 require(len(ids)==len(set(ids)) and set(ids)==set(required),'missing, duplicate or unexpected checks')
 for check in checks:
  require(check.get('status') in ('PASS','FAIL','NOT_RUN'),'invalid check status')
  if check['check_id'] in required:
   require(set(check.get('R_ids',[]))==set(required[check['check_id']]['R_ids']),'check requirement mapping differs from manifest')
 if expected=='PASS':require(all(c.get('status')=='PASS' for c in checks),'PASS has failed/skipped checks')
 if expected=='FAIL':require(any(c.get('status')=='FAIL' for c in checks),'FAIL has no failed check')
 execution=record['execution'];stages=[e.get('stage') for e in execution]
 require(stages==['import','validation'],'incomplete or duplicate execution stages')
 for entry in execution:
  require(bool(entry.get('command')),'missing execution command')
  require(entry.get('timeout') is False and entry.get('errors')==[],'execution error')
  code=0 if entry.get('stage')=='import' or expected=='PASS' else 1
  require(type(entry.get('exit_code')) is int and entry['exit_code']==code,'execution exit code contradicts result')
 nonce=behavior.get('nonce')
 require(behavior.get('complete') is True and isinstance(nonce,str) and bool(nonce),'missing completion or execution nonce')
 if 'nonce' in record:require(record['nonce']==nonce,'result/behavior nonce mismatch')
 raw=[(c.get('check_id'),c.get('status')) for c in behavior.get('checks',[])]
 require(raw==[(c.get('check_id'),c.get('status')) for c in checks],'result/behavior checks mismatch')
 validation=[e for e in execution if e.get('stage')=='validation']
 if validation:
  require('--nonce='+str(nonce) in validation[0].get('command',[]),'execution command nonce mismatch')
  require('--mode='+mode in validation[0].get('command',[]),'execution command mode mismatch')
 return errors,nonce

def current(run,tid):
 v=run/'validators'/tid;m=json.loads((v/'validator_manifest.json').read_text());runtime=(v/m['files']['base.gd']).resolve().parent
 grader={p:hashlib.sha256((v/r).resolve().read_bytes()).hexdigest() for p,r in [(v.joinpath('validator_manifest.json').name,'validator_manifest.json')]+[(r,r) for r in m['files'].values()]}
 return {'start':digest(hashes(run/'tasks'/tid)),'reference':digest(hashes(run/'tasks_gt'/tid)),'grader':grader,'runner':hashlib.sha256((runtime/'runner.py').read_bytes()).hexdigest(),'entry':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [v/'validate.py',v/'visual_checklist.json',runtime/'grade.py']},'spec':hashlib.sha256((run/'private'/tid/'task_spec.json').read_bytes()).hexdigest(),'contracts':{str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [run/'run_context.json',run/'candidate_registry.json',run/'repo_analysis.md']+[run/'private'/tid/n for n in ['coverage.json','provenance.json','design_report.md','construction_report.md']]}}
def gate(run,tid,require_review=True):
 run=Path(run).resolve();private=run/'private'/tid;errors=[]
 def require(ok,msg):
  if not ok:errors.append(msg)
 try:
  fp=current(run,tid);spec=json.loads((private/'task_spec.json').read_text());q=json.loads((private/'qualification.json').read_text());cfg=json.loads((run/'tasks'/tid/'task_config.json').read_text());m=json.loads((run/'validators'/tid/'validator_manifest.json').read_text());coverage=json.loads((private/'coverage.json').read_text())
  require(set(cfg)=={'task_id','name','instruction'} and cfg['task_id']==tid,'public config contract')
  require(spec['schema_version']==3 and spec['design_status']=='DESIGN_READY','spec readiness')
  targets={x['id'] for x in spec['requirements'] if x['kind']=='target'};allids={x['id'] for x in spec['requirements']}
  require({x['R_id'] for x in coverage['requirements']}==allids,'coverage missing requirements')
  require(all(c['R_ids'] and set(c['R_ids'])<=allids for group in ('checks','baseline_checks') for c in m[group].values()),'unmapped check')
  require(set(m['baseline_checks'])<=set(m['checks']),'baseline checks not in full checks')
  require(all(set(c['R_ids'])==set(m['checks'][cid]['R_ids']) for cid,c in m['baseline_checks'].items() if cid in m['checks']),'baseline/full requirement mappings differ')
  if 'required_check_ids' in m:require(set(m['required_check_ids'])==set(m['checks']),'manifest required_check_ids differ from checks')
  for tree in [run/'tasks'/tid,run/'tasks_gt'/tid]:
   require(not any(p.is_symlink() or '.git' in p.relative_to(tree).parts or p.suffix in ['.tmp','.bak'] for p in tree.rglob('*')),'unsafe public/reference file')
  def result(path,kind,expected,mode='full'):
   evidence=(run/path).resolve()
   if not evidence.is_relative_to(run):raise ValueError('Evidence path outside run: '+path)
   r=json.loads(evidence.read_text());behavior=json.loads(evidence.with_name('behavior.json').read_text())
   issues,nonce=audit_result(r,m,mode,expected,behavior)
   for issue in issues:require(False,path+': '+issue)
   require(r['source_unchanged'] and r['runner_sha256']==fp['runner'] and r['grader_files']==fp['grader'],path+': stale grader/runner')
   if kind in ['start','reference']:require(r['candidate_digest']==fp[kind],path+': stale candidate')
   return r,nonce
  for name,kind,status in [('reference','reference','PASS'),('start_baseline','start','PASS'),('start_full','start','FAIL')]:
   items=q.get(name,[]);require(len(items)>=3,name+': fewer than three final stability runs')
   require(len({str((run/path).resolve()) for path in items})==len(items),name+': repeated evidence paths')
   nonces=[]
   for path in items:
    r,nonce=result(path,kind,status,'baseline' if name=='start_baseline' else 'full');nonces.append(nonce)
    if name=='start_full':require(any(c['status']=='FAIL' and set(c['R_ids'])&targets for c in r['checks']),path+': no target gap failure')
   require(len(set(nonces))==len(nonces),name+': repeated execution nonce')
  covered=set();legal=0
  for c in json.loads((private/'controls.json').read_text()):
   require(c['kind'] in ('legal','negative'),c['name']+': unknown control kind')
   r,_=result(c['run'],'control','PASS' if c['kind']=='legal' else 'FAIL')
   require(r['candidate_digest']==c['candidate_digest'] and c['source_reference_digest']==fp['reference'],c['name']+': stale control')
   if c['kind']=='negative':
    failed={x['check_id'] for x in r['checks'] if x['status']=='FAIL'};expected=set(c['expected_failed_checks'])
    declared=set(c['R_ids']);require(bool(declared) and declared<=allids,c['name']+': invalid negative requirement IDs')
    require(bool(expected) and expected<=set(m['checks']),c['name']+': invalid expected failed checks')
    require(bool(failed&expected),c['name']+': intended defect not detected')
    detected={rid for cid in failed&expected if cid in m['checks'] for rid in m['checks'][cid]['R_ids']}
    require(declared<=detected,c['name']+': declared requirements without attributed failures: '+str(sorted(declared-detected)))
    covered.update(declared&detected)
   else:legal+=1
  require(allids<=covered,'target/preserved requirements lacking effective controls: '+str(sorted(allids-covered)));require(legal>=1,'missing substantive legal control')
  visual=json.loads((private/'visual_review.json').read_text());require(visual['status']=='PASS' and visual['reference_digest']==fp['reference'],'missing/stale visual review')
  require(bool(visual['images']), 'empty visual review')
  receipt=run/visual['receipt']
  rendered,_=result(visual['render_result'],'reference','PASS')
  combined=combine(rendered,receipt,json.loads((run/'validators'/tid/'visual_checklist.json').read_text())['checks'])
  require(combined['status']=='PASS','visual aggregation failed: '+str(combined.get('reason')))
  for x in visual['images']:require((run/x['path']).is_file() and hashlib.sha256((run/x['path']).read_bytes()).hexdigest()==x['sha256'],'missing/changed image')
  if require_review:
   review=json.loads((private/'review_report.json').read_text());require(review['status']=='ACCEPTED' and review['fresh_context'] is True,'independent review not accepted')
   require(review['fingerprints']==fp,'stale review inputs');require(not any(str(x.get('resolution','')).strip().lower()!='resolved' and str(x.get('severity','')).strip().lower() in ['blocker','major'] for x in review['findings']),'unresolved findings')
 except (OSError,ValueError,KeyError,TypeError) as e:errors.append(str(e))
 return {'task_id':tid,'status':'ACCEPTED' if not errors else 'NOT_QUALIFIED','errors':errors,'fingerprints':fp if 'fp' in locals() else {}}
def freeze(run,tid,result):
 run=Path(run).resolve();private=run/'private'/tid;files=set()
 for folder in [run/'tasks'/tid,run/'tasks_gt'/tid,run/'validators'/tid]:
  files.update(p for p in folder.rglob('*') if p.is_file() and '.godot' not in p.parts and '__pycache__' not in p.parts)
 for name in ['run_context.json','candidate_registry.json','repo_analysis.md']:files.add(run/name)
 # Fresh direct-construction tasks may have no legacy shared-preparation record.
 # The release inventory records it when present; task qualification does not
 # depend on an absent legacy file.
 if (run/'preparation.json').is_file():files.add(run/'preparation.json')
 if (ROOT/'existing_task_registry.json').exists():files.add(ROOT/'existing_task_registry.json')
 for name in ['task_spec.json','coverage.json','provenance.json','design_report.md','construction_report.md','qualification.json','controls.json','visual_review.json','review_report.json','review_report.md']:files.add(private/name)
 # The public-contract gate already checks visual_review's referenced receipt.
 # Older pipeline bookkeeping files are frozen if they exist, never fabricated.
 for name in ['visual_receipt.json','rebuild_bundle.json']:
  if (private/name).is_file():files.add(private/name)
 for name in ['rebuild.py','qualification.py','control_definitions.py']:
  if (ROOT/'tools'/name).exists():files.add(ROOT/'tools'/name)
 q=json.loads((private/'qualification.json').read_text());evidence=[run/x for items in q.values() if isinstance(items,list) for x in items]
 evidence += [run/x['run'] for x in json.loads((private/'controls.json').read_text())]
 visual=json.loads((private/'visual_review.json').read_text());evidence.append(run/visual['render_result'])
 for e in evidence:files.update(p for p in e.parent.iterdir() if p.is_file())
 for folder in [ROOT/'runtime',ROOT/'pipeline_tools',ROOT/'skill_snapshot',ROOT/'skills/godot-task-construction', ROOT/('prompts' if (ROOT/'prompts').exists() else 'pipeline')]:
  if folder.exists():files.update(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
 result.update(release_revision=1,frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventory_root='pipeline root containing runtime, pipeline_tools and runs',exclusions=['.godot','__pycache__','isolated copied execution projects','unused historical development evidence','mutable control project copies; mutations and run digests are preserved'])
 result['files']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
 result['public_export_files']=hashes(run/'tasks'/tid)
 (private/'release_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run-root',required=True);p.add_argument('--task',required=True);p.add_argument('--pre-review',action='store_true');p.add_argument('--freeze',action='store_true');a=p.parse_args();r=gate(a.run_root,a.task,not a.pre_review)
 if a.freeze:
  if a.pre_review:raise SystemExit('Cannot freeze without independent review')
  if r['status']=='ACCEPTED':r=freeze(a.run_root,a.task,r)
 print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(0 if r['status']=='ACCEPTED' else 1)
