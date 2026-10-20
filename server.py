"""Zeeshan Usmani digital twin: tiny backend that keeps the Anthropic key server-side.

Standard library only (Python 3.9+). Run:  python3 server.py
Config comes from environment variables or a .env file next to this script:
  ANTHROPIC_API_KEY  required
  MODEL              default claude-sonnet-5-5
  ACCESS_CODE        optional; if set, visitors must enter it before chatting
  PORT               default 8000
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.stdout.reconfigure(line_buffering=True)  # so hosted logs show up immediately


def load_dotenv():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_dotenv()
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")
PORT = int(os.environ.get("PORT", "8000"))

MAX_TURNS = 20           # messages of history sent upstream
MAX_CHARS = 4000         # per user message
RATE_LIMIT = 20          # requests per IP ...
RATE_WINDOW = 60 * 10    # ... per 10 minutes

SYSTEM_TEMPLATE = """You are the AI digital twin of Zeeshan Usmani (Zeeshan-ul-Hassan Usmani), created with his permission.
Speak in first person in his voice and style, as described in the knowledge base below.

Rules:
- Base factual claims about Zeeshan's life, work, opinions and numbers ONLY on the knowledge base. If something isn't covered, say you'd rather not guess, or answer from general expertise while making clear it's general advice.
- Never invent quotes, dates, employers, figures or personal details.
- If anyone asks whether you are the real Zeeshan, say plainly that you are an AI twin, not the person.
- Don't make commitments, promises, endorsements, financial or legal agreements on his behalf. For bookings, collaborations or personal matters, tell people to contact the real Zeeshan through his official channels.
- Reply in the user's language (English, Urdu, or Roman Urdu). Keep answers conversational and reasonably concise.

<knowledge_base>
{kb}
</knowledge_base>"""

hits = defaultdict(deque)


def rate_limited(ip):
    now = time.time()
    q = hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


def clean_messages(raw):
    if not isinstance(raw, list) or not raw:
        raise ValueError("messages must be a non-empty list")
    msgs = []
    for m in raw[-MAX_TURNS:]:
        role, content = m.get("role"), m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            raise ValueError("bad message")
        msgs.append({"role": role, "content": content[:MAX_CHARS]})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs or msgs[-1]["role"] != "user":
        raise ValueError("last message must be from the user")
    return msgs


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("%s - %s" % (self.client_ip(), fmt % args))

    def client_ip(self):
        fwd = self.headers.get("X-Forwarded-For")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (ROOT / "public" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/config":
            self.send_json(200, {"needsCode": bool(ACCESS_CODE)})
        elif self.path == "/healthz":
            self.send_json(200, {"ok": True})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/chat":
            return self.send_json(404, {"error": "not found"})
        if not API_KEY:
            return self.send_json(500, {"error": "Server has no ANTHROPIC_API_KEY set."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 200_000:
                return self.send_json(413, {"error": "Request too large."})
            req = json.loads(self.rfile.read(length) or b"{}")
            if ACCESS_CODE and req.get("code") != ACCESS_CODE:
                return self.send_json(401, {"error": "Wrong access code."})
            messages = clean_messages(req.get("messages"))
        except (ValueError, AttributeError, json.JSONDecodeError) as e:
            return self.send_json(400, {"error": str(e) or "Bad request."})
        if rate_limited(self.client_ip()):
            return self.send_json(429, {"error": "Too many messages. Please wait a few minutes."})

        kb = (ROOT / "knowledge.md").read_text(encoding="utf-8")
        upstream = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({
                "model": MODEL,
                "max_tokens": 1024,
                "stream": True,
                "system": SYSTEM_TEMPLATE.format(kb=kb),
                "messages": messages,
            }).encode(),
            headers={
                "content-type": "application/json",
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            resp = urllib.request.urlopen(upstream, timeout=120)
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("error", {}).get("message", "")
            except Exception:
                msg = ""
            print("upstream error", e.code, msg)
            return self.send_json(502, {"error": "The AI service returned an error (%s): %s" % (e.code, msg)})
        except urllib.error.URLError as e:
            return self.send_json(502, {"error": "Couldn't reach the AI service: %s" % e.reason})

        # Forward only the text deltas, as a plain-text stream.
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: "):
                    continue
                try:
                    ev = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "content_block_delta" and ev["delta"].get("type") == "text_delta":
                    try:
                        self.wfile.write(ev["delta"]["text"].encode())
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                elif ev.get("type") == "error":
                    self.wfile.write(b"\n\n[Sorry, something went wrong. Please try again.]")
                    return


if __name__ == "__main__":
    if not API_KEY:
        print("WARNING: ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
    print("Zeeshan twin running on http://localhost:%d (model %s, access code %s)"
          % (PORT, MODEL, "on" if ACCESS_CODE else "off"))
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
