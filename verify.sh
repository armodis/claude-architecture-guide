#!/usr/bin/env bash
# verify.sh — confirm the multi-domain substrate is wired correctly.
# Run after setup.sh. Reads the same CONFIG as setup.sh. Exit 0 = all pass.

set -uo pipefail

SUBSTRATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Same config setup.sh uses — single source of truth.
# shellcheck source=substrate.conf
source "$SUBSTRATE/substrate.conf"

pass=0; fail=0; fail_msgs=()
ok() { echo "  ✓ $1"; ((pass++)); }
ko() { echo "  ✗ $1"; ((fail++)); fail_msgs+=("$1"); }
section() { echo ""; echo "== $1 =="; }

check_symlink() {
  local path="$1"
  if [ -L "$path" ]; then
    local target; target=$(readlink -f "$path")
    if [ -e "$target" ]; then ok "$path -> $target"; else ko "$path -> $target (target missing)"; fi
  else
    ko "$path (not a symlink)"
  fi
}

# --- 1. Layer 0: universal config ---
section "Layer 0 — universal ~/.claude"
check_symlink "$HOME/.claude/CLAUDE.md"
[ -e "$HOME/.claude/settings.json" ] && ok "~/.claude/settings.json present" || ko "~/.claude/settings.json missing"

# --- 2. Universal layer is domain-neutral ---
section "Layer 0 is domain-neutral (no single domain bleeds in)"
leak=""
for d in "${DOMAINS[@]}"; do
  # A universal file shouldn't hard-code any one domain's private nouns.
  grep -qiw "$d" "$HOME/.claude/CLAUDE.md" 2>/dev/null && leak="$leak $d"
done
if [ -z "$leak" ]; then
  ok "universal CLAUDE.md names no specific domain"
else
  echo "  – universal CLAUDE.md references:$leak (fine if intentional)"
fi

# --- 3. Layer 1: per-domain roots ---
section "Layer 1 — domain roots"
for d in "${DOMAINS[@]}"; do
  check_symlink "$HOME/$d/CLAUDE.md"
done

# --- 4. Dotfile packages ---
section "Dotfile packages"
for pkg in "${STOW_PACKAGES[@]}"; do
  case "$pkg" in
    bash) for f in .bashrc .bash_aliases .bash_functions; do [ -e "$HOME/$f" ] && ok "$f present" || true; done ;;
    git)  for f in .gitconfig; do [ -e "$HOME/$f" ] && ok "$f present" || true; done ;;
  esac
done

# --- 5. GitHub auth (optional, for the orchestration layer) ---
section "GitHub auth (optional)"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  ok "gh authenticated as $(gh api /user --jq '.login' 2>/dev/null)"
else
  echo "  – gh not authenticated (only needed for the GitHub-as-substrate workflow)"
fi

# --- Summary ---
echo ""; echo "==========================="
echo "Passed: $pass    Failed: $fail"
if [ "$fail" -gt 0 ]; then
  echo ""; echo "Failures:"; for m in "${fail_msgs[@]}"; do echo "  - $m"; done
  exit 1
fi
echo "All checks passed."
