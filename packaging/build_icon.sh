#!/bin/sh
# Собирает packaging/AppIcon.icns из packaging/AppIcon.svg: PNG 16, 32, 128, 256, 512 px и их @2x-версии (ImageMagick).
# Запускать на Mac (нужна утилита iconutil) перед сборкой приложения, если менялся AppIcon.svg.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ICONSET=$(mktemp -d "${TMPDIR:-/tmp}/grado-icon.XXXXXX")/AppIcon.iconset
mkdir -p "$ICONSET"

for size in 16 32 128 256 512; do
  magick -background none "$ROOT/AppIcon.svg" -resize "${size}x${size}" "$ICONSET/icon_${size}x${size}.png"
  double=$((size * 2))
  magick -background none "$ROOT/AppIcon.svg" -resize "${double}x${double}" "$ICONSET/icon_${size}x${size}@2x.png"
done

iconutil -c icns "$ICONSET" -o "$ROOT/AppIcon.icns"
echo "Создан $ROOT/AppIcon.icns"
