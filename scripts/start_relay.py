#!/usr/bin/env python3
"""Start host-only Responses relay. Credentials are read from environment."""
import argparse,importlib.util,os,secrets,json
from pathlib import Path
from http.server import ThreadingHTTPServer
P=Path(__file__).resolve().parents[1]/'pipeline/host_tools/api_proxy.py'
s=importlib.util.spec_from_file_location('relay',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def main():
 p=argparse.ArgumentParser();p.add_argument('--private-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--port',type=int,default=18989);p.add_argument('--limit',type=int,default=16);a=p.parse_args()
 if not 1<=a.limit<=64:p.error('limit must be 1..64')
 a.private_root.mkdir(parents=True,exist_ok=True,mode=0o700);a.private_root.chmod(0o700);config={}
 for name in 'abc':
  key=os.environ.get('PROVIDER_'+name.upper()+'_API_KEY');url=os.environ.get('PROVIDER_'+name.upper()+'_BASE_URL')
  if not key and not url:continue
  if not key or not url:p.error('Both provider key and base URL are required')
  f=a.private_root/(name+'.token')
  if not f.exists():
   fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'w') as out:out.write(secrets.token_urlsafe(32))
  config[name]={'api_key':key,'base_url':url.rstrip('/'),'local_token':f.read_text().strip(),'limit':a.limit}
 if not config:p.error('Set PROVIDER_A_API_KEY and PROVIDER_A_BASE_URL')
 server=ThreadingHTTPServer(('127.0.0.1',a.port),m.Handler);server.relay=m.Relay(config,a.output)
 print(json.dumps({'listen':'127.0.0.1','port':a.port,'providers':list(config),'limit':a.limit}),flush=True);server.serve_forever()
if __name__=='__main__':main()
