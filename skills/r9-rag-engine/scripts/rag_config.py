"""Shared configuration for r9-rag-engine."""

from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
VENV_DIR = SKILL_DIR / ".venv"
PYTHON_BIN = VENV_DIR / "bin" / "python"

CONFIG_PATH = DATA_DIR / "config.json"
INDEX_PATH = DATA_DIR / "index.faiss"
METADATA_PATH = DATA_DIR / "metadata.jsonl"
STATE_PATH = DATA_DIR / "index_state.json"

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 100
DEFAULT_TOP_K = 5

# Sources to index
SKILLS_ROOT = Path.home() / ".kimi" / "skills"
OPC_ROOT = Path.home() / "OPC"
