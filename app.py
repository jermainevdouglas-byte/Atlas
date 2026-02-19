"""Experimental Flask scaffold for Atlas.

This module is intentionally non-production. The active runtime is the modular
BaseHTTPRequestHandler stack started via server.py / wsgi.py.
"""
from __future__ import annotations

import os
from flask import Flask, jsonify


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", os.getenv("SECRET_KEY", "change-me"))

    @app.get("/health")
    def health() -> tuple[dict, int]:
        return {
            "ok": True,
            "service": "atlas",
            "mode": "flask-scaffold",
            "active_runtime": "server.py -> atlas_app.http_handler",
        }, 200

    @app.get("/")
    def home_placeholder():
        return jsonify(
            {
                "ok": False,
                "message": "Flask scaffold only. Use server.py or wsgi.py for real Atlas runtime.",
            }
        ), 503

    @app.route("/login", methods=["GET", "POST"])
    def login_disabled():
        return jsonify(
            {
                "ok": False,
                "message": "Disabled in scaffold mode. Use the active runtime login endpoint.",
            }
        ), 410

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)

