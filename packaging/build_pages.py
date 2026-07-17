"""Собрать статическую браузерную редакцию Студии для GitHub Pages."""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
WEB = ROOT / "apps" / "studio" / "web"
TOP_LEVEL = (
    "app-transform.js", "app-snap.js", "app-data.js", "app-style-ui.js",
    "app-attr.js", "app.js", "app-import.js", "collab.js",
    "canvas-theme.js", "crs.js", "pages-core.js", "pages-adapter.js", "tokens.css", "style.css",
    "version.json", "icons.svg", "favicon.svg",
)
REDESIGN = ("shell.css", "studio2.css", "cmdk.js", "a11y.js")


def build_pages(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in TOP_LEVEL + ("index.html", "site.css", "site.js", "styles.json"):
        path = destination / name
        if path.exists():
            path.unlink()
    redesign = destination / "redesign"
    if redesign.exists():
        shutil.rmtree(redesign)

    for name in TOP_LEVEL:
        shutil.copy2(WEB / name, destination / name)
    studio_path = str(ROOT / "apps" / "studio")
    if studio_path not in sys.path:
        sys.path.insert(0, studio_path)
    import studio_core
    active_overrides = studio_core.current_style_overrides()
    try:
        studio_core.apply_style_overrides({})
        base_styles = studio_core.frontend_styles()
    finally:
        studio_core.apply_style_overrides(active_overrides)
    (destination / "styles.json").write_text(
        json.dumps(base_styles, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    redesign.mkdir()
    for name in REDESIGN:
        shutil.copy2(WEB / "redesign" / name, redesign / name)

    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/', 'href="./').replace('src="/', 'src="./')
    release = json.loads((WEB / "version.json").read_text(encoding="utf-8"))[
        "bundle_version"
    ]
    marker = '<script src="./canvas-theme.js"></script>'
    # Авто-обновление: index.html на GitHub Pages кэшируется браузером (~10 мин),
    # из-за чего мягкий reload подтягивает СТАРЫЙ app.js даже при свежем ?v=.
    # Ранний скрипт сверяет version.json (no-store) с запечённой версией сборки и,
    # если страница устарела, один раз переходит на свежий URL (?b=<version> —
    # новый ключ кэша ⇒ гарантированный чистый index.html). Петли нет: свежий
    # index.html уже совпадает по версии, а повтор гасится проверкой ?b.
    selfheal = (
        '<script>(function(){try{var B="' + str(release) + '";'
        'fetch("./version.json?ts="+Date.now(),{cache:"no-store"})'
        '.then(function(r){return r.json();}).then(function(v){'
        'var L=v&&String(v.bundle_version);'
        'if(L&&L!==B){var u=new URL(location.href);'
        'if(u.searchParams.get("b")!==L){u.searchParams.set("b",L);'
        'location.replace(u.toString());}}}).catch(function(){});'
        '}catch(e){}})();</script>'
    )
    # Правила маршрутизации ОГД — из ОДНОГО источника (studio_core), а не копией
    # в pages-core.js: копия расходилась (веб застрял на beta.60 — без корня
    # «берегов», без «ё»-нормализации, без гейта правовых актов). Теперь правка
    # правила на сервере доезжает до браузерной редакции сама.
    try:
        sys.path.insert(0, str(ROOT / "apps" / "studio"))
        import studio_core as _sc
        _rules = json.dumps(_sc.gisogd_frontend_rules(), ensure_ascii=False)
        rules_js = f'<script>window.__GRADO_GISOGD_RULES__={_rules};</script>\n'
    except Exception as exc:                      # не роняем сборку из-за правил
        print(f"  ВНИМАНИЕ: правила ОГД не впечены ({exc}) — браузер возьмёт свои")
        rules_js = ''
    html = html.replace(
        marker,
        selfheal + '\n' + rules_js +
        f'<script>window.__GRADO_ASSET_VERSION__="{release}";</script>\n'
        '<script src="./pages-core.js"></script>\n'
        '<script src="./pages-adapter.js"></script>\n' + marker,
    )
    html = re.sub(
        r'((?:href|src)="\./[^"?#]+)(")',
        rf'\1?v={release}\2',
        html,
    )
    (destination / "index.html").write_text(html, encoding="utf-8")
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build_pages(args.destination)


if __name__ == "__main__":
    main()
