"""
WSGI entry point, for hosts that run Python web apps through WSGI
(for example PythonAnywhere). It runs the same request handler as server.py,
so the pages, API, accounts and data files behave exactly the same.

PythonAnywhere: in the Web tab, open the WSGI configuration file and replace
its contents with (change the path to your own):

    import sys
    sys.path.insert(0, "/home/YOURNAME/thesis-noise-monitoring/software/dashboard")
    from wsgi import application

To try it locally:
    python -c "from wsgiref.simple_server import make_server; from wsgi import application; make_server('', 8000, application).serve_forever()"
"""

import io
import email.parser
from http.client import responses

import server

server.load_history()


class _WSGIHandler(server.Handler):
    """server.Handler fed from a WSGI environ instead of a socket."""

    def __init__(self, environ):  # noqa: D401 - deliberately skips the socket setup
        self.directory = str(server.DASHBOARD_DIR)
        self.command = environ["REQUEST_METHOD"]
        query = environ.get("QUERY_STRING", "")
        self.path = environ.get("PATH_INFO", "/") + (f"?{query}" if query else "")
        self.request_version = "HTTP/1.1"
        self.requestline = f"{self.command} {self.path} HTTP/1.1"
        self.close_connection = True
        # Behind the host's proxy the real visitor address is in X-Real-IP / X-Forwarded-For.
        ip = environ.get("HTTP_X_REAL_IP") or environ.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or environ.get("REMOTE_ADDR", "")
        self.client_address = (ip, 0)
        header_lines = []
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header_lines.append(f"{key[5:].replace('_', '-').title()}: {value}")
        if environ.get("CONTENT_TYPE"):
            header_lines.append(f"Content-Type: {environ['CONTENT_TYPE']}")
        if environ.get("CONTENT_LENGTH"):
            header_lines.append(f"Content-Length: {environ['CONTENT_LENGTH']}")
        self.headers = email.parser.Parser(_class=server.Handler.MessageClass).parsestr("\r\n".join(header_lines) + "\r\n\r\n")
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        body = environ["wsgi.input"].read(min(length, server.MAX_BODY_BYTES + 1)) if length else b""
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()

    def log_message(self, fmt, *args):
        pass  # the host keeps its own access log


def application(environ, start_response):
    handler = _WSGIHandler(environ)
    method = getattr(handler, "do_" + handler.command, None)
    if method is None:
        handler.send_error(405)
    else:
        method()
    raw = handler.wfile.getvalue()
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    code = int(lines[0].split(" ", 2)[1]) if lines and lines[0].startswith("HTTP/") else 500
    headers = []
    for line in lines[1:]:
        name, _, value = line.partition(":")
        # Hop-by-hop and server-identity headers are the host's job.
        if name and name.lower() not in ("connection", "server", "date", "transfer-encoding"):
            headers.append((name, value.strip()))
    start_response(f"{code} {responses.get(code, '')}", headers)
    return [body] if handler.command != "HEAD" else []
