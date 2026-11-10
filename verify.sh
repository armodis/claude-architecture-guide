#!/usr/bin/env bash
# verify.sh — confirm the multi-domain substrate is wired correctly.
# Run after setup.sh. Reads the same CONFIG as setup.sh. Exit 0 = all pass.

set -uo pipefail

SUBSTRATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SUBSTRATE/template"
# Same config setup.sh uses — single source of truth.
# shellcheck source=substrate.conf
source "$SUBSTRATE/substrate.conf"

pass=0; fail=0; fail_msgs=()
# Plain assignment, not ((n++)): ((0)) returns status 1, which turns
# `check && ok || ko` into a pass AND a failure for the first check.
ok() { echo "  ✓ $1"; pass=$((pass + 1)); }
ko() { echo "  ✗ $1"; fail=$((fail + 1)); fail_msgs+=("$1"); }
section() { echo ""; echo "== $1 =="; }

# Pass only when $path resolves to the expected file in template/ — a real
# file or a link to somewhere else means setup.sh hasn't wired it.
check_linked() {
  local path="$1" want="$2" target
  target=$(readlink -f "$path" 2>/dev/null)
  if [ ! -e "$path" ]; then
    ko "$path missing"
  elif [ ! -L "$path" ]; then
    ko "$path is a real file, not linked to ${want#"$SUBSTRATE"/}"
  elif [ "$target" != "$(readlink -f "$want")" ]; then
    ko "$path -> $target (expected ${want#"$SUBSTRATE"/})"
  else
    ok "$path -> ${want#"$SUBSTRATE"/}"
  fi
}

# Every file in a stow package must be linked at its place under ~.
check_package() {
  local pkg="$1" f
  while IFS= read -r -d '' f; do
    check_linked "$HOME/${f#"$TEMPLATE/$pkg"/}" "$f"
  done < <(find "$TEMPLATE/$pkg" -type f -print0)
}

# --- 1. Layer 0: universal config ---
section "Layer 0 — universal ~/.claude"
if [ -d "$TEMPLATE/claude-user" ]; then
  check_package claude-user
else
  ko "template/claude-user missing"
fi
# A domain-root CLAUDE.md suppresses every repo's AGENTS.md unless Claude Code is told to read both.
if [ ! -r "$HOME/.claude/settings.json" ]; then
  ko "~/.claude/settings.json missing — can't check the AGENTS.md setting"
elif grep -q '"instructionFiles": *"claude-md-and-agents-md"' "$HOME/.claude/settings.json"; then
  ok "Project instructions = claude-md-and-agents-md (repo AGENTS.md files load beneath the domain CLAUDE.md)"
else
  ko "settings.json lacks pluginConfigs.agents-md@builtin.options.instructionFiles = claude-md-and-agents-md — repo AGENTS.md files are being ignored"
fi

# --- 2. Universal layer is domain-neutral ---
section "Layer 0 is domain-neutral (no single domain bleeds in)"
if [ ! -r "$HOME/.claude/CLAUDE.md" ]; then
  ko "~/.claude/CLAUDE.md missing — can't check it for domain bleed"
else
  leak=""
  for d in "${DOMAINS[@]}"; do
    # A universal file shouldn't hard-code any one domain's private nouns.
    grep -qiw "$d" "$HOME/.claude/CLAUDE.md" && leak="$leak $d"
  done
  if [ -z "$leak" ]; then
    ok "universal CLAUDE.md names no specific domain"
  else
    echo "  – universal CLAUDE.md references:$leak (fine if intentional)"
  fi
fi

# --- 3. Layer 1: per-domain roots ---
section "Layer 1 — domain roots"
for d in "${DOMAINS[@]}"; do
  check_linked "$HOME/$d/CLAUDE.md" "$TEMPLATE/claude-domains/$d/CLAUDE.md"
done

# --- 4. Dotfile packages ---
if [ "${#STOW_PACKAGES[@]}" -gt 0 ]; then
  section "Dotfile packages"
  for pkg in "${STOW_PACKAGES[@]}"; do
    if [ -d "$TEMPLATE/$pkg" ]; then
      check_package "$pkg"
    else
      ko "template/$pkg missing (listed in STOW_PACKAGES)"
    fi
  done
fi

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
