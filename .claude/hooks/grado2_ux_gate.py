#!/usr/bin/env python3
"""Stop hook: Claude may not finish a turn that changed ГРАДО 2 until it has audited the result.

The state of apps/grado2 (committed tree + uncommitted diff) is hashed. When the hash differs
from the last audited one, the stop is blocked once with the audit instructions from
docs/ux/grado2-ux.md. The second stop in the same chain (stop_hook_active) always passes,
so the hook cannot loop.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
if data.get("stop_hook_active"):
    sys.exit(0)
root = Path(__file__).resolve().parents[2]
git = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True).stdout
state = git("rev-parse", "HEAD:apps/grado2") + git("diff", "HEAD", "--", "apps/grado2") + git("status", "--porcelain", "--", "apps/grado2")
digest = hashlib.sha256(state.encode()).hexdigest()
mark = root / ".claude" / ".grado2_ux_audited"
if mark.exists() and mark.read_text().strip() == digest:
    sys.exit(0)
mark.write_text(digest)
print(json.dumps({"decision": "block", "reason": (
    "ГРАДО 2 changed since the last UX audit. Before finishing:\n"
    "1. Open the grado2 preview and walk the scenarios in docs/ux/grado2-ux.md as the owner would "
    "(an urban planner, not a programmer). Check the console for errors.\n"
    "2. List what is unclear, awkward or broken, judged by the principles in that file.\n"
    "3. Fix what is small; add the rest to the queue section of that file.\n"
    "4. Tell the owner in two or three lines what you found and what you fixed.")}))
