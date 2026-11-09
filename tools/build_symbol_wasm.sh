#!/usr/bin/env bash
# ГРАДО 2 · слои знака на Rust для экрана (план 08.11.2026, шаг 3): rust/crates/symbol → WebAssembly в
# apps/grado2/ui/src/wasm (grado_symbol.js + grado_symbol_bg.wasm, в git), их берёт ui/src/symbology.js; затем
# сборка интерфейса (cd apps/grado2/ui && npm run build). Нужны: rustup target add wasm32-unknown-unknown,
# cargo install wasm-bindgen-cli --version <как wasm-bindgen в rust/Cargo.lock>.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/rust"
cargo build --release --target wasm32-unknown-unknown -p grado_symbol
wasm-bindgen --target web --no-typescript --out-dir "$ROOT/apps/grado2/ui/src/wasm" target/wasm32-unknown-unknown/release/grado_symbol.wasm
ls -la "$ROOT/apps/grado2/ui/src/wasm"
