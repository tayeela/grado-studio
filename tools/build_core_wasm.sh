#!/usr/bin/env bash
# ГРАДО · ядро для браузера (план 09.11.2026, шаг С1): rust/crates/wasm (координаты и формат проекта) → WebAssembly
# в apps/grado3/ui/src/wasm (grado_core_wasm.js + grado_core_wasm_bg.wasm, в git), их берёт apps/grado3/ui/src/core.ts;
# затем типы TypeScript из Rust (ts-rs, apps/grado3/ui/src/types). Нужны: rustup target add wasm32-unknown-unknown,
# cargo install wasm-bindgen-cli --version <как wasm-bindgen в rust/Cargo.lock>.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/rust"
cargo build --release --target wasm32-unknown-unknown -p grado_core_wasm
wasm-bindgen --target web --out-dir "$ROOT/apps/grado3/ui/src/wasm" target/wasm32-unknown-unknown/release/grado_core_wasm.wasm
cargo test -q -p grado_model export_bindings >/dev/null
ls -la "$ROOT/apps/grado3/ui/src/wasm" "$ROOT/apps/grado3/ui/src/types"
