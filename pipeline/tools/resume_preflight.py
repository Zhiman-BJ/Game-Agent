from pathlib import Path
import argparse,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import host
from construction import TaskConstructor
p=argparse.ArgumentParser();p.add_argument('--provider',required=True);p.add_argument('--attempt',type=int,default=1);a=p.parse_args()
cfg=host.read(ROOT/'batch_config.json');work=ROOT/'preflight'/f'{a.provider}-{a.attempt:02d}';job=work/'resume_check';job.mkdir(exist_ok=False)
events=[json.loads(l) for l in (work/'events.jsonl').read_text().splitlines() if l.startswith('{')];thread=next(e['thread_id'] for e in events if e.get('type')=='thread.started')
h=TaskConstructor.__new__(TaskConstructor);h.cfg=cfg
env=h.actor_environment({'task_id':'preflight-'+a.provider,'run_root':str(work),'provider':'provider_'+a.provider})
env['CODEX_HOME']=str(Path(cfg['private_root'])/'sessions'/f'preflight-{a.provider}-{a.attempt:02d}')
with (job/'display.txt').open('w') as out,(job/'xvfb.log').open('w') as err:xvfb=subprocess.Popen(['Xvfb','-displayfd','1','-screen','0','640x480x24','-nolisten','tcp'],stdout=out,stderr=err,env=env,start_new_session=True)
try:
 for _ in range(100):
  if (job/'display.txt').read_text().strip():break
  time.sleep(.1)
 env['DISPLAY']=':'+(job/'display.txt').read_text().strip()
 prompt='''Resume this exact native preflight thread; previous logs/evidence are preserved. The host has created the shared Godot slot directory on THIS host. Upstream503/500 were transport failures, not game failures. Finish the existing preflight now: use Python/file tools, PATH=/usr/bin:/bin:/usr/sbin:/sbin and login:false. Use $GODOT wrapper. If prior probe did not complete, import and execute original supplied probe.gd with GL Compatibility and --audio-driver Dummy under current DISPLAY, with finite timeout120s. Do not change probe.gd/project to force success. Inspect probe_result.json, then actually view both before.png/after.png via view_image. Existing complete image evidence may be inspected without rerender. Write preflight_receipt.json PASS only if required actual checks succeed, including real native input and images. Also test `timeout10s unshare -Urn /bin/sh -c 'ip link set lo up && python3 -c "import socket; s=socket.socket(); s.bind((\\\"127.0.0.1\\\",0)); print(\\\"NETWORK_NAMESPACE_OK\\\")"'` or an equivalent correct Python subprocess argv; record network_namespace_available truthfully in resume_receipt.json (failure does not invalidate other checks). Write resume_receipt.json with observed marker reuse, native_input_consumed, viewed_images and no credentials. Then stop.'''
 (job/'prompt.txt').write_text(prompt)
 argv=host.command(cfg,cfg['providers']['provider_'+a.provider],work,job);argv.insert(2,'resume');i=argv.index('-C');del argv[i:i+2];argv[-1:]=[thread,'-'];argv[3:3]=['-c','shell_environment_policy.set.PATH="/usr/bin:/bin:/usr/sbin:/sbin"']
 with (job/'prompt.txt').open() as inp,(job/'events.jsonl').open('w') as out,(job/'stderr.log').open('w') as err:
  proc=subprocess.Popen(argv,cwd=work,env=env,stdin=inp,stdout=out,stderr=err,start_new_session=True)
  try:rc=proc.wait(timeout=900)
  except subprocess.TimeoutExpired:host.terminate(proc);rc=124
 host.dump(job/'host_result.json',{'exit_code':rc,'thread_id':thread,'receipt':host.read(work/'preflight_receipt.json'),'resume_receipt':host.read(work/'resume_receipt.json'),'argv':argv})
 print(a.provider,rc,flush=True)
finally:host.terminate(xvfb)
