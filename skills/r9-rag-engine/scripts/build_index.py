#!/usr/bin/env python3
"""Build the vector index for R9 skills. Performs a full rebuild each run."""

import json
import sys
import time
from pathlib import Path
from typing import List

from _venv_helper import ensure_venv
ensure_venv()

import faiss
import numpy as np

from chunker import (
    Chunk,
    chunk_markdown,
    chunk_plain_text,
    extract_docx_text,
    extract_pdf_text,
)
from embedder import encode_texts
from rag_config import (
    CONFIG_PATH,
    DATA_DIR,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MODEL,
    INDEX_PATH,
    METADATA_PATH,
    OPC_ROOT,
    SKILLS_ROOT,
)


def discover_markdown_files(root: Path) -> List[Path]:
    files = []
    if not root.exists():
        return files
    for skill_dir in root.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_name = skill_dir.name
        if skill_name == "r9-rag-engine":
            continue
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            files.append(skill_md)
        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            for ref_file in refs_dir.iterdir():
                if ref_file.is_file() and ref_file.suffix.lower() in (".md", ".txt"):
                    files.append(ref_file)
    return files


def discover_opc_files(root: Path) -> List[Path]:
    files = []
    if not root.exists():
        return files
    for ext in (".pdf", ".docx"):
        files.extend(root.rglob(f"*{ext}"))
    return files


def source_for(path: Path) -> str:
    """Return a stable relative source string."""
    try:
        return str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def chunk_file(path: Path, chunk_size: int, overlap: int) -> List[Chunk]:
    source = source_for(path)
    suffix = path.suffix.lower()

    if suffix in (".md", ".txt"):
        content = path.read_text(encoding="utf-8", errors="ignore")
        return chunk_markdown(content, source, chunk_size, overlap)

    if suffix == ".pdf":
        text = extract_pdf_text(path)
        return chunk_plain_text(text, source, title=path.name, chunk_size=chunk_size, overlap=overlap)

    if suffix == ".docx":
        text = extract_docx_text(path)
        return chunk_plain_text(text, source, title=path.name, chunk_size=chunk_size, overlap=overlap)

    return []


def build_index(chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_files = discover_markdown_files(SKILLS_ROOT) + discover_opc_files(OPC_ROOT)
    print(f"Discovered {len(all_files)} files to index.")

    all_chunks: List[Chunk] = []
    for path in all_files:
        try:
            chunks = chunk_file(path, chunk_size, overlap)
            all_chunks.extend(chunks)
            print(f"  + {path.name}: {len(chunks)} chunks")
        except Exception as e:
            print(f"  ! Error processing {path}: {e}")

    if not all_chunks:
        print("No chunks to index.")
        return

    texts = [c.text for c in all_chunks]
    print(f"\nEncoding {len(texts)} chunks with {DEFAULT_MODEL}...")
    vectors = encode_texts(texts, batch_size=32, show_progress=True)
    dimension = vectors.shape[1]

    print(f"Building FAISS index (dim={dimension})...")
    index = faiss.IndexFlatIP(dimension)  # Inner product = cosine for normalized vectors
    index.add(vectors.astype(np.float32))
    faiss.write_index(index, str(INDEX_PATH))

    metadata = [
        {
            "text": c.text,
            "source": c.source,
            "title": c.title,
            "file_type": c.file_type,
        }
        for c in all_chunks
    ]
    METADATA_PATH.write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in metadata) + "\n",
        encoding="utf-8",
    )

    config = {
        "model": DEFAULT_MODEL,
        "dimension": dimension,
        "chunk_size": chunk_size,
        "overlap": overlap,
        "total_chunks": len(metadata),
        "last_build": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nIndex saved: {INDEX_PATH}")
    print(f"Metadata saved: {METADATA_PATH}")
    print(f"Total chunks: {len(metadata)}")


if __name__ == "__main__":
    build_index()
