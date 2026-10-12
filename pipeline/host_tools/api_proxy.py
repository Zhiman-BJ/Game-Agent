#!/usr/bin/env python3
"""Local Responses relay. Upstream secrets stay in the host, never author envs."""
import argparse
import collections
import datetime
import hmac
import json
import os
from pathlib import Path
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Relay:
    def __init__(self, config, output):
        self.config = config
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.semaphores = {k: threading.BoundedSemaphore(v['limit']) for k, v in config.items()}
        self.stats = {k: dict(active=0, peak=0, requests=0, completed=0, errors=0,
                             limit=v['limit'], status_counts={}) for k, v in config.items()}

    def event(self, provider, kind, **data):
        with self.lock:
            s = self.stats[provider]
            if kind == 'start':
                s['active'] += 1
                s['requests'] += 1
                s['peak'] = max(s['peak'], s['active'])
            if kind == 'end':
                s['active'] -= 1
                s['completed'] += int(data.get('response_completed', False))
                code = str(data.get('http_status', 'transport_error'))
                s['status_counts'][code] = s['status_counts'].get(code, 0) + 1
                s['errors'] += int(data.get('error_class') is not None or data.get('response_failure_event') is not None or code != '200')
            entry = dict(at=utc(), provider=provider, event=kind, **data)
            with (self.output / 'requests.jsonl').open('a') as f:
                f.write(json.dumps(entry) + '\n')
            tmp = self.output / 'status.json.tmp'
            tmp.write_text(json.dumps(dict(updated_utc=utc(), providers=self.stats), indent=2))
            tmp.replace(self.output / 'status.json')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *_):
        pass

    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            with self.server.relay.lock:
                data = json.loads(json.dumps(self.server.relay.stats))
            self.reply(200, dict(status='ok', providers=data))
        else:
            self.forward()

    def do_POST(self):
        self.forward()

    def forward(self):
        relay = self.server.relay
        parts = self.path.split('/')
        if len(parts) != 4 or parts[1] not in relay.config or parts[2] != 'v1' or parts[3] not in ('responses', 'models'):
            return self.reply(404, {'error': {'message': 'Unknown relay route'}})
        provider = parts[1]
        cfg = relay.config[provider]
        expected = 'Bearer ' + cfg['local_token']
        if not hmac.compare_digest(self.headers.get('Authorization', ''), expected):
            return self.reply(401, {'error': {'message': 'Invalid relay authorization'}})
        length = int(self.headers.get('Content-Length', '0'))
        if length > 128 * 1024 * 1024:
            return self.reply(413, {'error': {'message': 'Request too large'}})
        body = self.rfile.read(length) if length else None
        info = {}
        if body:
            try:
                request = json.loads(body)
                info = dict(model=request.get('model'), reasoning=request.get('reasoning'),
                            stream=request.get('stream'), tool_count=len(request.get('tools', [])))
            except (ValueError, TypeError):
                return self.reply(400, {'error': {'message': 'Invalid JSON'}})
        sem = relay.semaphores[provider]
        if not sem.acquire(timeout=600):
            return self.reply(429, {'error': {'message': 'Relay concurrency queue timeout'}})
        began = time.monotonic()
        record = dict(response_completed=False)
        relay.event(provider, 'start', **info)
        started = False
        response = None
        try:
            response = requests.request(self.command, cfg['base_url'].rstrip('/') + '/'+parts[3],
                headers={'Authorization': 'Bearer '+cfg['api_key'], 'Content-Type': 'application/json',
                         'Accept': self.headers.get('Accept', '*/*'), 'Accept-Encoding': 'identity'},
                data=body, stream=True, timeout=(30, 600), allow_redirects=False)
            record['http_status'] = response.status_code
            self.send_response(response.status_code)
            self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'close')
            self.end_headers()
            started = True
            pending = b''
            is_sse = 'event-stream' in response.headers.get('Content-Type', '')
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                self.wfile.write(chunk)
                self.wfile.flush()
                if is_sse:
                    pending += chunk
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        if line.startswith(b'data:'):
                            try:
                                event = json.loads(line[5:])
                                if event.get('type') == 'response.completed':
                                    record['response_completed'] = True
                                    record['usage'] = event.get('response', {}).get('usage')
                                elif event.get('type') in ('response.failed', 'error'):
                                    record['response_failure_event'] = event.get('type')
                            except (ValueError, TypeError):
                                pass
                    if len(pending) > 16 * 1024 * 1024:
                        pending = b''
        except (requests.RequestException, OSError) as error:
            record['error_class'] = type(error).__name__
            if not started:
                try:
                    self.reply(502, {'error': {'message': 'Upstream relay transport failure', 'type': type(error).__name__}})
                except OSError:
                    pass
        finally:
            if response is not None:
                response.close()
            record['seconds'] = round(time.monotonic() - began, 3)
            relay.event(provider, 'end', **record)
            sem.release()
            self.close_connection = True


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--port', type=int, default=18987)
    a = p.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    server = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    server.daemon_threads = True
    server.relay = Relay(cfg, a.output)
    Path(a.output, 'process.json').write_text(json.dumps(dict(pid=os.getpid(), port=a.port, started_utc=utc())))
    print(json.dumps(dict(status='READY', port=a.port, provider_limits={k:v['limit'] for k,v in cfg.items()})), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
