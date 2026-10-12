"""Isolated, manifest-driven Godot validator. No candidate-provided verdict code is trusted."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,signal,subprocess,tempfile,time,uuid
from godot_limiter import limit_godot_validation, godot_slot_fds
RUNNER_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
EXCLUDE={'.git','.godot','__pycache__'}
def hashes(root):
 out={}
 for p in sorted(Path(root).rglob('*')):
  if any(x in EXCLUDE for x in p.relative_to(root).parts):continue
  if p.is_symlink():
   if not p.resolve().is_relative_to(Path(root).resolve()):raise ValueError('External symlink: '+str(p))
  if p.is_file():out[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
 return out
def digest(items):return hashlib.sha256(json.dumps(items,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(path,obj):Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
@limit_godot_validation
def validate(manifest,candidate,output,mode='full',render=False):
 manifest=Path(manifest).resolve();cfg=json.loads(manifest.read_text());candidate=Path(candidate).resolve();out=Path(output).resolve()
 if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be fresh or empty')
 out.mkdir(parents=True,exist_ok=True)
 source=hashes(candidate);nonce=uuid.uuid4().hex;execution=[];start=time.time();report={};status='ERROR';why=[]
 trusted={manifest.name:hashlib.sha256(manifest.read_bytes()).hexdigest()}
 required=cfg['baseline_checks'] if mode=='baseline' else cfg['checks']
 def launch(stage,cmd,timeout):
  began=time.monotonic();proc=subprocess.Popen(cmd,pass_fds=godot_slot_fds(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
  timed=False
  try:log=proc.communicate(timeout=timeout)[0]
  except subprocess.TimeoutExpired:
   timed=True;os.killpg(proc.pid,signal.SIGKILL);log=proc.communicate()[0]
  (out/(stage+'.log')).write_text(log)
  errors=[s for s in log.splitlines() if re.search(r'SCRIPT ERROR:|Parse Error:|ERROR:',s)]
  execution.append({'stage':stage,'command':cmd,'exit_code':proc.returncode,'timeout':timed,'errors':errors,'seconds':round(time.monotonic()-began,3)})
  return execution[-1]
 godot=os.environ.get('GODOT',cfg['godot_binary'])
 try:
  version=subprocess.check_output([godot,'--version'],pass_fds=godot_slot_fds(),text=True,timeout=15).strip()
  if version!=cfg['godot_version']:raise ValueError('Engine version mismatch: '+version)
  project=out/'project';shutil.copytree(candidate,project,ignore=lambda p,n:[v for v in n if v in EXCLUDE])
  private=project/'__assessment_private__'
  if private.exists():raise ValueError('Reserved validator directory in candidate')
  private.mkdir()
  for name,relative in cfg['files'].items():
   src=(manifest.parent/relative).resolve();trusted[relative]=hashlib.sha256(src.read_bytes()).hexdigest();shutil.copy2(src,private/name)
  imported=launch('import',[godot,'--headless','--path',str(project),'--import'],cfg['timeouts_seconds']['import'])
  if imported['timeout']:status='TIMEOUT';why=['import timeout']
  elif imported['exit_code']!=0 or imported['errors']:status='ERROR';why=['Import failed; inspect source versus environment before classification']
  else:
   cmd=[godot,'--verbose','--path',str(project),'--fixed-fps','60']
   if not render:cmd+=['--headless']
   else:cmd+=['--rendering-method','gl_compatibility','--audio-driver','Dummy']
   cmd+=['--script','res://__assessment_private__/test.gd','--','--mode='+mode,'--report='+str(out/'behavior.json'),'--capture='+str(out),'--nonce='+nonce]
   run=launch('validation',cmd,cfg['timeouts_seconds'].get('render_validation',cfg['timeouts_seconds']['validation']) if render else cfg['timeouts_seconds']['validation'])
   if run['timeout']:status='TIMEOUT';why=['validation timeout']
   elif run['errors']:status='ERROR';why=['Engine/test errors prevent reliable classification']
   else:
    report=json.loads((out/'behavior.json').read_text());checks=report.get('checks',[])
    ids=[c.get('check_id') for c in checks]
    if report.get('complete') is not True or report.get('nonce')!=nonce:raise ValueError('Missing completion or nonce mismatch')
    if len(ids)!=len(set(ids)) or set(ids)!=set(required):raise ValueError('Missing, duplicate or unexpected checks: '+str(set(required)^set(ids)))
    for c in checks:
     if c.get('status') not in ['PASS','FAIL','NOT_RUN']:raise ValueError('Invalid check status')
     c['R_ids']=required[c['check_id']]['R_ids']
    passed=all(c['status']=='PASS' for c in checks);failed=any(c['status']=='FAIL' for c in checks)
    if not passed and not failed:raise ValueError('Skipped checks without a diagnosed failure')
    if run['exit_code']!=(0 if passed else 1):raise ValueError('Exit code contradicts complete report')
    status='PASS' if passed else 'FAIL'
 except (ValueError,OSError,KeyError,subprocess.SubprocessError) as e:status='ERROR';why.append(str(e))
 # Canonical scripts must remain the injected bytes even if a candidate modifies its workspace.
 try:
  if 'private' in locals():
   for name,relative in cfg['files'].items():
    if hashlib.sha256((private/name).read_bytes()).hexdigest()!=trusted[relative]:
     status='ERROR';why.append('Injected grader changed: '+name)
 except OSError as e:status='ERROR';why.append('Injected grader missing: '+str(e))
 unchanged=source==hashes(candidate)
 if not unchanged:status='ERROR';why.append('Candidate source changed during validation')
 result={'task_id':cfg['task_id'],'spec_revision':cfg['spec_revision'],'validator_revision':cfg['validator_revision'],'candidate_digest':digest(source),'candidate_files':source,'status':status,'mode':mode,'checks':report.get('checks',[]),'execution':execution,'reason':why,'source_unchanged':unchanged,'grader_files':trusted,'runner_sha256':RUNNER_SHA256,'godot_version':cfg['godot_version'],'rendered':render,'nonce':nonce,'seconds':round(time.time()-start,3)}
 write(out/'result.json',result);return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--candidate',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--mode',choices=['full','baseline'],default='full');p.add_argument('--render',action='store_true');a=p.parse_args()
 r=validate(a.manifest,a.candidate,a.output_dir,a.mode,a.render);print(json.dumps({'task':r['task_id'],'status':r['status'],'failed':[c['check_id'] for c in r['checks'] if c['status']=='FAIL'],'reason':r['reason']}));raise SystemExit({'PASS':0,'FAIL':1,'ERROR':2,'TIMEOUT':3}[r['status']])
