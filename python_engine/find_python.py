# -*- coding: utf-8 -*-
import os
import shutil
import sys
from pathlib import Path

def find_python() -> str | None:
    repo_root = Path(__file__).resolve().parent.parent
    candidates = [
        repo_root / "python_engine" / "venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python"),
        repo_root / "python_engine" / "portable" / ("python.exe" if os.name == "nt" else "python"),
        repo_root / "python_engine" / "portable" / ("Python.exe" if os.name == "nt" else "python"),
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    for name in ("python3", "python", "py"):
        resolved = shutil.which(name)
        if resolved:
            return resolved

    return None

def main() -> int:
    python_path = find_python()
    if python_path is None:
        print("PYTHON_NOT_FOUND", file=sys.stderr)
        return 1
    print(python_path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())