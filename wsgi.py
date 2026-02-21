"""WSGI entrypoint for Gunicorn using the modular BaseHTTPRequestHandler app."""
from atlasbahamas_app import core
from atlasbahamas_app.wsgi_adapter import WSGIHandler

# Run the same startup bootstrap used by server.py.
core.setup_logging()
core.bootstrap_files()
core.ensure_db()
if core.CLEAR_SESSIONS_ON_START:
    core.clear_active_sessions()

application = WSGIHandler()
app = application


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    with make_server("0.0.0.0", 8000, app) as httpd:
        print("Serving WSGI adapter on port 8000...")
        httpd.serve_forever()


