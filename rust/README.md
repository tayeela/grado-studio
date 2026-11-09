# grado-rust — ядро ГРАДО на Rust

Перевод ядра с Python на Rust (стратегия «удушающей змеи»: Rust подменяет Python по частям,
Python-версия остаётся эталоном и запасным путём). Начат агентом zcode на Mac владельца
(05–06.11.2026, вне git), перенесён в репозиторий 08.11.2026. Workspace из пяти крейтов:

- **`crates/compute`** (`grado_compute_rs`) — порт `core/compute` (ТЭП-движок),
  сверен с Python-эталоном **бит-в-бит**;
- **`crates/geom`** (`grado_geom_rs`) — порт `core/geom` (геометрическое ядро),
  сверен с Python-эталоном **по допуску** (см. ниже — почему не бит-в-бит);
- **`crates/plate`** (`grado_plate`) — пластина карты: список операций рендера печати (path, circle,
  clip, image, мм листа) → картинка заданного dpi на tiny-skia; тексты не растрируются (см. «Пластина карты»);
- **`crates/symbol`** (`grado_symbol`) — слои знака (план 08.11.2026, шаг 3): части стиля `parts` (линия,
  полоса внутрь, штриховка, значки вдоль со стороной) → операции рендера. Один код для печати (`grado_rs.parts_ops` →
  `apps/grado2/symparts.py` → пластина/PDF) и экрана (WebAssembly `apps/grado2/ui/src/wasm`, собирает
  `tools/build_symbol_wasm.sh`; `ui/src/symbology.js partStyles`). Сверка с Python-эталоном — `tests/test_symparts.py`
  (те же операции; полоса — та же картинка), `ui/src/symbolwasm.test.js`; типы линий ЛГР (REDLN97) — `linetype.rs`
  (`print_io.linetype_ops` и `symbology.js drawLt`);
- **`crates/py`** (`grado_rs`) — модуль Python (PyO3, abi3 ≥ 3.10): ТЭП-движок на Rust
  с API `grado_compute.Engine`; включается `GRADO_COMPUTE=rust` (см. «Мост в Python»);
  `render_plate(ops_json, w_mm, h_mm, dpi)` — пластина карты; `parts_ops(kind, shapes, parts, px_mm)` — слои знака (0.2.0); `LineLib(lib_json).ops(pts, name, k, color, width, shape_k)` — типы линий ЛГР REDLN97 (0.3.0).

## Мост в Python — статус (шаг 1 «змеи»)

| Что | Состояние |
|---|---|
| `grado_rs.ComputeEngine` (set_input/set_inputs/set_constants/value/display/results/eval_counts/raw_values) | готов |
| Обёртка `core/compute/grado_compute/rust_backend.py` (`RustEngine`) | готова: те же атрибуты `preset/title/inputs/constants/metrics`, те же классы ошибок (PresetError, KeyError, ExpressionError, ZeroDivisionError) |
| Выбор движка | `grado_compute.Engine` = Python по умолчанию; `GRADO_COMPUTE=rust` и установлен `grado_rs` → Rust (`grado_compute.BACKEND`); нет модуля — предупреждение и Python |
| Сверка | `core/compute/tests/test_rust_backend.py`: 9 сценариев + 200 случайных наборов входов + типы + ошибки; весь набор `core/compute/tests` зелёный и при `GRADO_COMPUTE=rust` |
| Ошибка вычисления в Rust | раньше `expect` (паника), теперь ошибка с видом → исключение Python, как в эталоне |
| Колёса для Mac/Windows/сайта | CI `rust.yml` (`wheels` + `release`) на каждый пуш в main с правкой Rust: релиз GitHub `grado-rs-v<версия>`; программа ставит колесо сама при запуске (`apps/grado2/rs_wheel.py`, v0.99.137), `/api/health` показывает `grado_rs`. Правка модуля = новая `version` в `crates/py/Cargo.toml` и `WANT` в `rs_wheel.py` |

## Пластина карты (plate) — статус

Цель (концепция ГРАДО 3, 08.11.2026): одна картинка карты для экрана, PDF и PPTX — что видно на листе, то и в выдаче;
подписи и легенда остаются векторными (редактируемыми) поверх.

| Что | Состояние |
|---|---|
| Операции | `path` (заливка с alpha, контур, штрих, по чётности/ненулевое, скруглённое соединение), `circle`, `clip` (прямоугольник, кольца) / `unclip`, `image` (JPEG или PNG в прямоугольник или параллелограмм — плитки подложки и их куски); фон белый или прозрачный (`transparent`); `text`, `layer` — пропуск |
| Вход | ровно те операции, что `print_io.SketchMapFrame` отдаёт PDF/SVG/PPTX-бэкендам (`layout_io.map_plate`, `plate_ops_json`) |
| В программе | `POST /api/print/map_png` (тело как у `map_svg`, плюс `dpi`, по умолчанию 300): PNG, заголовки `X-Plate-Ink` (доля закраски — пустая карта ≈ 0) и `X-Plate-Ops` (нарисовано/пропущено). Без grado_rs — 501, остальная печать как раньше |
| Сверка | `parity/plate/dump.py` + `compare.mjs`: 3 сцены образца (1:1000, 1:2000, 1:5000; заливки, прозрачность, штриховка сеткой и своим цветом, штрих, линии, точки) против того же списка операций, растрированного Chromium из SVG: средняя разница 0,2–1,1 из 255, сильно разных пикселей ≤ 0,07 % |
| Скорость | карта блока 270×224 мм при 300 dpi — меньше 0,1 с |
| Лист «Макета листа» | с grado_rs карта блока в PDF — пластиной PNG 300 dpi в рамке блока, подписи — текстом поверх в обрезке рамки (`layout_io._plated`); `GRADO_PLATE=0` — векторно, как раньше. Пустая карта (закраска < 0,2 %) — `X-Empty-Maps`, окно листа пишет «карта пустая» |
| Альбом | PDF альбома — по-прежнему векторный (байты PDF с grado_rs и без совпадают). Пустая карта альбома (ни снимка, ни закраски на пластине 40 dpi < 0,2 %) — пометка «не готов» на листе (`print_io.map_is_empty`, `EMPTY_MAP_NOTE`). PPTX: тяжёлая карта слайда (больше 20 тыс. фигур) — растром пластины 200 dpi с прозрачным фоном вместо прежнего растра PIL (`print_io.pptx_rasterize`): в 2–2,7 раза быстрее, к векторному PDF ближе (сглаженная разница 2,1 против 2,9 и 5,7 против 7,1 из 255) |
| Не сделано | пластина в PDF альбома — после пересборки настоящих альбомов и сверки album_check на Mac; колесо внутри собранных установщиков (py2app, PyInstaller) |

## compute — статус

| Что | Состояние |
|---|---|
| Порт `expressions.py` (безопасный вычислитель выражений) | готов, семантика Python: bigint, `//`/`%` напольные, `**` с пределами |
| Порт `engine.py` (граф метрик, топосортировка, пересчёт) | готов, порядок результатов идентичен |
| `round_half_up` (Decimal(repr(x)) в Python) | готов, по цифрам кратчайшего repr: 2.675 → 2.68, 0.145 → 0.15 |
| Тесты из `core/compute/tests` | портированы 21 шт., зелёные (`cargo test`) |
| Сверка с Python (10 сценариев: 2 пресета, Якиманка, зоны, константы) | `parity/compare.py`: результаты, все сырые значения (repr) и eval_counts идентичны |
| Скорость | ~246 тыс. пересчётов/с против ~2,9 тыс. у Python — **84×** |
| CLI | `--preset`, `--set ID=ЗНАЧ`, `--const ID=ЗНАЧ`, `--json`, `dump`, `bench` |

Ключевые ловушки порта (решены): `round(290.84, 6)` — масштаб от последней
фактической цифры; `0.145 → 0.15` — округление только по десятичной записи
repr(x); `min/max/clamp` возвращают операнд-победитель; напольные `//`/`%`;
`-2**2 = -4`.

## geom — статус

| Модуль Python | Rust | Сверка с Python |
|---|---|---|
| `affine.py` (поворот, масштаб, зеркало) | `src/affine.rs` | тесты + паритет |
| `curves.py` (дуги, линеаризация, схемы кривых) | `src/curves.rs` | тесты + паритет |
| `path.py` (пикетаж, сопряжения, офсеты, miter) | `src/path.rs` | тесты + паритет |
| `overlay.py` (площадь ∪∩ через GEOS) | `src/overlay.rs` | тесты + паритет, см. «чем заменён GEOS» |
| `snap.py` (привязки через STRtree) | `src/snap.rs` (R-дерево `rstar`) | тесты + паритет |
| `coverage.py` (топологическое покрытие зон) | `src/coverage.rs` | тесты + паритет |
| Тесты `core/geom/tests` (3 файла) | `tests/geom_tests.rs` | 36/36 зелёные |

Паритет: `parity/geom/` — 36 сценариев (10 overlay, 4 snap, 7 coverage,
6 path, 4 arc, 5 тесселяция), дампы Python (`dump_reference_geom.py`) и Rust
(`run_rs_dumps.py`), сравнение `compare.py` с допуском rel 1e-9 / abs 1e-12 —
**СВЕРКА СХОДИТСЯ**, максимальное относительное расхождение ~7e-9 (на
градусных координатах; в абсолюте ~3.5e-13 кв. градусов).

### Чем заменён GEOS/shapely

- **`overlay`** — свой планарный движок: все кольца вместе нодятся (рёбра
  делятся во всех пересечениях), для каждого подребра статус «внутри
  (∪ regions) ∩ (∪ clips)» вычисляется слева/справа (чётность точки по
  каждому кольцу — PNPOLY; полигон — внешнее кольцо нечётно, дыры чётны;
  группа — ИЛИ по полигонам, дубли не гасятся), вклад по теореме Грина —
  только у подрёбер-границ. Совпадающие подрёбра (общие границы, дубли)
  дедуплицируются — вклад границы считается один раз. Точность f64 без
  квантования; попытка использовать крейт `geo` (BooleanOps) дала ~1e-8
  относительной ошибки на T-стыках в градусных координатах — заменено.
- **`snap`** — `rstar` (R-дерево) вместо STRtree; пересечения отрезков и
  ближайшая точка — своя аналитика, повторяющая семантику GEOS (перекрытие
  коллинеарных — не точка, касание — точка).
- **`coverage`** — хранение рёбер своё, как в эталоне; площади — формула
  шнурков; `coverage_is_valid` заменён парными пересечениями граней
  (крейт `geo`) и балансом площадей. Ограничение: экзотическая комбинация
  «нахлёст + щель, компенсирующие друг друга» ловится балансом, но не
  парной проверкой — конструктивно невозможна при сборке из совпадающих
  цепочек вершин.

### Честная граница точности (почему допуск, а не бит-в-бит)

- `hypot` у CPython собственный компенсированный алгоритм, у Rust — libm:
  расхождение до пары ulp в длинах и дистанциях.
- GEOS-предикаты точные (адаптивная арифметика), здесь — f64: точки
  пересечений могут расходиться с GEOS в последних битах.
- `round(x, 9)` (нормализация узлов покрытия) сверена с CPython
  **бит-в-бит** на 150 тыс. значений — форматирование Rust корректно
  округляет точное бинарное значение так же, как Gay's dtoa.
- Python-семантика воспроизведена: `py_mod` (fmod со знаком делителя),
  ZeroDivisionError-места заменены на ошибки домена (задокументированы в
  коде), eids рёбер покрытия начинаются с 1.

## Запуск

```bash
cd rust
cargo test                                          # все крейты (тесты читают пресеты из корня репозитория или $GRADO_REPO)
cargo build --release
./target/release/grado_compute_rs --preset <пресет.json> --set terr_area=15 --json
```

Модуль Python и сверка через него (из корня репозитория):

```bash
pip install maturin
maturin build --release -m rust/crates/py/Cargo.toml -o /tmp/grado-wheels
~/.grado2/venv/bin/pip install /tmp/grado-wheels/grado_rs-*.whl
GRADO_COMPUTE=rust PYTHONPATH=core/compute ~/.grado2/venv/bin/python -m pytest -q core/compute/tests
```

Сверка compute с Python через CLI (нужен `~/.grado2/venv` с зависимостями репозитория; дампы — во временную папку):

```bash
cargo build --release
~/.grado2/venv/bin/python parity/dump_reference.py .. /tmp/par/py
python3 -I parity/run_rs_dumps.py /tmp/par/rs .. /tmp/par/py
python3 -I parity/compare.py /tmp/par/py /tmp/par/rs   # «СВЕРКА СХОДИТСЯ …»
```

Сверка geom с Python:

```bash
~/.grado2/venv/bin/python parity/geom/dump_reference_geom.py .. /tmp/par/gpy
python3 -I parity/geom/run_rs_dumps.py /tmp/par/grs ..
python3 -I parity/geom/compare.py /tmp/par/gpy /tmp/par/grs
```

## Остальная Python-поверхность ГРАДО 2

| Модуль | Строк | Готовые Rust-аналоги | Оценка переноса |
|---|---|---|---|
| `core/compute` | ~400 | — | **перенесён**, подключается через `grado_rs` |
| `core/geom` | ~1 тыс. | — | **перенесён** |
| `core/connectors` | ~3 тыс. | `reqwest` — зрелый | реалистично |
| `core/model`, `core/reactive` | ~2 тыс. | serde | реалистично |
| `core/render` (PDF/PPTX/DXF/SVG) | ~3,5 тыс. | PDF/PPTX/DXF-экосистема Rust заметно слабее reportlab/python-pptx/ezdxf | главный риск |
| `core/layout` + печать альбома | ~0,7 тыс. | зависит от render | главный риск |
| `apps/grado2` сервер | ~8 тыс. | `axum` — зрелый | реалистично, но объёмно |

Вывод и рекомендация — стратегия «удушающей змеи»: сначала вычислительно
тяжёлые части через PyO3, сервер и рендер — позже; рендер последним
(или никогда: reportlab остаётся легитимной зависимостью).
