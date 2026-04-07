# web_serve.py
"""
Lightweight web server that streams the pygame game to a browser.
No additional dependencies — uses stdlib http.server + raw RGB frames.

Usage: python client.py --web
Opens http://localhost:1232 in your browser to play.
"""

import io
import json
import struct
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

# Shared state between game thread and web server
_frame_lock = threading.Lock()
_frame_data = None        # raw RGB bytes of current frame
_frame_w = 1280
_frame_h = 720
_input_queue = []         # pending input events from browser
_input_lock = threading.Lock()

WEB_W = 1280  # web streaming resolution
WEB_H = 720


def set_frame(pygame_surface, pygame_module):
    """Called from the game loop to update the current frame."""
    global _frame_data, _frame_w, _frame_h
    try:
        # Downscale to web resolution
        scaled = pygame_module.transform.scale(pygame_surface, (WEB_W, WEB_H))
        raw = pygame_module.image.tobytes(scaled, 'RGB')
        with _frame_lock:
            _frame_data = raw
            _frame_w = WEB_W
            _frame_h = WEB_H
    except Exception:
        pass


def get_pending_inputs():
    """Get and clear pending input events from the browser."""
    with _input_lock:
        events = list(_input_queue)
        _input_queue.clear()
    return events


# BMP encoding (no dependencies needed)
def _rgb_to_bmp(raw_rgb, w, h):
    """Encode raw RGB bytes to BMP format (bottom-up, padded rows)."""
    row_size = (w * 3 + 3) & ~3  # pad to 4 bytes
    pixel_size = row_size * h
    file_size = 54 + pixel_size
    # BMP file header (14 bytes)
    header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 54)
    # DIB header (40 bytes)
    dib = struct.pack('<IiiHHIIiiII', 40, w, h, 1, 24, 0, pixel_size, 2835, 2835, 0, 0)
    # Pixel data (flip vertically, BGR order, pad rows)
    rows = []
    for y in range(h - 1, -1, -1):
        offset = y * w * 3
        row = bytearray()
        for x in range(w):
            px = offset + x * 3
            row.append(raw_rgb[px + 2])  # B
            row.append(raw_rgb[px + 1])  # G
            row.append(raw_rgb[px])      # R
        # Pad row
        while len(row) % 4 != 0:
            row.append(0)
        rows.append(bytes(row))
    return header + dib + b''.join(rows)


HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>GeoPolitical Domination</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0e1220; display: flex; justify-content: center; align-items: center; height: 100vh; overflow: hidden; }
  canvas { cursor: crosshair; }
  #status { position: fixed; top: 8px; right: 8px; color: #8a8; font: 14px monospace; background: rgba(0,0,0,0.6); padding: 4px 8px; border-radius: 4px; z-index: 10; }
</style>
</head>
<body>
<canvas id="c" width="WEB_W" height="WEB_H"></canvas>
<div id="status">Connecting...</div>
<script>
const W = WEB_W, H = WEB_H;
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const status = document.getElementById('status');
let frames = 0, lastFps = 0, lastCount = Date.now();

// Resize canvas to fill window while preserving aspect ratio
function resizeCanvas() {
    const vw = window.innerWidth, vh = window.innerHeight;
    const s = Math.min(vw / W, vh / H);
    canvas.style.width = Math.floor(W * s) + 'px';
    canvas.style.height = Math.floor(H * s) + 'px';
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

function canvasCoords(e) {
    const rect = canvas.getBoundingClientRect();
    return {
        x: Math.round((e.clientX - rect.left) / rect.width * W),
        y: Math.round((e.clientY - rect.top) / rect.height * H)
    };
}

// Send input to server
function sendInput(data) {
    fetch('/input', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) }).catch(()=>{});
}

canvas.addEventListener('mousedown', e => { const p = canvasCoords(e); sendInput({type:'mousedown', button: e.button+1, x: p.x, y: p.y}); e.preventDefault(); });
canvas.addEventListener('mouseup', e => { const p = canvasCoords(e); sendInput({type:'mouseup', button: e.button+1, x: p.x, y: p.y}); e.preventDefault(); });
canvas.addEventListener('mousemove', e => { const p = canvasCoords(e); sendInput({type:'mousemove', x: p.x, y: p.y}); });
canvas.addEventListener('wheel', e => { sendInput({type:'wheel', y: e.deltaY > 0 ? -1 : 1}); e.preventDefault(); }, {passive:false});
canvas.addEventListener('contextmenu', e => e.preventDefault());

document.addEventListener('keydown', e => {
    sendInput({type:'keydown', key: e.key, code: e.keyCode}); e.preventDefault();
});
document.addEventListener('keyup', e => {
    sendInput({type:'keyup', key: e.key, code: e.keyCode});
});

// Frame streaming
async function streamFrames() {
    while (true) {
        try {
            const resp = await fetch('/frame');
            if (!resp.ok) { await new Promise(r => setTimeout(r, 500)); continue; }
            const buf = await resp.arrayBuffer();
            const rgb = new Uint8Array(buf);
            const img = ctx.createImageData(W, H);
            const d = img.data;
            for (let i = 0, j = 0; i < rgb.length; i += 3, j += 4) {
                d[j] = rgb[i]; d[j+1] = rgb[i+1]; d[j+2] = rgb[i+2]; d[j+3] = 255;
            }
            ctx.putImageData(img, 0, 0);
            frames++;
            if (Date.now() - lastCount > 1000) { lastFps = frames; frames = 0; lastCount = Date.now(); }
            status.textContent = lastFps + ' FPS';
        } catch(e) {
            status.textContent = 'Disconnected';
            await new Promise(r => setTimeout(r, 1000));
        }
    }
}
streamFrames();
</script>
</body>
</html>""".replace('WEB_W', str(WEB_W)).replace('WEB_H', str(WEB_H))


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress request logs

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
        elif self.path == '/frame':
            with _frame_lock:
                data = _frame_data
            if data:
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(204)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/input':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length else b''
            try:
                evt = json.loads(body)
                with _input_lock:
                    _input_queue.append(evt)
            except Exception:
                pass
            self.send_response(200)
            self.send_header('Content-Length', '0')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


def start_server(port=1232):
    """Start the web server in a background thread."""
    server = HTTPServer(('0.0.0.0', port), _Handler)
    server.timeout = 0.5
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[Web] Server running at http://localhost:{port}")
    return server
