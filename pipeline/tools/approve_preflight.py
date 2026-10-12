"""Host verifies preserved native workload evidence, never accepts actor PASS alone."""
from pathlib import Path
import json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def events(p):return [json.loads(l) for l in p.read_text().splitlines() if l.startswith('{')]
def main():
 cfg=read(ROOT/'batch_config.json');records=[]
 for provider in cfg['providers']:
  k=provider.removeprefix('provider_')
  work=ROOT/'preflight'/f'{k}-01';first=read(work/'host_result.json');resumed=read(work/'resume_check/host_result.json')
  assert first['exit_code']==resumed['exit_code']==0
  assert first['receipt']['status']==resumed['receipt']['status']==resumed['resume_receipt']['status']=='PASS'
  original=events(work/'events.jsonl');continuation=events(work/'resume_check/events.jsonl')
  thread=[e['thread_id'] for e in original if e.get('type')=='thread.started']
  assert len(thread)==1 and [e['thread_id'] for e in continuation if e.get('type')=='thread.started']==thread
  assert resumed['thread_id']==thread[0]
  for es in [original,continuation]:
   assert any(e['type']=='turn.completed' for e in es) and not any(e['type']=='turn.failed' for e in es)
  assert read(work/'project/probe_result.json')['native_input_consumed'] is True
  assert resumed['resume_receipt']['network_namespace_available'] is True
  home=Path(cfg['private_root'])/'sessions'/f'preflight-{k}-01'
  native=[(p,events(p)) for p in home.glob('sessions/**/*.jsonl')]
  calls=[e['payload'] for _,es in native for e in es if e.get('payload',{}).get('name')=='view_image']
  viewed=[json.loads(e['arguments'])['path'] for e in calls]
  images={}
  for name in ['before.png','after.png']:
   path=work/'project'/name
   assert viewed.count(str(path))>=2, 'Both initial and resumed image calls required'
   assert path.read_bytes().startswith(b'\x89PNG')
   images[name]=hashlib.sha256(path.read_bytes()).hexdigest()
  assert images['before.png']!=images['after.png']
  records.append({'provider':k,'status':'PASS','thread_id':thread[0],'same_thread_resume':True,'native_input_consumed':True,'network_namespace_available':True,'image_view_calls':len(calls),'image_sha256':images,'host_result':str(work/'host_result.json'),'resume_host_result':str(work/'resume_check/host_result.json'),'native_event_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p,_ in native}})
 out={'status':'PASS','checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'providers':records,'scope':'Actual native shell, engine/import, graphical probe/input, image calls and same-thread continuation. No guarantee of future provider availability or task acceptance.'}
 (ROOT/'preflight/approval.json').write_text(json.dumps(out,indent=2)+'\n');print('HOST_PREFLIGHT_PASS',','.join(r['provider'] for r in records))
if __name__=='__main__':main()
