#!/usr/bin/env python3
"""Finite native Codex + Godot integration check, with no upstream credentials."""
from pathlib import Path
import argparse,datetime,json,os,signal,subprocess,time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host_tools'))
from actor_permissions import actor_permission_args

ROOT=Path(__file__).resolve().parents[1]
GODOT=None

def main():
 p=argparse.ArgumentParser();p.add_argument('--provider',choices=['a','b','c'],required=True);p.add_argument('--attempt',type=int,default=1);p.add_argument('--timeout',type=int,default=900);a=p.parse_args()
 cfg=json.loads((ROOT/'batch_config.json').read_text());GODOT=cfg['godot_binary']
 work=ROOT/'preflight'/f'{a.provider}-{a.attempt:02d}';work.mkdir(parents=True,exist_ok=False)
 project=work/'project';project.mkdir()
 (project/'project.godot').write_text('config_version=5\n[application]\nconfig/name="Harness Probe"\n[display]\nwindow/size/viewport_width=320\nwindow/size/viewport_height=240\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
 (project/'probe.gd').write_text('''extends SceneTree
class Board extends Node2D:
 var clicked=false
 func _input(event):
  if event is InputEventMouseButton and event.pressed:
   clicked=true
   queue_redraw()
 func _draw():
  draw_rect(Rect2(40,40,120,100),Color.GREEN if clicked else Color.BLUE)
func _initialize():
 call_deferred("run_probe")
func run_probe():
 var board=Board.new()
 root.add_child(board)
 for i in range(5): await process_frame
 await RenderingServer.frame_post_draw
 root.get_texture().get_image().save_png("res://before.png")
 var click=InputEventMouseButton.new()
 click.button_index=MOUSE_BUTTON_LEFT
 click.pressed=true
 click.position=Vector2(80,80)
 Input.parse_input_event(click)
 Input.flush_buffered_events()
 for i in range(3): await process_frame
 await RenderingServer.frame_post_draw
 root.get_texture().get_image().save_png("res://after.png")
 var f=FileAccess.open("res://probe_result.json",FileAccess.WRITE)
 f.store_string(JSON.stringify({"native_input_consumed":board.clicked}))
 f.close()
 board.queue_free()
 await process_frame
 quit(0 if board==null or not is_instance_valid(board) else 0)
''')
 home=Path(cfg['private_root'])/'sessions'/f'preflight-{a.provider}-{a.attempt:02d}';home.mkdir(parents=True,exist_ok=False,mode=0o700)
 env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ['API_KEY','API_TOKEN','SECRET','AUTH_TOKEN'])}
 env.update(CODEX_HOME=str(home),CODEX_PROXY_TOKEN=(Path(cfg['private_root'])/(a.provider+'.token')).read_text().strip(),GODOT=GODOT,LIBGL_ALWAYS_SOFTWARE='1',PYTHONDONTWRITEBYTECODE='1',LD_LIBRARY_PATH=json.loads((ROOT/'batch_config.json').read_text())['library_path'],OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
 for k,v in [('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('TMPDIR','tmp')]:
  d=work/'.runtime_home'/v;d.mkdir(parents=True,exist_ok=True);env[k]=str(d)
 env.update(GODOT=str(ROOT/'runtime/godot_wrapper.py'),DIRECT82_REAL_GODOT=GODOT,DIRECT82_GODOT_SLOT_DIR=cfg['godot_slot_dir'],DIRECT82_GODOT_SLOTS=str(cfg['godot_slots']),DIRECT82_NET_ISOLATION='1',DIRECT82_GODOT_LANE='preflight-'+a.provider,TOKIO_WORKER_THREADS='2',LP_NUM_THREADS='2')
 display=work/'display.txt'
 with display.open('w') as o,(work/'xvfb.log').open('w') as e:
  xvfb=subprocess.Popen(['Xvfb','-displayfd','1','-screen','0','640x480x24','-nolisten','tcp'],stdout=o,stderr=e,start_new_session=True)
 try:
  for _ in range(100):
   if display.read_text().strip():break
   if xvfb.poll() is not None:raise RuntimeError('Xvfb failed')
   time.sleep(.1)
  env['DISPLAY']=':'+display.read_text().strip()
  prompt=f'''This is a finite infrastructure preflight, not task generation. Work only in {work}.
Use Python for file listing and inspection; an unavailable rg convenience binary is not an engine failure and may be replaced by Python. Explicitly use PATH=/usr/bin:/bin:/usr/sbin:/sbin for shell tools to avoid inaccessible session-private shims. Use shell tools to write/read a small marker file, run the pinned Godot version, import {project} headlessly, then run its supplied probe.gd with the configured DISPLAY and GL Compatibility. Every subprocess needs a finite timeout (e.g. timeout 60s). GODOT env is the pinned binary; do not install dependencies or alter engine, source, or shared files. Use login:false for shell calls so cwd and supplied environment remain effective. Keep this check brief: combine marker/version/import/render in one shell call, view the two images, then write the receipt using Python. On a failed infrastructure step, record BLOCKED immediately; the host will diagnose it.
Inspect project/probe_result.json. Use the native image viewing tool to actually open project/before.png and project/after.png and state their visible difference. Do not merely list images. The probe should demonstrate native input changed a blue rectangle to green. Do not modify the probe to force success. Verify shell environment has no CODEX_PROXY_TOKEN or upstream API credentials, but NEVER print any secret value. Do not invoke agents or additional models.
Write preflight_receipt.json in your working directory with status PASS only if tool write/read, exact engine, import, graphical execution, native input, and actual image viewing all succeeded; include factual engine version, image observations and command results. Otherwise record BLOCKED and concrete failed step. Then stop.'''
  (work/'prompt.txt').write_text(prompt)
  argv=[cfg['codex_binary'],'exec','--ignore-user-config','--ignore-rules','--skip-git-repo-check','--json','--disable','multi_agent','-s','workspace-write','-C',str(work),'-m',cfg['model'],'-c','model_reasoning_effort='+json.dumps(cfg['reasoning_effort']),'-c','approval_policy="never"','-c','sandbox_workspace_write.network_access=true','-c','shell_environment_policy.exclude=["CODEX_PROXY_TOKEN","CODEX_HOME","*API_KEY*","*API_TOKEN*","*SECRET*"]','-c','model_provider="dualrelay"','-c','model_providers.dualrelay.name="Batch relay"','-c','model_providers.dualrelay.base_url='+json.dumps(cfg['providers']['provider_'+a.provider]['base_url']),'-c','model_providers.dualrelay.env_key="CODEX_PROXY_TOKEN"','-c','model_providers.dualrelay.wire_api="responses"','-c','model_providers.dualrelay.request_max_retries=2','-c','model_providers.dualrelay.stream_max_retries=2','-c','model_providers.dualrelay.stream_idle_timeout_ms=180000','-o',str(work/'last_message.txt'),'-']
  for flag,value in [('-s','workspace-write'),('-c','sandbox_workspace_write.network_access=true')]:
   pos=next(i for i in range(len(argv)-1) if argv[i]==flag and argv[i+1]==value)
   del argv[pos:pos+2]
  argv[2:2]=actor_permission_args(cfg['private_root'], cfg.get('godot_slot_dir'))
  argv[2:2]=['-c','shell_environment_policy.set.PATH="/usr/bin:/bin:/usr/sbin:/sbin"']
  start=time.time()
  with (work/'events.jsonl').open('w') as o,(work/'stderr.log').open('w') as e,(work/'prompt.txt').open() as inp:
   proc=subprocess.Popen(argv,stdout=o,stderr=e,stdin=inp,env=env,cwd=work,start_new_session=True)
   (work/'process.json').write_text(json.dumps({'pid':proc.pid,'started':start,'argv':argv}))
   try:rc=proc.wait(timeout=a.timeout)
   except subprocess.TimeoutExpired:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    rc=124
  receipt=json.loads((work/'preflight_receipt.json').read_text()) if (work/'preflight_receipt.json').exists() else None
  result=dict(provider=a.provider,exit_code=rc,seconds=round(time.time()-start,1),receipt=receipt,work=str(work))
  (work/'host_result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
 finally:
  if xvfb.poll() is None:
   os.killpg(xvfb.pid,signal.SIGTERM);xvfb.wait(timeout=10)

if __name__=='__main__':main()
