"""Experiment-scoped HTTP route to the user-provided K3 endpoint.

The original CONNECT proxy still handles official Godot documentation. The
solver receives a dummy credential; only this host-side bridge reads the key.
Request/response bodies are saved privately for reproducible trajectory counts.
"""
import http.client
import http.server
import json
import socket
import socketserver
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from gamedevbench.src.provider_proxy import (
    ProviderProxy, _ProviderProxyHandler, _ThreadingUnixServer,
)



class HTTPRoute(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def forward(self):
        target = urlsplit(self.path)
        if (target.scheme != 'http' or target.netloc != 'model.local'
                or target.query or target.fragment
                or (self.command, target.path) not in {
                    ('GET', '/v1/models'), ('POST', '/v1/chat/completions')}):
            self.server.audit.record(self.path, False)
            self.send_error(403, 'Route unavailable')
            return
        if self.headers.get('Transfer-Encoding'):
            self.send_error(400, 'Content-Length required')
            return
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 <= size <= 100 * 1024 * 1024:
            self.send_error(413)
            return
        body = self.rfile.read(size)
        if self.command == 'POST':
            payload = json.loads(body)
            if payload.get('model') != self.server.model:
                self.send_error(403, 'Unexpected model')
                return
            # Kimi's generic thinking switch emits "high". This deployment
            # accepts xhigh (its default), medium, or low when thinking is on.
            # Adapt only the model parameter, leaving messages/tools intact.
            if self.server.family == 'qwen' and payload.get('reasoning_effort') == 'high':
                payload['reasoning_effort'] = 'xhigh'
                body = json.dumps(payload, ensure_ascii=False).encode()
        self.server.audit.record(self.path, True)
        with self.server.counter_lock:
            self.server.counter += 1
            sequence = self.server.counter
        prefix = self.server.evidence / f'{sequence:06d}'
        prefix.with_suffix('.request.json').write_bytes(body or b'{}')
        metadata = {'sequence': sequence, 'method': self.command,
                    'path': target.path, 'started_unix': time.time()}
        base = urlsplit(self.server.upstream)
        cls = http.client.HTTPSConnection if base.scheme == 'https' else http.client.HTTPConnection
        connection = cls(base.hostname, base.port, timeout=30)
        self.close_connection = True
        sent = False
        try:
            # Bound only TCP/TLS establishment. Generation/stream reads have no deadline.
            connection.connect()
            connection.sock.settimeout(None)
            connection.request(self.command, base.path + target.path[len('/v1'):],
                               body=body or None,
                               headers={'Authorization': 'Bearer ' + self.server.key,
                                        'Content-Type': 'application/json',
                                        'Accept': self.headers.get('Accept', '*/*')})
            response = connection.getresponse()
            metadata['status'] = response.status
            self.send_response(response.status)
            self.send_header('Content-Type', response.getheader('Content-Type',
                                                              'application/json'))
            self.send_header('Connection', 'close')
            self.end_headers()
            sent = True
            with prefix.with_suffix('.response.body').open('wb', buffering=0) as out:
                while chunk := response.read1(65536):
                    out.write(chunk)
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except Exception as error:
            metadata['error_type'] = type(error).__name__
            if not sent:
                self.send_error(502, 'Upstream request failed')
        finally:
            connection.close()
            metadata['ended_unix'] = time.time()
            prefix.with_suffix('.meta.json').write_text(json.dumps(metadata, indent=2))


class Dispatch(socketserver.BaseRequestHandler):
    def handle(self):
        # Peeking leaves CONNECT bytes intact for the original audited handler.
        first = self.request.recv(8, socket.MSG_PEEK)
        if first.startswith(b'CONNECT '):
            _ProviderProxyHandler(self.request, self.client_address, self.server)
        else:
            HTTPRoute(self.request, ('local', 0), self.server)


class ModelProxy(ProviderProxy):
    def __init__(self, socket_path, allowed_hosts, *, credential, model, upstream, family, evidence):
        super().__init__(socket_path, ('docs.godotengine.org',))
        self.credential = credential
        self.model = model
        self.upstream = upstream.rstrip('/')
        self.family = family
        self.evidence = Path(evidence)

    def __enter__(self):
        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.socket_path.unlink(missing_ok=True)
        server = _ThreadingUnixServer(str(self.socket_path), Dispatch)
        server.allowed_hosts = self.allowed_hosts
        server.audit = self.audit
        server.key = self.credential
        server.model = self.model
        server.upstream = self.upstream
        server.family = self.family
        server.evidence = self.evidence
        server.counter = 0
        server.counter_lock = threading.Lock()
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        return self
