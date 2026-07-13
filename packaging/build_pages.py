"""Собрать статическую браузерную редакцию Студии для GitHub Pages."""

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).parents[1]
WEB = ROOT / "apps" / "studio" / "web"
TOP_LEVEL = (
    "app-transform.js", "app-snap.js", "app-data.js", "app-style-ui.js",
    "app-attr.js", "app.js", "app-import.js", "collab.js",
    "canvas-theme.js", "pages-adapter.js", "tokens.css", "style.css",
    "version.json", "icons.svg",
)
REDESIGN = ("shell.css", "studio2.css", "cmdk.js", "a11y.js")


def build_pages(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in TOP_LEVEL + ("index.html", "site.css", "site.js"):
        path = destination / name
        if path.exists():
            path.unlink()
    redesign = destination / "redesign"
    if redesign.exists():
        shutil.rmtree(redesign)

    for name in TOP_LEVEL:
        shutil.copy2(WEB / name, destination / name)
    redesign.mkdir()
    for name in REDESIGN:
        shutil.copy2(WEB / "redesign" / name, redesign / name)

    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/', 'href="./').replace('src="/', 'src="./')
    marker = '<script src="./canvas-theme.js"></script>'
    html = html.replace(marker, '<script src="./pages-adapter.js"></script>\n' + marker)
    (destination / "index.html").write_text(html, encoding="utf-8")
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build_pages(args.destination)


if __name__ == "__main__":
    main()
