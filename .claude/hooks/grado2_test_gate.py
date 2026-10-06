#!/usr/bin/env python3
"""Stop hook: ход, в котором менялась программа ГРАДО 2, не заканчивается, пока не пройдут тесты (владелец 06.10.2026,
задача #13, «А»; рекомендация Anthropic — проверка как жёсткие ворота, а не правило на словах).

Где смотреть: рабочая копия, в которой идёт сессия (`cwd` из данных хука), если это копия grado-studio (основная или
worktree). Если в ней есть незакоммиченные правки в apps/grado2 или core и их состояние ещё не проверялось —
запускается `tools/gate.sh` (без браузерных сценариев). Провал → ход блокируется с хвостом вывода. Повторный стоп в той
же цепочке (`stop_hook_active`) проходит всегда: хук не зацикливается. Прошедшее состояние запоминается — тот же код
второй раз не гоняется. Работа агентов в других рабочих копиях здесь не проверяется (их проверяет руководитель).
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
if data.get("stop_hook_active"):
    sys.exit(0)
cwd = Path(data.get("cwd") or ".")


def git(*a, root=cwd):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)


top = git("rev-parse", "--show-toplevel")
if top.returncode:
    sys.exit(0)
root = Path(top.stdout.strip())
if not (root / "tools" / "gate.sh").exists() or not (root / "apps" / "grado2").exists():
    sys.exit(0)                                   # не копия grado-studio
diff = git("diff", "HEAD", "--", "apps/grado2", "core", root=root).stdout
untracked = git("ls-files", "--others", "--exclude-standard", "--", "apps/grado2", "core", root=root).stdout
if not diff and not untracked:
    sys.exit(0)
digest = hashlib.sha256((git("rev-parse", "HEAD", root=root).stdout + diff + untracked).encode()).hexdigest()
mark = Path.home() / ".grado2" / "test_gate_passed"
passed = set(mark.read_text().split()) if mark.exists() else set()
if digest in passed:
    sys.exit(0)
r = subprocess.run(["bash", str(root / "tools" / "gate.sh")], cwd=root, capture_output=True, text=True, timeout=900)
out = (r.stdout + r.stderr).strip().splitlines()
if r.returncode == 0 and any("GATE: OK" in ln for ln in out):
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text("\n".join(list(passed)[-50:] + [digest]))
    sys.exit(0)
print("tools/gate.sh не прошёл для незакоммиченных правок в " + str(root) + ":\n" + "\n".join(out[-15:])
      + "\nИсправь и проверь снова (лог: /tmp/grado-gate).", file=sys.stderr)
sys.exit(2)
