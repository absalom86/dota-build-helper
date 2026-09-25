from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import secrets
import threading


def config_text(token, port=38765):
    return f'''"Dota Build Helper"
{{
    "uri" "http://127.0.0.1:{port}/"
    "timeout" "5.0"
    "buffer" "0.1"
    "throttle" "0.5"
    "heartbeat" "2.0"
    "auth" {{ "token" "{token}" }}
    "data"
    {{
        "provider" "1"
        "map" "1"
        "player" "1"
        "hero" "1"
        "abilities" "1"
        "items" "1"
        "draft" "1"
    }}
}}
'''


class Receiver:
    def __init__(self, callback, token=None, port=38765):
        self.token = token or secrets.token_urlsafe(32)
        secret = self.token

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def do_POST(self):
                try:
                    size = int(self.headers.get("Content-Length", 0))
                    if not 0 < size <= 262144:
                        self.send_error(413)
                        return
                    payload = json.loads(self.rfile.read(size))
                    token_value = payload.get("auth", {}).get("token", "")
                    if not isinstance(token_value, str) or not hmac.compare_digest(token_value, secret):
                        self.send_error(403)
                        return
                    if not all(isinstance(payload.get(k, {}), dict) for k in ("map", "hero", "player", "items", "abilities")):
                        self.send_error(400)
                        return
                    payload.pop("auth", None)
                    callback(payload)
                    self.send_response(200)
                    self.end_headers()
                except (ValueError, AttributeError, TypeError, TimeoutError):
                    self.send_error(400)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
