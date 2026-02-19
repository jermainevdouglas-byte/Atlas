#!/usr/bin/env python3
"""Atlas entrypoint (modular)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
os.environ.setdefault("DATABASE_PATH", str(ROOT_DIR / "data" / "atlas.sqlite"))
os.environ.setdefault("LOG_DIR", str(ROOT_DIR / "data" / "logs"))
os.environ.setdefault("UPLOAD_DIR", str(ROOT_DIR / "data" / "uploads"))

from atlas_app.core import main

if __name__ == "__main__":
    main()

