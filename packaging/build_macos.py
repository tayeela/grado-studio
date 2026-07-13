#!/usr/bin/env python3
"""Build, sign, verify and package the macOS application as a DMG.

The default build uses an ad-hoc signature and is suitable for local testing.
Set ``MACOS_SIGN_IDENTITY`` to a Developer ID Application identity for a
distributable signed build.  If ``MACOS_NOTARY_PROFILE`` is also set, the DMG
is submitted with ``notarytool`` and stapled after approval.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple, Union


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP_NAME = "ГРАДО Студия.app"
APP = DIST / APP_NAME
OLD_CARBON_PATH = "/System/Library/Carbon.framework/Carbon"
CARBON_PATH = "/System/Library/Frameworks/Carbon.framework/Versions/A/Carbon"


def run(*args: Union[str, Path]) -> None:
    command = [str(arg) for arg in args]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def clean_previous_build() -> None:
    if APP.exists():
        shutil.rmtree(APP)
    for path in (ROOT / "build").glob("bdist.macosx-*"):
        if path.is_dir():
            shutil.rmtree(path)


def patch_argv_emulation(app: Path) -> None:
    """Use the versioned Carbon binary path present on current macOS.

    py2app 0.28.x generates an argv-emulation bootstrap that opens a removed
    compatibility symlink on macOS 26.  The framework itself is still present
    at its canonical versioned path.  Keeping argv emulation preserves Finder
    opening and drag-and-drop support for .grado files.
    """

    boot = app / "Contents" / "Resources" / "__boot__.py"
    source = boot.read_text(encoding="utf-8")
    if CARBON_PATH in source:
        return
    if OLD_CARBON_PATH not in source:
        raise RuntimeError("Unknown py2app argv-emulation bootstrap format")
    boot.write_text(source.replace(OLD_CARBON_PATH, CARBON_PATH), encoding="utf-8")


def sign_app(app: Path) -> Tuple[str, bool]:
    identity = os.environ.get("MACOS_SIGN_IDENTITY", "-").strip() or "-"
    signed_for_distribution = identity != "-"
    args = ["codesign", "--force", "--deep"]
    if signed_for_distribution:
        args.extend(["--options", "runtime", "--timestamp"])
    args.extend(["--sign", identity, str(app)])
    run(*args)
    run("codesign", "--verify", "--deep", "--strict", "--verbose=2", app)
    return identity, signed_for_distribution


def verify_bundle(app: Path, version: dict[str, object]) -> None:
    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        plist = plistlib.load(handle)
    expected = {
        "CFBundleIdentifier": "tech.tailink.grado-studio",
        "CFBundleShortVersionString": version["bundle_short_version"],
        "CFBundleVersion": version["bundle_version"],
    }
    for key, value in expected.items():
        if plist.get(key) != value:
            raise RuntimeError(f"{key}: expected {value!r}, got {plist.get(key)!r}")
    executable = app / "Contents" / "MacOS" / "ГРАДО Студия"
    output = subprocess.check_output(["lipo", "-archs", str(executable)], text=True)
    architectures = set(output.split())
    if architectures != {"arm64", "x86_64"}:
        raise RuntimeError(f"Expected universal2 executable, got: {output.strip()}")


def create_dmg(app: Path, version: str) -> Path:
    DIST.mkdir(exist_ok=True)
    dmg = DIST / f"GRADO-Studio-{version}-macOS-universal.dmg"
    if dmg.exists():
        dmg.unlink()
    with tempfile.TemporaryDirectory(prefix="grado-dmg-") as staging_raw:
        staging = Path(staging_raw)
        shutil.copytree(app, staging / APP_NAME, symlinks=True)
        (staging / "Applications").symlink_to("/Applications")
        run(
            "hdiutil", "create", "-volname", "ГРАДО Студия",
            "-srcfolder", staging, "-ov", "-format", "UDZO", dmg,
        )
    run("hdiutil", "verify", dmg)
    return dmg


def sign_dmg(dmg: Path, identity: str, signed_for_distribution: bool) -> None:
    if not signed_for_distribution:
        return
    run("codesign", "--force", "--timestamp", "--sign", identity, dmg)
    run("codesign", "--verify", "--verbose=2", dmg)


def notarize(dmg: Path, signed_for_distribution: bool) -> None:
    profile = os.environ.get("MACOS_NOTARY_PROFILE", "").strip()
    if not profile:
        return
    if not signed_for_distribution:
        raise RuntimeError("MACOS_NOTARY_PROFILE requires MACOS_SIGN_IDENTITY")
    run(
        "xcrun", "notarytool", "submit", dmg,
        "--keychain-profile", profile, "--wait",
    )
    run("xcrun", "stapler", "staple", dmg)
    run("xcrun", "stapler", "validate", dmg)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("The macOS build must run on macOS")
    version = json.loads(
        (ROOT / "apps" / "studio" / "web" / "version.json").read_text(
            encoding="utf-8"
        )
    )
    clean_previous_build()
    run(sys.executable, "packaging/py2app_setup.py", "py2app")
    patch_argv_emulation(APP)
    identity, signed_for_distribution = sign_app(APP)
    verify_bundle(APP, version)
    dmg = create_dmg(APP, str(version["version"]))
    sign_dmg(dmg, identity, signed_for_distribution)
    notarize(dmg, signed_for_distribution)
    print(f"DMG: {dmg}")
    print(f"SHA-256: {sha256(dmg)}")
    if not signed_for_distribution:
        print("Signature: ad-hoc (Gatekeeper warning is expected on another Mac)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
