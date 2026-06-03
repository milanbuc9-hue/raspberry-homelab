#!/usr/bin/env python3
"""
Contact-Form Proxy für milanbuchta.com
- Nimmt POST /api/contact {name, message} entgegen
- Hält Bot-Token + Chat-ID server-seitig (aus Env) -> NIE im Browser
- Leitet als Telegram-Nachricht weiter
"""
import json, os, html, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "6372069186")
PORT = int(os.environ.get("PORT", "8080"))

MAX_NAME = 100
MAX_MSG = 4000


def log(msg):
    print(msg, flush=True)


def send_telegram(name, message):
    text = (
        "📬 <b>Neue Nachricht — milanbuchta.com</b>\n\n"
        f"👤 <b>Name:</b> {html.escape(name)}\n\n"
        f"💬 <b>Nachricht:</b>\n{html.escape(message)}"
    )
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status == 200


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        # nginx proxyt /api/contact -> hier landet "/" oder "/api/contact"
        if self.path not in ("/", "/api/contact"):
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > 16384:
                self._json(400, {"error": "invalid length"})
                return
            payload = json.loads(self.rfile.read(length))
            name = str(payload.get("name", "")).strip()[:MAX_NAME]
            message = str(payload.get("message", "")).strip()[:MAX_MSG]
            if not name or not message:
                self._json(400, {"error": "name und message erforderlich"})
                return
            send_telegram(name, message)
            log(f"CONTACT_SENT name={name!r} len={len(message)}")
            self._json(200, {"ok": True})
        except Exception as e:
            log(f"CONTACT_ERROR: {e}")
            self._json(502, {"error": "send failed"})

    def log_message(self, *args):
        pass  # eigenes Logging via log()


if __name__ == "__main__":
    log(f"contact-proxy listening on :{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
