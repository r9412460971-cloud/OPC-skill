"""Helper to ensure scripts run inside the r9-rag-engine virtual environment."""

import os
import subprocess
import sys
from pathlib import Path

from rag_config import PYTHON_BIN, VENV_DIR


def ensure_venv():
    """If not running inside the venv, re-execute the current script with venv python."""
    in_venv = (
        sys.prefix != sys.base_prefix
        or os.environ.get("VIRTUAL_ENV") == str(VENV_DIR)
    )
    if in_venv and Path(sys.executable).resolve() == PYTHON_BIN.resolve():
        return

    if not PYTHON_BIN.exists():
        print(f"Virtual env not found: {VENV_DIR}", file=sys.stderr)
        print("Please run setup.py first:", file=sys.stderr)
        print(f"  python3 {Path(__file__).parent / 'setup.py'}", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run([str(PYTHON_BIN), sys.argv[0]] + sys.argv[1:])
    sys.exit(result.returncode)
