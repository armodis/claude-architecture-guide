#!/usr/bin/env bash
# Minimal status line: shows the current domain (first path segment under ~)
# and the git branch if inside a repo. Customize freely.
cwd="${PWD/#$HOME/\~}"
domain=$(printf '%s' "$cwd" | sed -E 's#^~/([^/]+).*#\1#')
branch=$(git branch --show-current 2>/dev/null)
printf '%s' "$domain"
[ -n "$branch" ] && printf ' · %s' "$branch"
