# Work Domain (Layer 1)

Applies to everything under `~/work/`. Inherits the universal Layer 0
(`~/.claude/CLAUDE.md`); does **not** apply to other domains.

## Scope

Applies to: `~/work/*` — your day-job repositories and work projects.
Does NOT apply to: `~/personal/` or any other domain.

## Conventions

- Each sub-directory is a separate repository with its own project-level CLAUDE.md.
  Launch Claude from inside the repo you're working on so its `.claude/` loads.
- Professional tone. Business context is appropriate here.
- Git identity in this tree uses your work email (see `.gitconfig` routing).

## Boards

Read and change GitHub project boards with `board` (`board --help` lists the commands and the plan format). The boards are named in `~/.config/board/boards.json`.

- Look before changing: `board snapshot <board>`, then `board tree`, `board hygiene`, `board select`, `board search`.
- Every change is a JSON change plan: `board check <board> <plan>` shows the dry run, and `board apply` writes it and reads back every board. A plan that prints "needs review" waits for the operator's go; apply it with `--approved`.
- Claim with `board claim <board> <owner/repo#n> --status-md STATUS.md`; finish with `board finish … --close`.
- The `item`, `pickup` and `board-setup` skills run the common tasks; `preflight` checks the checkouts and sign-ins before a build or a scheduled run.

<!-- Replace with your real work-domain conventions: repo directory, launch
     rules, review standards, the multi-agent workflow if you run one. -->
