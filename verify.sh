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
ok()   { echo "  ✓ $1"; pass=$((pass + 1)); }
ko()   { echo "  ✗ $1"; fail=$((fail + 1)); fail_msgs+=("$1"); }
note() { echo "  – $1"; }
section() { echo ""; echo "== $1 =="; }

# Absolute path with every link resolved; empty if it can't be resolved.
# macOS before 12.3 has no `readlink -f`, so fall back to realpath.
resolve() {
  readlink -f -- "$1" 2>/dev/null || realpath -- "$1" 2>/dev/null || true
}

# Pass only when $path resolves to the expected file in template/ — through a
# link on the file itself or on a parent directory. A real file, a link to
# somewhere else, or a dangling link means setup.sh hasn't wired it.
check_linked() {
  local path="$1" want="$2" target wanted
  if [ -L "$path" ] && [ ! -e "$path" ]; then
    ko "$path -> $(readlink -- "$path") (dangling link)"; return
  fi
  if [ ! -e "$path" ]; then ko "$path missing"; return; fi
  target=$(resolve "$path"); wanted=$(resolve "$want")
  if [ -z "$target" ] || [ -z "$wanted" ]; then
    ko "$path: can't resolve links (needs readlink -f or realpath)"
  elif [ "$target" = "$wanted" ]; then
    ok "$path -> ${want#"$SUBSTRATE"/}"
  elif [ -L "$path" ]; then
    ko "$path -> $target (expected ${want#"$SUBSTRATE"/})"
  else
    ko "$path is a real file, not linked to ${want#"$SUBSTRATE"/}"
  fi
}

# Files stow never links (its default ignore list), relative to the package.
stow_ignored() {
  local rel="$1" base="${1##*/}"
  case "/$rel/" in */.git/*|*/.svn/*|*/.hg/*|*/CVS/*|*/RCS/*|*/_darcs/*) return 0 ;; esac
  case "$base" in .gitignore|.gitmodules|.cvsignore|*~|\#*\#|.\#*|*,v) return 0 ;; esac
  case "$rel" in README*|LICENSE*|COPYING) return 0 ;; esac   # top level only
  return 1
}

# Every file stow links from a package must resolve at its place under ~.
check_package() {
  local pkg="$1" f rel n=0
  if [ ! -d "$TEMPLATE/$pkg" ]; then ko "template/$pkg missing"; return; fi
  [ -f "$TEMPLATE/$pkg/.stow-local-ignore" ] && \
    note "template/$pkg has .stow-local-ignore; files it excludes will report missing"
  while IFS= read -r -d '' f; do
    rel="${f#"$TEMPLATE/$pkg"/}"
    stow_ignored "$rel" && continue
    [ "$rel" = .stow-local-ignore ] && continue
    n=$((n + 1))
    check_linked "$HOME/$rel" "$f"
  done < <(find "$TEMPLATE/$pkg" -type f -print0)
  [ "$n" -gt 0 ] || ko "template/$pkg has no files to link"
}

if [ -f "$SUBSTRATE/.task-mgmt-release" ]; then
  section "Release"
  while IFS= read -r l; do note "$l"; done < "$SUBSTRATE/.task-mgmt-release"
fi

# --- 1. Layer 0: universal config ---
section "Layer 0 — universal ~/.claude"
check_package claude-user
# A domain-root CLAUDE.md suppresses every repo's AGENTS.md unless Claude Code is told to read both.
if [ ! -r "$HOME/.claude/settings.json" ]; then
  note "AGENTS.md setting not checked: ~/.claude/settings.json is missing (reported above)"
elif grep -q '"instructionFiles": *"claude-md-and-agents-md"' "$HOME/.claude/settings.json"; then
  ok "Project instructions = claude-md-and-agents-md (repo AGENTS.md files load beneath the domain CLAUDE.md)"
else
  ko "settings.json lacks pluginConfigs.agents-md@builtin.options.instructionFiles = claude-md-and-agents-md — repo AGENTS.md files are being ignored"
fi

# --- 2. Universal layer is domain-neutral ---
section "Layer 0 is domain-neutral (no single domain bleeds in)"
if [ ! -r "$HOME/.claude/CLAUDE.md" ]; then
  note "domain bleed not checked: ~/.claude/CLAUDE.md is missing (reported above)"
else
  leak=""
  for d in ${DOMAINS[@]+"${DOMAINS[@]}"}; do
    # A universal file shouldn't hard-code any one domain's private nouns.
    grep -qiwF -- "$d" "$HOME/.claude/CLAUDE.md" && leak="$leak $d"
  done
  if [ -z "$leak" ]; then
    ok "universal CLAUDE.md names no specific domain"
  else
    note "universal CLAUDE.md references:$leak (fine if intentional)"
  fi
fi

# --- 3. Layer 1: per-domain roots ---
section "Layer 1 — domain roots"
if [ "${#DOMAINS[@]}" -eq 0 ]; then
  note "no DOMAINS configured"
fi
for d in ${DOMAINS[@]+"${DOMAINS[@]}"}; do
  src="$TEMPLATE/claude-domains/$d/CLAUDE.md"
  if [ ! -f "$src" ]; then
    ko "template/claude-domains/$d/CLAUDE.md missing — create it, or remove '$d' from DOMAINS"
  else
    check_linked "$HOME/$d/CLAUDE.md" "$src"
  fi
done

# --- 4. Dotfile packages ---
if [ "${#STOW_PACKAGES[@]}" -gt 0 ]; then
  section "Dotfile packages"
  for pkg in "${STOW_PACKAGES[@]}"; do
    check_package "$pkg"
  done
fi

# --- 5. Skill overlays ---
if [ "${#SKILL_OVERLAYS[@]}" -gt 0 ]; then
  section "Skill overlays"
  for spec in "${SKILL_OVERLAYS[@]}"; do
    domain="${spec%%:*}" src="${spec#*:}"
    if [ ! -d "$src" ]; then ko "overlay source missing: $src"; continue; fi
    n=0
    while IFS= read -r -d '' f; do
      n=$((n + 1))
      check_linked "$HOME/$domain/.claude/${f#"$src"/}" "$f"
    done < <(find "$src" -type f -print0)
    [ "$n" -gt 0 ] || ko "overlay source $src has no files"
  done
fi

# --- 5b. The board command resolves on PATH ---
if [[ " ${STOW_PACKAGES[*]} " == *" board "* ]]; then
  section "Board command"
  if command -v board >/dev/null 2>&1; then
    ok "board on PATH ($(command -v board))"
  else
    note "board is installed in ~/.local/bin but not on PATH; add: export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl --user is-enabled board-refresh.timer >/dev/null 2>&1; then
    ok "board-refresh.timer enabled (daily snapshot refresh)"
  else
    note "board-refresh.timer not enabled; snapshots still refresh on read once older than a day"
  fi
fi

# --- 5c. The claude-restore commands resolve on PATH ---
if [[ " ${STOW_PACKAGES[*]} " == *" claude-restore "* ]]; then
  section "claude-restore commands"
  for c in claude-restore claude-provider; do
    if command -v "$c" >/dev/null 2>&1; then
      ok "$c on PATH ($(command -v "$c"))"
    else
      note "$c is installed in ~/.local/bin but not on PATH; add: export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
  done
fi

# --- 6. GitHub auth (optional, for the orchestration layer) ---
section "GitHub auth (optional)"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  ok "gh authenticated as $(gh api /user --jq '.login' 2>/dev/null)"
else
  note "gh not authenticated (only needed for the GitHub-as-substrate workflow)"
fi

# --- 7. GitHub matches github.json (when there is one) ---
if [ -f "$SUBSTRATE/github.json" ]; then
  section "GitHub (provision.py rehearsal)"
  if ! command -v gh >/dev/null 2>&1 || ! gh auth status >/dev/null 2>&1; then
    ko "github.json exists but gh is not logged in"
  else
    out=$(python3 "$SUBSTRATE/provision.py" "$SUBSTRATE/github.json" 2>&1); rc=$?
    case $rc in
      0) ok "organizations, repos, boards and board config match github.json" ;;
      2) ko "GitHub doesn't match github.json yet:"; printf '%s\n' "$out" | grep -E '^  [·!] ' ;;
      *) ko "provision.py failed: $(printf '%s' "$out" | tail -1)" ;;
    esac
  fi
fi

# --- Summary ---
echo ""; echo "==========================="
echo "Passed: $pass    Failed: $fail"
if [ "$fail" -gt 0 ]; then
  echo ""; echo "Failures:"; for m in "${fail_msgs[@]}"; do echo "  - $m"; done
  exit 1
fi
echo "All checks passed."
