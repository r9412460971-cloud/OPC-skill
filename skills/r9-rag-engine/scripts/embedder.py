#!/usr/bin/env python3
"""Embedding model wrapper. Runs inside the isolated venv."""

import json
import os
import sys
from pathlib import Path

from rag_config import DEFAULT_MODEL

os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # Model is pre-downloaded by setup.py
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(DEFAULT_MODEL)


def encode_texts(texts: list, batch_size: int = 32, show_progress: bool = False):
    model = get_model()
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
        normalize_embeddings=True,  # Normalize for cosine similarity
    )


def encode_query(query: str):
    model = get_model()
    return model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0]


def cli_encode():
    """Read texts from stdin (JSON list) and output embeddings as JSON."""
    texts = json.load(sys.stdin)
    embeddings = encode_texts(texts, show_progress=False)
    result = {
        "embeddings": embeddings.tolist(),
        "dimension": embeddings.shape[1],
    }
    print(json.dumps(result))


if __name__ == "__main__":
    cli_encode()
