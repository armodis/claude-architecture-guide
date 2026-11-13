# Personal Domain (Layer 1)

Applies to everything under `~/personal/`. Inherits the universal Layer 0
(`~/.claude/CLAUDE.md`); does **not** apply to work.

## Scope

Applies to: `~/personal/*` — personal projects, home, side ventures.
Does NOT apply to: `~/work/` or any other domain.

## Conventions

- Less formal than work; conversational tone is fine.
- Sensitive topics (finances, health, legal) get extra care.
- Git identity in this tree uses your personal email (see `.gitconfig` routing).

## Boards

Read and change GitHub project boards with `board` (`board --help` lists the commands and the plan format). The boards are named in `~/.config/board/boards.json`.

- Look before changing: `board snapshot <board>`, then `board tree`, `board hygiene`, `board select`, `board search`.
- Every change is a JSON change plan: `board check <board> <plan>` shows the dry run, and `board apply` writes it and reads back every board. A plan that prints "needs review" waits for the operator's go; apply it with `--approved`.
- Claim with `board claim <board> <owner/repo#n> --status-md STATUS.md`; finish with `board finish … --close`.
- The `item`, `pickup` and `board-setup` skills run the common tasks; `preflight` checks the checkouts and sign-ins before a build or a scheduled run.

<!-- Replace with your real personal-domain conventions. -->
