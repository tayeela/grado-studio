#!/usr/bin/env python3
"""PostToolUse hook: after Claude edits a ГРАДО 2 file, check that it still parses.

JS goes through `node --check`, Python through py_compile. A failure exits with code 2,
so Claude Code shows the error to Claude right away instead of letting a broken file sit.
"""
import json
import py_compile
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
path = Path((data.get("tool_input") or {}).get("file_path") or "")
if "apps/grado2" not in path.as_posix() or not path.exists():
    sys.exit(0)
err = ""
if path.suffix == ".js":
    r = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    err = r.stderr.strip() if r.returncode else ""
elif path.suffix == ".py":
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as e:
        err = str(e)
if err:
    print(f"{path.name} does not parse:\n{err}", file=sys.stderr)
    sys.exit(2)
