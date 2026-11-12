---
name: preflight
description: Check that every checkout a run touches is clean and current, and that the tools it needs are signed in, before a build or a scheduled run starts. Use before the design loop's Build step, before an unattended or scheduled run, when the user says "preflight", "check my checkouts" or "are my repos clean and current", or when a run is about to work across several repos.
---

# preflight

**Inputs:** the current repo; the paths the run will work in, when it names any; otherwise the board config's `preflight` section (`$BOARD_CONFIG` or `~/.config/board/boards.json`): its `repos` list, and its `probes`, one cheap read command per tool a run needs.

## Run it

```
python3 <this skill's folder>/scripts/preflight.py [PATH ...] [--pull]
```

`<this skill's folder>` is `~/.claude/skills/preflight/` when installed at user level.

It checks the current repo plus the paths given; with no paths, the config's `repos` list instead. Each repo is fetched, then reported on one line: its branch, clean or changed, and ahead and behind its own remote branch. Then each probe runs and reports signed in or failed.

- **Blocks (exit 1):**
  - uncommitted changes while behind the branch's own remote branch;
  - a branch that has diverged from its own remote branch;
  - a failed probe.
- **Can't check (exit 2):** a missing path, a folder that isn't a git checkout, a fetch that fails or times out, an unreadable config.
- **Reported, never blocking:**
  - untracked files;
  - a branch not pushed yet;
  - a detached HEAD;
  - a feature branch whose tracked branch (such as `main`) has moved.

  A build's own branch keeps working while `main` moves.
- **`--pull`** fast-forwards a clean checkout that is only behind its own remote branch. Nothing else is ever changed: no stash, no rebase, no branch switch.

Each line marked ✗ carries its fix. Act on the exit code: 0 go ahead; 1 stop and tell the user what blocks and the fix; 2 stop and say what couldn't be checked.

## Config

All optional, in the board config beside `boards`:

```json
"preflight": {
  "repos": ["~/work/acme-co/ops", "~/work/acme-co/web"],
  "probes": [
    {"name": "GitHub", "run": "gh api user -q .login", "fix": "gh auth login"}
  ]
}
```

`repos` is the standing list for a run that names no paths, such as a scheduled one. Keep probes cheap and read-only: each runs on every preflight.

## Check it

`preflight.py --controls` builds throwaway repos in a temp folder, offline, and checks each rule both ways: a case that must fire and a clean case that must not.
