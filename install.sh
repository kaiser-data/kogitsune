#!/usr/bin/env bash
# kogitsune installer — symlink bin/kit into your PATH. Idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_TARGET="${KOGITSUNE_BIN_DIR:-$HOME/.local/bin}"

echo "kogitsune 🦊 installer"
mkdir -p "$BIN_TARGET"
ln -sf "$ROOT/bin/kit" "$BIN_TARGET/kit"
echo "  ✔ linked $BIN_TARGET/kit -> $ROOT/bin/kit"

# dependency check (non-fatal)
miss=()
for d in claude python3 jq; do command -v "$d" >/dev/null 2>&1 || miss+=("$d"); done
command -v fzf >/dev/null 2>&1 || echo "  • fzf not found (needed only for the interactive picker)"
python3 -c "import yaml" 2>/dev/null || miss+=("python3-PyYAML (pip install pyyaml)")
if ((${#miss[@]})); then
  echo "  ! missing required deps: ${miss[*]}"
fi

case ":$PATH:" in
  *":$BIN_TARGET:"*) ;;
  *) echo "  ! $BIN_TARGET is not on your PATH — add to your shell rc:"
     echo "        export PATH=\"$BIN_TARGET:\$PATH\"" ;;
esac

echo
echo "shell completion (optional):"
case "$(basename "${SHELL:-}")" in
  zsh)  echo "  # add to ~/.zshrc:"
        echo "  fpath=($ROOT/completions \$fpath); autoload -Uz compinit && compinit" ;;
  bash) echo "  # add to ~/.bashrc:"
        echo "  source $ROOT/completions/kit.bash" ;;
  *)    echo "  bash: source $ROOT/completions/kit.bash"
        echo "  zsh:  fpath=($ROOT/completions \$fpath); autoload -Uz compinit && compinit" ;;
esac

echo
echo "next:"
echo "  cp examples/kits.example.yaml kits.yaml   # customize your kits"
echo "  kit doctor                                # verify setup"
echo "  kit db                                    # send the fox off 🦊"
