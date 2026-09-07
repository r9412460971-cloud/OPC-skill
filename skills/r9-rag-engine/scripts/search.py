#!/usr/bin/env python3
"""CLI search tool. Auto-runs inside the r9-rag-engine venv if not already there."""

import sys

from _venv_helper import ensure_venv

if __name__ == "__main__":
    ensure_venv()

    from rag_api import format_results, search

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "基金回撤安抚话术"
    results = search(query, top_k=5)
    print(format_results(results))
