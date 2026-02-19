"""Primary WSGI entrypoint for AtlasBahamas Flask runtime."""
from app import app as application

app = application


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    with make_server("0.0.0.0", 8000, app) as httpd:
        print("Serving AtlasBahamas WSGI app on port 8000...")
        httpd.serve_forever()

