#!/usr/bin/env python3
"""Markdown/PDF/DOCX text chunking for RAG."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Chunk:
    text: str
    source: str          # relative path from skills root or OPC root
    title: str = ""
    start_line: int = 0
    end_line: int = 0
    file_type: str = ""  # md, pdf, docx


def _clean_text(text: str) -> str:
    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_markdown(content: str, source: str, chunk_size: int = 800, overlap: int = 100) -> List[Chunk]:
    """Split markdown by headers, then by paragraphs if section is too long."""
    lines = content.split("\n")
    chunks: List[Chunk] = []

    # Build sections by header
    sections = []
    current_title = ""
    current_lines: List[str] = []
    header_stack: List[str] = []

    def close_section():
        if current_lines:
            sections.append((" / ".join(header_stack), current_lines.copy()))
            current_lines.clear()

    for i, line in enumerate(lines):
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if header_match:
            close_section()
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            # Adjust header stack
            header_stack = header_stack[: level - 1]
            header_stack.append(title)
            current_title = " / ".join(header_stack)
        else:
            current_lines.append(line)

    close_section()

    # Split each section into chunks
    for sec_title, sec_lines in sections:
        text = _clean_text("\n".join(sec_lines))
        if not text:
            continue

        # If whole section fits, keep it
        if len(text) <= chunk_size:
            chunks.append(Chunk(
                text=text,
                source=source,
                title=sec_title,
                file_type="md",
            ))
            continue

        # Otherwise split by paragraphs, keeping headers context
        paragraphs = text.split("\n\n")
        buffer = []
        buffer_len = 0

        def flush():
            if buffer:
                chunk_text = _clean_text("\n\n".join(buffer))
                if chunk_text:
                    chunks.append(Chunk(
                        text=chunk_text,
                        source=source,
                        title=sec_title,
                        file_type="md",
                    ))

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if buffer_len + len(para) > chunk_size and buffer:
                flush()
                # Keep overlap
                buffer = []
                overlap_len = 0
                for p in reversed(buffer):
                    if overlap_len + len(p) > overlap:
                        break
                    buffer.insert(0, p)
                    overlap_len += len(p)
                buffer_len = sum(len(p) for p in buffer)
            buffer.append(para)
            buffer_len += len(para) + 2

        flush()

    return chunks


def chunk_plain_text(content: str, source: str, title: str = "", chunk_size: int = 800, overlap: int = 100) -> List[Chunk]:
    """Generic paragraph-based chunking for PDF/DOCX text."""
    content = _clean_text(content)
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    chunks: List[Chunk] = []
    buffer = []
    buffer_len = 0

    def flush():
        if buffer:
            chunk_text = _clean_text("\n\n".join(buffer))
            if chunk_text:
                chunks.append(Chunk(
                    text=chunk_text,
                    source=source,
                    title=title,
                    file_type="txt",
                ))

    for para in paragraphs:
        if buffer_len + len(para) > chunk_size and buffer:
            flush()
            buffer = []
            overlap_len = 0
            for p in reversed(buffer):
                if overlap_len + len(p) > overlap:
                    break
                buffer.insert(0, p)
                overlap_len += len(p)
            buffer_len = sum(len(p) for p in buffer)
        buffer.append(para)
        buffer_len += len(para) + 2

    flush()
    return chunks


def extract_pdf_text(path: Path) -> str:
    try:
        import fitz
        doc = fitz.open(str(path))
        parts = []
        for page in doc:
            text = page.get_text().strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts)
    except Exception as e:
        return f"[Error reading PDF {path}: {e}]"


def extract_docx_text(path: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(path))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        return f"[Error reading DOCX {path}: {e}]"
