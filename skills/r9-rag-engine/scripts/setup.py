#!/usr/bin/env python3
"""Setup isolated environment and download embedding model for r9-rag-engine."""

import subprocess
import sys
import venv
from pathlib import Path

from rag_config import VENV_DIR, DEFAULT_MODEL

REQUIREMENTS = [
    "sentence-transformers>=3.0.0",
    "faiss-cpu>=1.8.0",
    "numpy>=1.24.0",
    "PyMuPDF>=1.23.0",
    "python-docx>=1.1.0",
    "tqdm>=4.66.0",
]


def create_venv():
    if VENV_DIR.exists():
        print(f"Virtual env already exists: {VENV_DIR}")
        return
    print(f"Creating virtual env: {VENV_DIR}")
    venv.create(VENV_DIR, with_pip=True)


def install_deps():
    python = VENV_DIR / "bin" / "python"
    print("Installing dependencies...")
    subprocess.check_call(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        stdout=subprocess.DEVNULL,
    )
    subprocess.check_call(
        [str(python), "-m", "pip", "install"] + REQUIREMENTS,
    )
    print("Dependencies installed.")


def download_model():
    python = VENV_DIR / "bin" / "python"
    print(f"Downloading embedding model: {DEFAULT_MODEL}")
    script = f"""
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('{DEFAULT_MODEL}')
print('Model cached at:', model.get_sentence_embedding_dimension())
"""
    subprocess.check_call([str(python), "-c", script])
    print("Model ready.")


def main():
    create_venv()
    install_deps()
    download_model()
    print("\nSetup complete. Run build_index.py to create the vector index.")


if __name__ == "__main__":
    main()
