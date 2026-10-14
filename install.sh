#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PETSCII_PREFIX:-$HOME/.local}"
PYTHON="${PETSCII_PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null; then
  echo 'Python 3.12 or newer is required.' >&2
  exit 1
fi
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "Python 3.12 or newer is required.")'
for program in parec pactl; do
  if ! command -v "$program" >/dev/null; then
    echo 'Audio tools missing. Arch/Omarchy: install libpulse; Debian/Ubuntu: install pulseaudio-utils.' >&2
    exit 1
  fi
done
"$PYTHON" -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/requirements.txt"
mkdir -p "$PREFIX/bin" "$PREFIX/share/applications"
if [[ -e "$PREFIX/bin/petscii-64" && ! -L "$PREFIX/bin/petscii-64" ]]; then
  echo "Refusing to replace an existing file: $PREFIX/bin/petscii-64" >&2
  exit 1
fi
ln -sfn "$ROOT/run" "$PREFIX/bin/petscii-64"
"$ROOT/.venv/bin/python" - "$ROOT" "$PREFIX" <<'PY'
from pathlib import Path
import sys
root, prefix = map(Path, sys.argv[1:])
def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
desktop = f'''[Desktop Entry]
Type=Application
Name=PETSCII / 64
Comment=C64 colours and PETSCII-inspired music visualisation
Exec={quote(root / 'run')}
Icon={root / 'assets/icon.svg'}
Terminal=false
Categories=AudioVideo;Audio;
Keywords=music;visualiser;visualizer;petscii;c64;
'''
(prefix / 'share/applications/petscii-64.desktop').write_text(desktop)
PY
echo "Installed! Launch PETSCII / 64 from your app menu or run: $PREFIX/bin/petscii-64"
echo "Keep this project at $ROOT; the launcher uses it."
