#!/usr/bin/env python3
"""AtlasBahamas development server entrypoint."""
import os

from app import app


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=False)

