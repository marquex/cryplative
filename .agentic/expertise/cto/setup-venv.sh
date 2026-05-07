#!/bin/bash
set -e

PROJECT_ROOT="/Users/javi/projects/cryplative"
VENV_DIR="$PROJECT_ROOT/.venv"
PLATFORM_DIR="$PROJECT_ROOT/platform"
GITIGNORE="$PROJECT_ROOT/.gitignore"

# Helper: test if a Python binary works fully (version + core imports)
test_python() {
  local candidate="$1"
  [ -x "$candidate" ] || return 1
  local VER=$("$candidate" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
  local MAJOR=$(echo "$VER" | cut -d. -f1)
  local MINOR=$(echo "$VER" | cut -d. -f2)
  [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ] || return 1
  "$candidate" -c "import pyexpat; import ssl; import sqlite3" 2>/dev/null || return 1
  echo "$VER"
  return 0
}

echo "=== Step 0: Find working Python >= 3.11 ==="
PYTHON=""

# First pass: check existing installations
for candidate in \
  /opt/homebrew/bin/python3.12 \
  /opt/homebrew/bin/python3.11 \
  /opt/homebrew/bin/python3.13 \
  /opt/homebrew/bin/python3 \
  /usr/local/bin/python3.12 \
  /usr/local/bin/python3.11 \
  /usr/local/bin/python3.13 \
  /usr/local/bin/python3 \
  "$HOME/.pyenv/shims/python3" \
  "$HOME/.local/bin/python3"; do
  VER=$(test_python "$candidate") && {
    PYTHON="$candidate"
    echo "Found working Python: $candidate ($VER)"
    break
  }
done

# Strategy 2: Fix Homebrew Python by force-linking Homebrew's expat
if [ -z "$PYTHON" ] && command -v brew &>/dev/null; then
  echo "Homebrew Pythons broken (libexpat issue). Attempting to fix..."
  # Force-link Homebrew expat so its lib is in /opt/homebrew/lib/
  brew link --force expat 2>&1 || true
  # Also try install_name_tool to patch the .so files directly
  for PYVER in 3.12 3.13; do
    PYEXPAT_SO=$(find "/opt/homebrew/Cellar/python@${PYVER}" -name "pyexpat.cpython-${PYVER/./}-darwin.so" 2>/dev/null | head -1)
    if [ -n "$PYEXPAT_SO" ] && [ -f "$PYEXPAT_SO" ]; then
      echo "Patching $PYEXPAT_SO to use Homebrew expat..."
      BREW_EXPAT=$(find /opt/homebrew/Cellar/expat -name "libexpat.1.dylib" 2>/dev/null | head -1)
      if [ -n "$BREW_EXPAT" ]; then
        # Change the linked library path from system to Homebrew
        install_name_tool -change "/usr/lib/libexpat.1.dylib" "$BREW_EXPAT" "$PYEXPAT_SO" 2>&1 || true
      fi
    fi
  done

  # Re-test after patching
  for candidate in /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.11; do
    VER=$(test_python "$candidate") && {
      PYTHON="$candidate"
      echo "Fixed! Working Python: $candidate ($VER)"
      break
    }
  done
fi

# Strategy 3: Use uv to install Python (if available)
if [ -z "$PYTHON" ] && command -v uv &>/dev/null; then
  echo "Using uv to install Python 3.12..."
  uv python install 3.12 2>&1 | tail -5
  # IMPORTANT: Search uv's managed directory directly to avoid resolving to a venv symlink
  UV_PYTHON=$(find "$HOME/.local/share/uv/python" -name "python3.12" -path "*cpython-3.12*" 2>/dev/null | head -1)
  if [ -z "$UV_PYTHON" ]; then
    UV_PYTHON=$(find "$HOME/.local/share/uv/python" -name "python3" -path "*cpython-3.12*" 2>/dev/null | head -1)
  fi
  if [ -n "$UV_PYTHON" ] && [ -x "$UV_PYTHON" ]; then
    VER=$(test_python "$UV_PYTHON") && {
      PYTHON="$UV_PYTHON"
      echo "uv-provided Python: $PYTHON ($VER)"
    }
  fi
fi

# Strategy 4: Install uv via Homebrew and use it
if [ -z "$PYTHON" ] && command -v brew &>/dev/null; then
  echo "Installing uv via Homebrew for Python management..."
  brew install uv 2>&1 | tail -5
  uv python install 3.12 2>&1 | tail -5
  UV_PYTHON=$(find "$HOME/.local/share/uv/python" -name "python3.12" -path "*cpython-3.12*" 2>/dev/null | head -1)
  if [ -n "$UV_PYTHON" ] && [ -x "$UV_PYTHON" ]; then
    VER=$(test_python "$UV_PYTHON") && {
      PYTHON="$UV_PYTHON"
      echo "uv-provided Python: $PYTHON ($VER)"
    }
  fi
fi

if [ -z "$PYTHON" ]; then
  echo "ERROR: Could not find or install a working Python >= 3.11"
  echo "All strategies exhausted."
  exit 1
fi

echo ""
echo "=== Step 1: Add .venv/ to .gitignore ==="
if grep -q '\.venv/' "$GITIGNORE" 2>/dev/null; then
  echo ".venv/ already in .gitignore"
else
  echo ".venv/" >> "$GITIGNORE"
  echo "Added .venv/ to .gitignore"
fi

echo ""
echo "=== Step 2: Create venv with Python $("$PYTHON" --version) ==="
rm -rf "$VENV_DIR"
echo "Old venv removed"
"$PYTHON" -m venv "$VENV_DIR" 2>&1 || {
  echo "ensurepip failed, trying without pip..."
  rm -rf "$VENV_DIR"
  "$PYTHON" -m venv --without-pip "$VENV_DIR"
  echo "Bootstrapping pip via get-pip.py..."
  curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  "$VENV_DIR/bin/python" /tmp/get-pip.py 2>&1 | tail -3
  rm -f /tmp/get-pip.py
}
echo "Venv created at $VENV_DIR"
"$VENV_DIR/bin/python" --version

echo ""
echo "=== Step 3: Install cryplative as editable ==="
"$VENV_DIR/bin/pip" install --upgrade pip 2>&1 | tail -3
"$VENV_DIR/bin/pip" install -e "$PLATFORM_DIR" 2>&1 | tail -15

echo ""
echo "=== Step 4: Verify imports ==="
"$VENV_DIR/bin/python" -c "
import importlib
import pkgutil
import cryplative

# Discover all submodules
mods = [name for _, name, _ in pkgutil.walk_packages(cryplative.__path__, cryplative.__name__ + '.')]
print(f'Discovered modules: {mods}')

# Try to import each one
success = []
failed = []
for mod_name in mods:
    try:
        mod = importlib.import_module(mod_name)
        names = [n for n in dir(mod) if not n.startswith('_')]
        success.append(mod_name)
        print(f'  {mod_name}: OK ({len(names)} exports)')
    except Exception as e:
        failed.append(f'{mod_name}: {e}')
        print(f'  {mod_name}: FAILED - {e}')

if failed:
    print(f'Some imports failed: {failed}')
else:
    print(f'ALL {len(success)} MODULE IMPORTS SUCCESSFUL')
"

echo ""
echo "=== Step 5: Commit .gitignore change ==="
cd "$PROJECT_ROOT"
git add .gitignore
git diff --cached --stat
git commit -m "$(cat <<'EOF'
chore: add .venv/ to .gitignore for root virtual environment

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"

echo ""
echo "=== COMPLETE ==="
echo "To use: source .venv/bin/activate"
