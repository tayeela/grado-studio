#!/usr/bin/env python3
"""Stop hook: Claude may not finish a turn that changed ГРАДО 2 until it has audited the result.

The state of apps/grado2 (committed tree + uncommitted diff) is hashed. When the hash differs
from the last audited one, the stop is blocked once with the audit instructions from
docs/ux/grado2-ux.md. The second stop in the same chain (stop_hook_active) always passes.

The audit itself edits files, which used to change the hash and block the next stop again.
Within COOLDOWN_S of the last block those edits are absorbed into the mark and the stop passes.
"""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

COOLDOWN_S = 3 * 3600

data = json.load(sys.stdin)
if data.get("stop_hook_active"):
    sys.exit(0)
root = Path(__file__).resolve().parents[2]
git = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True).stdout
state = git("rev-parse", "HEAD:apps/grado2") + git("diff", "HEAD", "--", "apps/grado2") + git("status", "--porcelain", "--", "apps/grado2")
digest = hashlib.sha256(state.encode()).hexdigest()
mark = root / ".claude" / ".grado2_ux_audited"
prev, blocked_at = "", 0.0
if mark.exists():
    parts = mark.read_text().split()
    prev = parts[0] if parts else ""
    if len(parts) > 1:
        try:
            blocked_at = float(parts[1])
        except ValueError:
            blocked_at = 0.0
if prev == digest:
    sys.exit(0)
now = time.time()
if blocked_at and now - blocked_at < COOLDOWN_S:
    mark.write_text(f"{digest} {blocked_at}\n")
    sys.exit(0)
mark.write_text(f"{digest} {now}\n")
print(json.dumps({"decision": "block", "reason": (
    "ГРАДО 2 changed since the last UX audit. Before finishing, do this yourself in this session. "
    "Do not start a workflow and do not spawn subagents for this audit.\n"
    "1. Open the grado2 preview and walk the scenarios in docs/ux/grado2-ux.md that touch what changed "
    "(not all of them; owner 06.10.2026, «А»), as the owner would (an urban planner, not a programmer). "
    "Check the console for errors. A browser check already done in this session for this change counts.\n"
    "2. List what is unclear, awkward or broken, judged by the principles in that file.\n"
    "3. Fix what is small; add the rest to the queue section of that file.\n"
    "4. Tell the owner in two or three lines what you found and what you fixed.")}))
