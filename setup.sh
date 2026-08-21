#!/usr/bin/env bash
# setup.sh — deploy a multi-domain Claude Code substrate.
#
# Companion to README.md (the architecture guide) and brief.html (the visual
# overview). This is the runnable version of the pattern: it wires a single
# source-of-truth repo into your home directory with GNU Stow + symlinks, so
# every Claude Code session inherits the right layered instructions.
#
# What it does:
#   1. Stows  template/claude-user/  -> ~/.claude/        (Layer 0: universal)
#   2. Symlinks each domain's root CLAUDE.md -> ~/<domain>/CLAUDE.md (Layer 1)
#   3. (optional) Stows shell/git dotfile packages         -> ~/
#   4. (optional) Aggregates skill overlays into ~/<domain>/.claude/
#
# Idempotent. Any *real* file found where a symlink should go is backed up
# first, never overwritten. Re-run any time.
#
# Usage:
#   git clone https://github.com/armodis/claude-architecture-guide
#   cd claude-architecture-guide
#   $EDITOR setup.sh          # edit the CONFIG block below
#   ./setup.sh
#   ./verify.sh

set -euo pipefail

SUBSTRATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SUBSTRATE/template"

# Configuration lives in substrate.conf (edit that, not this script).
# shellcheck source=substrate.conf
source "$SUBSTRATE/substrate.conf"

BACKUP_DIR="$HOME/.claude-substrate-backup/$(date +%Y%m%d-%H%M%S)"

info() { printf '\033[36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$1"; }

command -v stow >/dev/null 2>&1 || {
  echo "GNU Stow is required. Install it:"
  echo "  Debian/Ubuntu: sudo apt install stow"
  echo "  macOS:         brew install stow"
  echo "  Fedora:        sudo dnf install stow"
  exit 1
}

# Back up a real file/dir (not a symlink) before it's replaced; remove a stale symlink.
backup_if_real() {
  local target="$1"
  if [ -L "$target" ]; then
    rm "$target"
  elif [ -e "$target" ]; then
    mkdir -p "$BACKUP_DIR"
    mv "$target" "$BACKUP_DIR/"
    warn "backed up existing $target -> $BACKUP_DIR/"
  fi
}

mkdir -p "$HOME/.claude"

# ─── Layer 0: universal user config -> ~/.claude/ ─────────────────────────
info "Stowing template/claude-user -> ~/  (Layer 0: universal)"
if [ -d "$TEMPLATE/claude-user/.claude" ]; then
  # Back up any real files that would collide, then stow the package.
  while IFS= read -r f; do
    rel="${f#"$TEMPLATE"/claude-user/}"
    backup_if_real "$HOME/$rel"
  done < <(find "$TEMPLATE/claude-user" -type f)
  stow -d "$TEMPLATE" -t "$HOME" --no-folding -Rv claude-user
else
  warn "no template/claude-user — skipping Layer 0"
fi

# ─── Layer 1: per-domain root CLAUDE.md -> ~/<domain>/CLAUDE.md ────────────
info "Linking domain-root CLAUDE.md files -> ~/<domain>/  (Layer 1)"
for d in "${DOMAINS[@]}"; do
  src="$TEMPLATE/claude-domains/$d/CLAUDE.md"
  if [ -f "$src" ]; then
    mkdir -p "$HOME/$d"
    backup_if_real "$HOME/$d/CLAUDE.md"
    ln -sfn "$src" "$HOME/$d/CLAUDE.md"
    echo "  ~/$d/CLAUDE.md -> $src"
  else
    warn "no template/claude-domains/$d/CLAUDE.md — create one, or remove '$d' from DOMAINS"
  fi
done

# ─── Optional: shell + git dotfiles -> ~/ ─────────────────────────────────
if [ "${#STOW_PACKAGES[@]}" -gt 0 ]; then
  info "Stowing dotfile packages: ${STOW_PACKAGES[*]}"
  for pkg in "${STOW_PACKAGES[@]}"; do
    if [ -d "$TEMPLATE/$pkg" ]; then
      while IFS= read -r f; do
        rel="${f#"$TEMPLATE"/"$pkg"/}"
        backup_if_real "$HOME/$rel"
      done < <(find "$TEMPLATE/$pkg" -type f)
      stow -d "$TEMPLATE" -t "$HOME" --no-folding -Rv "$pkg"
    else
      warn "no template/$pkg — skipping"
    fi
  done
fi

# ─── Optional: skill overlays -> ~/<domain>/.claude/ ──────────────────────
if [ "${#SKILL_OVERLAYS[@]}" -gt 0 ]; then
  info "Aggregating skill overlays"
  for spec in "${SKILL_OVERLAYS[@]}"; do
    domain="${spec%%:*}"
    src="${spec#*:}"
    dest="$HOME/$domain/.claude"
    if [ ! -d "$src" ]; then warn "overlay source missing: $src"; continue; fi
    mkdir -p "$dest"
    # Clean stale symlinks we previously created, then re-link every file.
    find "$dest" -type l -delete 2>/dev/null || true
    while IFS= read -r file; do
      rel="${file#"$src"/}"
      mkdir -p "$dest/$(dirname "$rel")"
      ln -sfn "$file" "$dest/$rel"
    done < <(find "$src" -type f)
    echo "  $src -> $dest"
  done
fi

echo ""
info "Done. Run ./verify.sh to confirm the wiring."
[ -d "$BACKUP_DIR" ] && warn "Some real files were backed up to $BACKUP_DIR"
echo "Then restart your shell (or: source ~/.bashrc) and launch 'claude' from any domain."
