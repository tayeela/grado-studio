"""Общие безопасные правила подготовки ресурсов релизной сборки."""

from pathlib import Path


SKIP_NAMES = {
    ".DS_Store", "style_overrides.json", ".autosave.json",
}
SKIP_PARTS = {
    ".git", ".hub", ".sources", ".tile_cache", "__pycache__",
    ".pytest_cache", "tests",
}


def data_files_for_tree(root, source, destination):
    """py2app data_files без локальных настроек, кэшей и Finder-мусора."""
    root = Path(root)
    source = root / source
    grouped = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if (path.is_symlink() or not path.is_file() or
                path.name in SKIP_NAMES or
                any(part in SKIP_PARTS for part in relative.parts) or
                path.suffix in {".pyc", ".pyo"} or
                path.name.startswith(".autosave.")):
            continue
        target = str(Path(destination) / relative.parent)
        grouped.setdefault(target, []).append(str(path))
    return [(target, files) for target, files in grouped.items()]
