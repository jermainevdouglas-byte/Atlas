"""WSGI adapter to run the existing BaseHTTPRequestHandler stack under Gunicorn."""
from __future__ import annotations

from io import BytesIO
from http import HTTPStatus

from .http_handler import H


class _CaseInsensitiveHeaders:
    def __init__(self):
        self._store = {}

    def add(self, name: str, value: str):
        k = str(name or "").strip()
        if not k:
            return
        self._store[k.lower()] = (k, str(value or ""))

    def get(self, name: str, default=None):
        k = str(name or "").lower()
        row = self._store.get(k)
        if not row:
            return default
        return row[1]


class _WriteBuffer:
    def __init__(self):
        self._buf = BytesIO()

    def write(self, data):
        if data is None:
            return
        if isinstance(data, str):
            data = data.encode("utf-8", "replace")
        self._buf.write(data)

    def getvalue(self):
        return self._buf.getvalue()


def _http_status_phrase(code: int, fallback: str = "OK") -> str:
    try:
        return HTTPStatus(int(code)).phrase
    except Exception:
        return fallback


def _headers_from_environ(environ) -> _CaseInsensitiveHeaders:
    h = _CaseInsensitiveHeaders()
    for k, v in environ.items():
        if not k.startswith("HTTP_"):
            continue
        name = k[5:].replace("_", "-").title()
        h.add(name, v)
    if environ.get("CONTENT_TYPE"):
        h.add("Content-Type", environ.get("CONTENT_TYPE"))
    if environ.get("CONTENT_LENGTH"):
        h.add("Content-Length", environ.get("CONTENT_LENGTH"))
    if environ.get("REMOTE_ADDR"):
        h.add("X-Real-Ip", environ.get("REMOTE_ADDR"))
    if environ.get("wsgi.url_scheme"):
        h.add("X-Forwarded-Proto", environ.get("wsgi.url_scheme"))
    if environ.get("HTTP_HOST"):
        h.add("Host", environ.get("HTTP_HOST"))
    elif environ.get("SERVER_NAME"):
        host = environ.get("SERVER_NAME")
        port = environ.get("SERVER_PORT")
        if host and port:
            h.add("Host", f"{host}:{port}")
    return h


class WSGIHandler:
    def __init__(self, handler_class=H):
        self.handler_class = handler_class

    def __call__(self, environ, start_response):
        method = (environ.get("REQUEST_METHOD") or "GET").upper()
        if method not in ("GET", "POST"):
            payload = b"Method Not Allowed"
            start_response(
                "405 Method Not Allowed",
                [
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Content-Length", str(len(payload))),
                ],
            )
            return [payload]

        path = environ.get("PATH_INFO") or "/"
        qs = environ.get("QUERY_STRING") or ""
        full_path = f"{path}?{qs}" if qs else path

        body = b""
        try:
            ln = int((environ.get("CONTENT_LENGTH") or "0").strip() or "0")
            if ln > 0:
                body = environ["wsgi.input"].read(ln)
        except Exception:
            body = b""

        handler = self.handler_class.__new__(self.handler_class)
        handler.command = method
        handler.path = full_path
        handler.request_version = environ.get("SERVER_PROTOCOL", "HTTP/1.1")
        handler.requestline = f"{method} {full_path} {handler.request_version}"
        handler.client_address = (
            environ.get("REMOTE_ADDR", "0.0.0.0"),
            int(environ.get("REMOTE_PORT") or 0),
        )
        handler.server = type(
            "WSGIServerStub",
            (),
            {"server_name": environ.get("SERVER_NAME", "atlas"), "server_port": int(environ.get("SERVER_PORT") or 0)},
        )()
        handler.headers = _headers_from_environ(environ)
        handler.rfile = BytesIO(body)
        handler.wfile = _WriteBuffer()

        response = {"code": 200, "phrase": "OK", "headers": []}

        def _send_response(code, message=None):
            c = int(code)
            response["code"] = c
            response["phrase"] = str(message or _http_status_phrase(c, "OK"))

        def _send_header(key, value):
            response["headers"].append((str(key), str(value)))

        def _end_headers():
            return

        handler.send_response = _send_response
        handler.send_header = _send_header
        handler.end_headers = _end_headers

        try:
            if method == "GET":
                handler.do_GET()
            else:
                handler.do_POST()
        except Exception:
            payload = b"Internal Server Error"
            response["code"] = 500
            response["phrase"] = "Internal Server Error"
            response["headers"] = [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(payload)))]
            start_response("500 Internal Server Error", response["headers"])
            return [payload]

        payload = handler.wfile.getvalue()
        if not any(k.lower() == "content-length" for k, _ in response["headers"]):
            response["headers"].append(("Content-Length", str(len(payload))))

        status_line = f"{response['code']} {response['phrase']}"
        start_response(status_line, response["headers"])
        return [payload]


