"""ГРАДО 2 · модуль Rust (grado_rs) ставится сам: при запуске сервера, если модуля нет или он не той версии, колесо
нужной версии скачивается из релиза GitHub `grado-rs-v<WANT>` (его собирает CI `rust.yml`: macOS arm64 и x86_64,
Windows, Linux сайта) и ставится pip в то же окружение, фоном — запуск не ждёт; не вышло — ещё раз через 30 минут. Нет сети, нет релиза, pip не смог —
одна строка в журнал, программа работает на Python, как раньше (план 08.11.2026, шаг 1).
Зовёт server.main(); GRADO_RS_AUTO=0 — не ставить; собранная программа (py2app, PyInstaller) — не ставит.
Свой релиз для проверки — GRADO_RS_RELEASE (адрес API релиза GitHub). Проверяет tests/test_rs_wheel.py."""
import importlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

WANT = "0.1.0"                                  # = version в rust/crates/py/Cargo.toml (сверяет тест)
REPO = "tayeela/grado-studio"
TAG = f"grado-rs-v{WANT}"
API = f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}"
LOCK = Path.home() / ".grado2" / "grado_rs.lock"  # сайт: две копии (grado, grado-guest) на одном venv — ставит одна
LOCK_STALE = 15 * 60
TRIES = 3                                       # ≤ 3 попыток с паузой (правило порталов, #51)
AGAIN = 30 * 60                                 # фоном: не вышло (релиз ещё собирается после выкладки) — ещё раз через 30 мин
ROUNDS = 6                                      # … и не больше 6 раз за запуск


def installed():
    """Версия установленного grado_rs или None."""
    try:
        import grado_rs
        return getattr(grado_rs, "__version__", "?")
    except ImportError:
        return None


def status():
    """Для /api/health: {"grado_rs": версия или None, "want": WANT}."""
    return {"grado_rs": installed(), "want": WANT}


def _ctx():
    """HTTPS с python.org Python на Mac: корни certifi (железное правило 4), проверку не выключаем."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get(url, accept="application/octet-stream"):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "grado2-rs-wheel"})
    last = None
    for i in range(TRIES):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:
                return r.read()
        except Exception as e:               # noqa: BLE001 — сеть: любая ошибка = следующая попытка
            last = e
            if getattr(e, "code", None) == 404:
                break
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def wheel_urls(api=None):
    """Адреса колёс grado_rs в релизе: [(имя, адрес)]."""
    rel = json.loads(_get(api or os.environ.get("GRADO_RS_RELEASE") or API, "application/vnd.github+json"))
    return [(a["name"], a["browser_download_url"]) for a in rel.get("assets", [])
            if a.get("name", "").startswith("grado_rs-") and a["name"].endswith(".whl")]


def _lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime > LOCK_STALE:
            LOCK.unlink()
        os.close(os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except OSError:
        return False


def install(python=None, api=None, log=print):
    """Скачать колёса релиза и поставить подходящее pip (pip сам выбирает колесо под систему). True — стоит нужная версия."""
    if installed() == WANT:
        return True
    if not _lock():
        log("ГРАДО 2: модуль Rust уже ставит другая копия программы")
        return False
    tmp = Path(tempfile.mkdtemp(prefix="grado_rs-"))
    try:
        urls = wheel_urls(api)
        if not urls:
            raise RuntimeError(f"в релизе {TAG} нет колёс")
        for name, url in urls:
            (tmp / Path(name).name).write_bytes(_get(url))
        r = subprocess.run([python or sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                            "--no-index", "--find-links", str(tmp), "--upgrade", f"grado_rs=={WANT}"],
                           capture_output=True, text=True, timeout=300)
        if r.returncode:
            raise RuntimeError(((r.stderr or r.stdout).strip().splitlines() or ["pip не смог"])[-1])
        importlib.invalidate_caches()
        log(f"ГРАДО 2: модуль Rust grado_rs {WANT} установлен — карты печати рисуются на Rust"
            + (" после перезапуска" if installed() not in (None, WANT) else ""))
        return True
    except Exception as e:                   # noqa: BLE001 — любая неудача = работаем на Python
        log(f"ГРАДО 2: модуль Rust не поставился ({e}) — работаю на Python, как раньше")
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            LOCK.unlink()
        except OSError:
            pass


def ensure_background(frozen=False):
    """Фоном поставить grado_rs, если нужно. None — ставить не надо или нельзя; иначе поток."""
    if frozen or os.environ.get("GRADO_RS_AUTO", "").strip() == "0" or installed() == WANT:
        return None
    def run():
        for i in range(ROUNDS):
            if install(log=lambda m: print(m, flush=True)) or i == ROUNDS - 1:
                return
            time.sleep(AGAIN)
    t = threading.Thread(target=run, name="grado_rs", daemon=True)
    t.start()
    return t
