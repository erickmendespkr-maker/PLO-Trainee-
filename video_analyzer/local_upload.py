"""Loopback-only offline video upload/status UI; worker runs separately.

Run: python video_analyzer/local_upload.py /path/to/private-workdir --port 8765
Then: python video_analyzer/offline_worker.py /path/to/private-workdir/jobs.sqlite /path/to/private-workdir/results

No network binding beyond 127.0.0.1, no remote poker connectivity, no auto-review.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import uuid

from offline_jobs import OfflineJobStore
from video_validator import ALLOWED_EXTENSIONS, MAX_SIZE_BYTES

HTML = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PLO Trainee — análise offline</title>
<style>body{font:16px system-ui;max-width:720px;margin:6vh auto;padding:1rem;background:#121a25;color:#f5f7fa}
main{background:#223044;border-radius:16px;padding:2rem}input,button{padding:12px;margin:10px 0}
button{background:#83dbbd;border:0;border-radius:8px;font-weight:bold}pre{white-space:pre-wrap;word-break:break-word}
small{color:#d2dce9}</style><main><h1>PLO Trainee</h1>
<p>Envie uma gravação MP4/WebM. A análise é local e requer revisão humana das cartas e ações.</p>
<input id="file" type="file" accept=".mp4,.webm"><br><button id="send">Enviar gravação</button>
<pre id="status" role="status">Aguardando vídeo.</pre>
<small>O worker é iniciado separadamente. Nenhuma conexão com mesas de pôquer ao vivo.</small></main>
<script>
const status=document.getElementById('status');
async function poll(id){try{const r=await fetch('/api/jobs/'+id);const data=await r.json();
status.textContent=JSON.stringify(data,null,2);if(data.state==='review_required'){const a=document.createElement('a');a.href='/api/jobs/'+id+'/report';a.textContent='Ver relatório de extração';a.style.color='#83dbbd';status.append('\n');status.append(a)}if(['queued','running'].includes(data.state))setTimeout(()=>poll(id),2500);
}catch(e){status.textContent='Erro ao consultar: '+e.message}}
document.getElementById('send').onclick=async()=>{const file=document.getElementById('file').files[0];
if(!file){status.textContent='Selecione um vídeo.';return}
status.textContent='Enviando...';try{const r=await fetch('/api/upload',{method:'POST',headers:{
'Content-Type':'application/octet-stream','X-PLO-Local-Upload':'1','X-File-Name':file.name},body:file});
const data=await r.json();if(!r.ok)throw Error(data.error||'Upload rejeitado');poll(data.job_id)
}catch(e){status.textContent='Erro: '+e.message}};
</script></html>'''


def make_handler(root, *, max_upload_bytes=MAX_SIZE_BYTES):
    """Return a handler bound to an isolated local workspace (useful in tests)."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    upload_dir = root / 'uploads'
    upload_dir.mkdir(exist_ok=True)
    store = OfflineJobStore(root / 'jobs.sqlite')
    if isinstance(max_upload_bytes, bool) or not isinstance(max_upload_bytes, int) or not 0 < max_upload_bytes <= MAX_SIZE_BYTES:
        raise ValueError('Invalid upload size limit')

    class Handler(BaseHTTPRequestHandler):
        server_version = 'PLO-Offline/0.1'
        protocol_version = 'HTTP/1.1'

        def _valid_host(self):
            # Reject DNS rebinding to loopback, even if the socket is local.
            host = self.headers.get('Host', '')
            port = self.server.server_port
            return host in (f'127.0.0.1:{port}', f'localhost:{port}',
                            '127.0.0.1', 'localhost')

        def _send(self, status, payload, content_type='application/json; charset=utf-8'):
            data = (payload.encode('utf-8') if isinstance(payload, str)
                    else json.dumps(payload, ensure_ascii=False).encode('utf-8'))
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self' 'unsafe-inline'; connect-src 'self'")
            if status >= 400:
                self.send_header('Connection', 'close')
                self.close_connection = True
            self.end_headers()
            self.wfile.write(data)

        def _deny_host(self):
            if not self._valid_host():
                self._send(403, {'error': 'Invalid local Host header'})
                return True
            return False

        def do_GET(self):
            if self._deny_host():
                return
            if self.path == '/':
                self._send(200, HTML, 'text/html; charset=utf-8')
                return
            match = re.fullmatch(r'/api/jobs/([0-9a-f]{32})(/report|/review-template)?', self.path)
            if not match:
                self._send(404, {'error': 'Not found'})
                return
            job = store.get(match.group(1))
            if job is None:
                self._send(404, {'error': 'Unknown job'})
                return
            if match.group(2):
                if job['state'] != 'review_required' or not job.get('result_path'):
                    self._send(409, {'error': 'Review report is not available'})
                    return
                result_file = Path(job['result_path']).resolve()
                safe_root = (root / 'results' / job['job_id']).resolve()
                if result_file != safe_root / 'result.json':
                    self._send(403, {'error': 'Report outside local workspace'})
                    return
                selected = result_file if match.group(2) == '/report' else safe_root / 'review_template.json'
                if not selected.is_file():
                    self._send(404, {'error': 'Review artifact not found'})
                    return
                try:
                    payload = json.loads(selected.read_text(encoding='utf-8'))
                except (ValueError, OSError):
                    self._send(422, {'error': 'Invalid review artifact'})
                    return
                if match.group(2) == '/report':
                    payload = {key: payload[key] for key in (
                        'schema_version', 'job_id', 'status', 'frame_count',
                        'ocr_candidates', 'review_template', 'table_count',
                        'timestamp_semantics', 'requires_manual_review', 'next_step')
                        if key in payload}
                self._send(200, payload)
                return
            # Never disclose filesystem paths, hashes or internal tracebacks to the UI.
            self._send(200, {k: job[k] for k in ('job_id', 'state', 'attempts', 'created_at', 'updated_at')})

        def do_POST(self):
            if self._deny_host():
                return
            if self.path != '/api/upload':
                self._send(404, {'error': 'Not found'})
                return
            origin = self.headers.get('Origin')
            if origin is not None and origin not in (f'http://127.0.0.1:{self.server.server_port}',
                                                     f'http://localhost:{self.server.server_port}'):
                self._send(403, {'error': 'Invalid upload Origin'})
                return
            if self.headers.get('X-PLO-Local-Upload') != '1':
                self._send(403, {'error': 'Missing local upload confirmation header'})
                return
            if self.headers.get('Transfer-Encoding'):
                self._send(400, {'error': 'Chunked uploads are not supported'})
                return
            size_text = self.headers.get('Content-Length', '')
            if not size_text.isascii() or not size_text.isdecimal():
                self._send(411, {'error': 'Content-Length required'})
                return
            size = int(size_text)
            if size < 1 or size > max_upload_bytes:
                self._send(413, {'error': 'Upload size outside allowed limit'})
                return
            filename = self.headers.get('X-File-Name', '')
            if (not filename or filename != Path(filename).name or '\\' in filename
                    or '\x00' in filename or Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS):
                self._send(400, {'error': 'Invalid MP4/WebM filename'})
                return
            destination = upload_dir / (uuid.uuid4().hex + Path(filename).suffix.lower())
            try:
                # Exclusive create, bounded streaming, and cleanup on any failure.
                with destination.open('xb') as output:
                    remaining = size
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError('Incomplete upload')
                        output.write(chunk)
                        remaining -= len(chunk)
                job = store.enqueue(destination)
            except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, KeyError, json.JSONDecodeError):
                destination.unlink(missing_ok=True)
                self.close_connection = True
                self._send(422, {'error': 'Video rejected: invalid or incomplete recording'})
                return
            self._send(202, {'job_id': job['job_id'], 'state': job['state']})

        def log_message(self, format, *args):
            return  # Avoid logging private filenames/queries.

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', help='Private local directory for uploads and queue')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(args.workspace))
    print(f'Open http://127.0.0.1:{server.server_port} locally; run offline_worker.py separately.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
