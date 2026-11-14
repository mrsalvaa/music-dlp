#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Construye dist/music-dlp-<versión>-x86_64.AppImage con Python, Qt, yt-dlp y ffmpeg adentro.
# Requisitos: uv y appimagetool (en el PATH, o su AppImage en build/appimagetool-x86_64.AppImage).
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
[ -x "$PY" ] || uv venv -q --python 3.13 .venv
uv pip install -q --python "$PY" "yt-dlp[default]" PySide6-Essentials keyring secretstorage imageio-ffmpeg pyinstaller

VERSION=$("$PY" -c "import sys; sys.path.insert(0,'src'); import music_dlp; print(music_dlp.__version__)")
rm -rf build/pyi build/launcher.py build/music-dlp.spec dist/music-dlp AppDir
mkdir -p build dist

# 1) Empaquetar Python + Qt + yt-dlp en una carpeta autónoma
printf 'import sys\nfrom music_dlp.__main__ import main\nsys.exit(main())\n' > build/launcher.py
"$PY" -m PyInstaller --noconfirm --clean --windowed --name music-dlp \
  --paths src --distpath dist --workpath build/pyi --specpath build \
  --collect-submodules yt_dlp --collect-data yt_dlp_ejs \
  --hidden-import keyring.backends.SecretService --hidden-import secretstorage \
  --exclude-module tkinter --exclude-module imageio_ffmpeg --exclude-module PySide6.QtNetwork \
  --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.QtOpenGL \
  --exclude-module PySide6.QtPdf \
  build/launcher.py >build/pyinstaller.log 2>&1 || { tail -20 build/pyinstaller.log; exit 1; }

# Quitar plugins de Qt y bibliotecas del sistema que la app no usa
"$PY" packaging/prune.py dist/music-dlp/_internal

# ffmpeg estático (el que distribuye imageio-ffmpeg), para no depender del sistema
FFMPEG=$("$PY" -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
mkdir -p dist/music-dlp/ffmpeg
cp "$FFMPEG" dist/music-dlp/ffmpeg/ffmpeg
chmod +x dist/music-dlp/ffmpeg/ffmpeg

# 2) Armar el AppDir
mkdir -p AppDir/usr/bin AppDir/usr/share/applications AppDir/usr/share/icons/hicolor/256x256/apps
cp -a dist/music-dlp AppDir/usr/lib-music-dlp
ln -s ../lib-music-dlp/music-dlp AppDir/usr/bin/music-dlp
cp packaging/music-dlp.desktop AppDir/usr/share/applications/music-dlp.desktop
cp packaging/music-dlp.desktop AppDir/music-dlp.desktop
QT_QPA_PLATFORM=offscreen PYTHONPATH=src "$PY" packaging/make_icon.py AppDir/usr/share/icons/hicolor/256x256/apps/music-dlp.png 256
cp AppDir/usr/share/icons/hicolor/256x256/apps/music-dlp.png AppDir/music-dlp.png
ln -s music-dlp.png AppDir/.DirIcon
cp LICENSE AppDir/usr/lib-music-dlp/LICENSE
printf '#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/lib-music-dlp/music-dlp" "$@"\n' > AppDir/AppRun
chmod +x AppDir/AppRun
echo "AppDir listo: $(du -sh AppDir | cut -f1)"

# 3) Crear el AppImage
if command -v appimagetool >/dev/null; then
  TOOL=(appimagetool)
elif [ -x build/appimagetool-x86_64.AppImage ]; then
  TOOL=(build/appimagetool-x86_64.AppImage --appimage-extract-and-run)
else
  echo "Falta appimagetool: instalalo, o dejá su AppImage en build/appimagetool-x86_64.AppImage" >&2
  echo "  https://github.com/AppImage/appimagetool/releases" >&2
  exit 2
fi
OUT="dist/music-dlp-$VERSION-x86_64.AppImage"
ARCH=x86_64 "${TOOL[@]}" --no-appstream AppDir "$OUT" >build/appimagetool.log 2>&1 || { tail -20 build/appimagetool.log; exit 1; }
chmod +x "$OUT"
(cd dist && sha256sum "music-dlp-$VERSION-x86_64.AppImage" > SHA256SUMS)
ls -lh "$OUT"
cat dist/SHA256SUMS
