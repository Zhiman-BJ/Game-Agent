"""Combine automated behavior with a separately produced, candidate-bound visual review."""
from pathlib import Path
import argparse,json,hashlib,sys
from runner import validate,hashes,digest,RUNNER_SHA256

def combine(behavior,receipt_path,visual_ids):
 out={'task_id':behavior['task_id'],'candidate_digest':behavior['candidate_digest'],'behavior_status':behavior['status'],'status':behavior['status'],'scope':'baseline' if behavior['mode']=='baseline' else 'complete_task','reason':list(behavior['reason'])}
 if behavior['status']!='PASS' or behavior['mode']=='baseline':return out
 if not receipt_path:out.update(status='ERROR',reason=['visual_review_required']);return out
 try:
  receipt_path=Path(receipt_path).resolve();v=json.loads(receipt_path.read_text());rendered=json.loads((receipt_path.parent/v['render_result']).read_text())
  for key in ['candidate_digest','grader_files','runner_sha256']:
   if rendered[key]!=behavior[key]:raise ValueError('Visual evidence uses different '+key)
  if not rendered.get('rendered') or rendered['status']!='PASS':raise ValueError('Rendered behavior run incomplete')
  if v['candidate_digest']!=behavior['candidate_digest']:raise ValueError('Visual receipt candidate mismatch')
  if not v.get('reviewer') or not v.get('method'):raise ValueError('Review provenance missing')
  checks=v['checks'];ids=[x['check_id'] for x in checks]
  if len(ids)!=len(set(ids)) or set(ids)!=set(visual_ids):raise ValueError('Incomplete visual checks')
  if any(x['status'] not in ['PASS','FAIL'] or not x.get('observation') for x in checks):raise ValueError('Invalid visual check')
  if not v['images']:raise ValueError('No rendered evidence')
  for i in v['images']:
   p=receipt_path.parent/i['path']
   if hashlib.sha256(p.read_bytes()).hexdigest()!=i['sha256']:raise ValueError('Image hash mismatch')
  out['status']='PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL';out['visual_checks']=checks;out['visual_receipt_sha256']=hashlib.sha256(receipt_path.read_bytes()).hexdigest()
 except (OSError,ValueError,KeyError,TypeError) as e:out.update(status='ERROR',reason=['invalid_visual_review: '+str(e)])
 return out

def main(manifest=None):
 p=argparse.ArgumentParser();p.add_argument('--manifest',default=str(manifest) if manifest else None,required=manifest is None);p.add_argument('--candidate',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--mode',choices=['full','baseline'],default='full');p.add_argument('--render',action='store_true');p.add_argument('--visual-review');p.add_argument('--combine-existing',action='store_true');a=p.parse_args()
 out=Path(a.output_dir)
 b=json.loads((out/'result.json').read_text()) if a.combine_existing else validate(a.manifest,a.candidate,out,a.mode,a.render)
 if digest(hashes(Path(a.candidate).resolve()))!=b['candidate_digest']:
  raise ValueError('Candidate differs from recorded behavior evidence')
 cfg=json.loads(Path(a.manifest).read_text());parent=Path(a.manifest).resolve().parent
 expected={Path(a.manifest).name:hashlib.sha256(Path(a.manifest).read_bytes()).hexdigest()}
 expected.update({rel:hashlib.sha256((parent/rel).resolve().read_bytes()).hexdigest() for rel in cfg['files'].values()})
 if b['grader_files']!=expected or b['runner_sha256']!=RUNNER_SHA256:
  raise ValueError('Behavior evidence uses an obsolete grader/runner')
 # Visual checklist is alongside the canonical validator, not supplied by a candidate.
 ids=json.loads(Path(a.manifest).with_name('visual_checklist.json').read_text())['checks']
 r=combine(b,a.visual_review,ids);(out/'final_result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False));return {'PASS':0,'FAIL':1,'ERROR':2,'TIMEOUT':3}[r['status']]
if __name__=='__main__':raise SystemExit(main())
