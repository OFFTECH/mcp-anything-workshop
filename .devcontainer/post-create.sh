#!/usr/bin/env bash
# Runs once when a codespace is created (devcontainer.json "postCreateCommand"; not part of a prebuild).
# Needs network access. It never stops the codespace from opening: problems are printed loudly and saved
# to ~/workshop-setup.txt.
set -u
cd "$(dirname "$0")/.." || { echo "SETUP INCOMPLETE: cannot enter the repository folder from $0" >&2; exit 0; }
root="$(pwd)"
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  grep -q "WORKSHOP_ROOT=" "$rc" 2>/dev/null || printf '\nexport WORKSHOP_ROOT="%s"\n' "$root" >> "$rc"
done
export WORKSHOP_ROOT="$root"
{
  echo "== Workshop setup $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 -m workshop.plugin install; plugin=$?
  # Claude Code's permission hook from the installed plugin: optional, so it never makes the setup incomplete.
  python3 -m workshop.permissions || echo "permission hook not installed: the helper failed; participants will see the normal prompts"
  python3 -m workshop.check_tools; tools=$?
  cache=ready
  if warm="$(timeout 600 uv run --no-project --python 3.12 --with "mcp>=1.12,<2" --with "pytest>=8" --with hatchling python -c "import mcp" 2>&1)"
  then echo "uv cache: ready"
  else
    cache=cold
    echo "uv cache: WARN could not pre-fill it; the first server build will download more. uv said:"
    printf '%s\n' "$warm" | tail -n 3
  fi
  if [ "$plugin" -ne 0 ] || [ "$tools" -ne 0 ]; then
    echo "SETUP INCOMPLETE: read the lines above, then README.md, section 'If something is missing'."
  elif [ "$cache" = cold ]; then
    echo "SETUP OK (uv cache not pre-filled: see the uv cache lines above)"
  else
    echo "SETUP OK"
  fi
} 2>&1 | tee "$HOME/workshop-setup.txt"
exit 0
