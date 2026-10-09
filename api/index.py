import sys
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path para Vercel Serverless
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app

__all__ = ["app"]
