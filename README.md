# Multi-Domain Claude Code Architecture: A General Guide

**Purpose:** A working architecture for using Claude across multiple distinct life or work domains — keeping context appropriate, configuration shared where it should be shared, and isolated where it should be isolated.

**Audience:** Anyone using Claude Code (and adjacent Claude surfaces) who has more than one distinct domain of work — a day job and personal projects; multiple clients; work, family, and side ventures — and wants the agent to behave correctly in each without manual context-juggling.

**Status:** A pattern document, not a step-by-step plan. The architecture is concrete; the migration to get there is described as a pattern that a Claude Code session can tailor to your specific starting state.

***

## How to Use This Document

**If you're reading as a human:** read Parts 1–3 to get the mental model. Part 4 describes the migration shape; you'll likely hand it to a Claude Code session along with a description of your current setup and ask for a tailored plan.

**If you're a Claude Code agent helping someone adopt this architecture:** read end-to-end. Part 4 is a pattern, not a plan — your job is to inspect the user's environment (current directory layout, existing dotfiles, GitHub orgs, identity strategy, sensitive content scope), then produce a phase-by-phase plan specific to them. See the "Tailoring This Pattern" section at the end of Part 4 for what to ask before producing the plan.

***

# Part 1: The Mental Model

## The Claude Surfaces

Claude has several distinct surfaces that share a brand but differ in mechanics. Knowing which surface you're using is the first prerequisite for using them well.

| Surface | Where | What it reads | What it writes |
|---------|-------|---------------|----------------|
| **claude.ai** (chat + Projects) | Web | User Preferences, Project knowledge, GitHub connector (read-only for the most part) | Inline responses, artifacts, downloads |
| **Web Claude Code** | Web (claude.ai/code) | A cloned repo's `.claude/`, `CLAUDE.md`, `.mcp.json` — single repo only | Git branches, push to remote |
| **Local Claude Code** | Terminal / IDE | Merges `CLAUDE.md` up the whole tree; resolves slash commands from the nearest repo (stops at the repo boundary); memory keyed to launch cwd | Local filesystem; git push when told to |
| **Claude Design** | Web (claude.ai/design) | Visual collaboration tool | Visual artifacts; handoff bundle to Claude Code |
| **Browser extension** | Browser | Live DOM; bridges to local Claude Code | Browser actions |

Two facts do most of the work in this guide:

1. **Local Claude Code resolves config from the directory tree** — but the three resolution mechanisms behave differently (see Config Resolution below). CLAUDE.md merges up the whole tree; slash commands stop at the first repo boundary; memory is keyed to the exact launch directory. The practical upshot: **launch from inside the repo you're working on.**
2. **Web Claude Code only sees the single repo you clone.** Anything you want available in a web session has to be in that repo's `.claude/` (or a submodule). Because the canonical layout puts skills at the repo root's `.claude/`, web sessions get them for free.

## Config Resolution

Three mechanisms resolve config, and they do **not** all walk the tree the same way. The differences determine where you launch `claude` and where you put skills.

| Mechanism | What it loads | Walk behavior |
|-----------|---------------|---------------|
| **CLAUDE.md instructions** | Every `CLAUDE.md` from cwd up to `~`, plus `~/.claude/CLAUDE.md` | **Merges all.** Walks up through every ancestor; closer wins on conflicts. |
| **Slash commands** (`.claude/commands/`) | Commands from a `.claude/` reachable from cwd | **Stops at the first project boundary.** A directory containing `CLAUDE.md` or `.git` is treated as a project root; the walk does not cross above it. |
| **Auto-memory** (`~/.claude/projects/<encoded-cwd>/memory/`) | One directory, keyed by the exact launch cwd | **No walk.** Each cwd has its own memory bucket; subdirectories don't inherit a parent's memory. |

The load-bearing consequence: **a repo is a project boundary** (it has both `CLAUDE.md` and `.git`). Slash commands defined *above* a repo — e.g., in `~/work/.claude/commands/` — will **not** be found when you launch `claude` from inside `~/work/some-repo/`. So skills must live where they'll be found: at the repo root's `.claude/commands/`. This is standard Claude Code project layout, and it has a bonus — web Claude Code (which clones a single repo) picks them up too.

CLAUDE.md, by contrast, composes exactly as you'd hope. A session in `~/work/some-repo/` loads, merged:

1. `~/work/some-repo/CLAUDE.md` — repo context
2. `~/work/CLAUDE.md` — **domain layer** (note: a root `CLAUDE.md`, not `~/work/.claude/CLAUDE.md` — see below)
3. `~/.claude/CLAUDE.md` — **universal layer** (formatting, communication style, working habits)

**Domain-level CLAUDE.md goes at the domain root** (`~/work/CLAUDE.md`), not inside a `.claude/` subdir. The walk reliably picks up a root `CLAUDE.md` at each ancestor level; a `~/work/.claude/CLAUDE.md` does not load the same way. (Only `~/.claude/CLAUDE.md` — the universal user-level file — is special.)

Memory follows the launch cwd. Launch from `~/work/some-repo/` and memory comes from the bucket keyed to that path; launch from `~/work/` and it's a different bucket. Pick one launch point per context and stay consistent, or you'll scatter memory across buckets.

## Scoping Strategy

The architecture in this guide assumes you have **distinct domains** that should not bleed into each other. The most common shape:

- **Work** — your day job, where you spend most professional time
- **Personal** — everything else, often subdivided

You may have more (multiple clients, multiple businesses, family vs. household vs. building projects). The mechanism is the same regardless of count.

The hardest part isn't technical — it's discipline:

- Always start a chat in the right Project (claude.ai)
- Always `cd` into the right domain (Claude Code)

The system can't enforce that. But it can make the right thing easy: per-domain shortcut aliases (`cwork`, `cpersonal`), domain-rooted Project boards, and visible cues in your shell prompt all reduce the friction of being in the right place.

## The Three-Layer Pattern

Universal → Domain → Repo. Each layer adds specificity — but remember from Config Resolution that the layers compose cleanly for **CLAUDE.md** while **skills resolve from the repo root only**.

**Universal layer (`~/.claude/`)** — applies everywhere. Things true regardless of context:

- Output style (file references, markdown formatting, lists vs prose)
- Communication preferences (terse vs verbose, when to confirm, when to act)
- Working habits (commit conventions, test-first preferences, etc.)

**Domain layer (`~/<domain>/CLAUDE.md`)** — a root `CLAUDE.md` at the domain dir, applies inside one domain:

- Domain-specific conventions, tone, and vocabulary (e.g., a different register for personal vs work)
- A map of the domain's repos

(Domain-level **skills** don't resolve via the walk — the repo boundary blocks them. If you want a skill available across a domain, put it in the domain's "hub" repo and launch from there, or aggregate skills into a domain-root `.claude/` and launch from the domain root as a deliberate convenience — see below.)

**Repo layer (`<repo>/.claude/` + `<repo>/CLAUDE.md`)** — applies to one repo, and is where skills actually live:

- Skills (`.claude/commands/`) and subagents (`.claude/agents/`) — committed in the repo, standard Claude Code layout, found when you launch from inside the repo
- Repo context in `CLAUDE.md`

The rule of thumb for CLAUDE.md: **put a setting at the highest layer where it's still true.** For skills, there's effectively one place: the repo whose work they operate on. Skills that span repos live in the repo you launch from to do that cross-repo work (a planning/hub repo), referencing siblings by relative path (`../other-repo/...`).

### Optional: a domain-root skill aggregation

If you frequently launch from a domain root (`~/work/`) for cross-repo work, you can aggregate skills from your repos into `~/work/.claude/` via per-file symlinks (a `setup.sh` step). This is a personal convenience — it makes skills resolve when cwd is the domain root itself (not a repo boundary). Teammates don't need it; they clone the hub repo and launch from inside it.

***

# Part 2: Architecture Patterns

## Directory Layout

A typical layout for two domains:

```
~/                                          
├── .claude/                                  ← universal Claude config (CLAUDE.md, settings.json)
├── .bashrc / .bash_aliases / .bash_functions ← universal shell
├── .gitconfig                                ← universal git
├── .gitconfig-<work>                         ← work-scoped git overrides
│
├── work/                                     ← your day job's parent dir
│   ├── CLAUDE.md                            ← work domain layer (root file, not .claude/)
│   ├── .claude/                             ← OPTIONAL: aggregated skills for domain-root launches
│   ├── <hub-repo>/                          ← e.g. a planning repo; carries shared skills at its .claude/
│   │   ├── .claude/commands/               ← skills (found when you launch from here)
│   │   └── CLAUDE.md
│   ├── <repo>/                              ← other work repos
│   └── ...
│
└── personal/                                 ← everything else
    ├── CLAUDE.md                            ← personal domain layer (root file, not .claude/)
    ├── dotfiles/                            ← your dotfiles repo (stow source for ~/ + domain CLAUDE.md backups)
    ├── <hub-repo>/                          ← personal analog of the work hub repo (skills at its .claude/)
    ├── <domain1>/                           ← personal subdomain repos
    ├── <domain2>/
    └── ...
```

Adapt names to your preferences. The load-bearing shape: universal config at `~/`, a root `CLAUDE.md` at each domain dir, and **skills committed at each repo's own `.claude/`** (launch from inside the repo). The domain `.claude/` aggregation is an optional convenience for cross-repo launches.

## GitHub Home Strategy

Where do your repos live on GitHub? The choices:

| Option | When it fits |
|--------|--------------|
| **Your user account** | Solo work; no transfer plans; simple permission model |
| **An org you own** | Work you might commercialize, accept collaborators on, or transfer; needs distinct billing or policies |
| **An org you don't own** (employer, client) | Work that belongs to someone else |

A common pattern:

- Work repos → your employer's or client's org (not yours to reshape)
- Personal life repos (family, household, journaling) → **your user account** (no transfer scenario, no need for org overhead)
- Personal commercial / collaborative projects → **a personal org** (clean transfer story if you ever sell)
- Side businesses → **a separate org per business** (distinct legal entity, distinct identity)

The decision criterion: is there a future scenario where this code or its ownership might need to move? If yes, org. If never, user account is simpler.

## Git Identity Routing

If you commit to multiple domains, you probably want different commit identities — work email for work commits, personal email for personal. Manual per-repo setup is tedious and error-prone.

Better: route automatically by directory. Modern git supports `includeIf` directives that load a config file conditionally.

```ini
# ~/.gitconfig (universal)
[user]
    name = Your Name
    email = personal@example.com

[includeIf "gitdir:~/work/"]
    path = ~/.gitconfig-work
```

```ini
# ~/.gitconfig-work
[user]
    email = work@example.com
```

Any commit made under `~/work/...` uses the work email automatically. Anywhere else uses the personal default. No per-repo setup, no remembering to switch.

## Stow Operations

[GNU stow](https://www.gnu.org/software/stow/) symlinks files from a source directory into a target directory based on the source's internal structure. The use case here: keep all your dotfiles in one git repo (the **source**), and have stow create the symlinks into the right places (the **target** — your home dir).

Why this pattern:

- One repo holds all config — bash, git, Claude, anything else you want versioned
- Cloning the repo on a new machine + running one script reproduces your entire environment
- Edits go in the repo (versioned) instead of in `~/` (forgotten)

A typical dotfiles repo structure:

```
dotfiles/
├── claude-user/.claude/        ← stows to ~/.claude/
│   ├── CLAUDE.md
│   ├── settings.json
│   └── projects/<cwd>/memory/  ← optional: version-control auto-memory
├── claude-domains/             ← stows domain-root CLAUDE.md files
│   ├── work/CLAUDE.md          ← stows to ~/work/CLAUDE.md
│   └── personal/CLAUDE.md      ← stows to ~/personal/CLAUDE.md
├── bash/                       ← stows to ~/
│   ├── .bashrc
│   ├── .bash_aliases
│   └── .bash_functions
├── git/                        ← stows to ~/
│   ├── .gitconfig
│   └── .gitconfig-work
├── setup.sh                    ← orchestrates the stow operations
└── verify.sh                   ← test suite (Part 4)
```

After `setup.sh` runs, `~/.bashrc` is a symlink pointing into the dotfiles repo. Edits made there (via the symlink) write through to the repo. Commit and push to sync across machines. The `claude-domains` package uses `stow --no-folding` so the domain `CLAUDE.md` symlinks land inside the existing `~/work` and `~/personal` dirs without stow trying to symlink the whole directory.

**What to stow, what not to:**

- **Stow** the universal layer (`~/.claude/`, `~/.bashrc`, etc.) — identical on every machine.
- **Stow** domain-root `CLAUDE.md` files and (optionally) auto-memory — their natural home (`~/work/CLAUDE.md`, `~/.claude/projects/.../memory/`) isn't itself a git repo, so dotfiles is how you version them.
- **Don't stow skills.** Skills live at the repo root's `.claude/` and are versioned in that repo — team-shared skills in the team repo, where teammates get them on clone with no stow setup at all. Wrapping a team `.claude/` in a stow package (e.g., `stow/claude-project/.claude/`) is an antipattern: it puts the skills at a non-standard path that the slash-command walk can't find from inside the repo, breaking the canonical launch-from-repo flow. Put skills where Claude Code expects them — `<repo>/.claude/` — and commit them in the repo.

> **Hard-won lesson:** an early version of this architecture stowed a team `.claude/` from a `stow/claude-project/` wrapper into a domain-level `.claude/`. It broke per-repo launches (slash commands stopped resolving) because the repo boundary blocks the upward walk. The fix was to move skills to each repo's own root `.claude/` (standard layout) and treat any domain-level aggregation as a personal convenience built with per-file symlinks, not a stow package wrapper.

## Global Settings Reference

When you (or a future you, or a future agent) want to "update my global settings to do X," this table answers: which file owns X, and does anything need to re-source after the change?

| Concern | File | Re-source needed? |
|---------|------|-------------------|
| Bash aliases | `dotfiles/bash/.bash_aliases` | Yes (`source ~/.bashrc`) |
| Bash functions, prompt, init logic | `dotfiles/bash/.bashrc` | Yes |
| Environment variables (loaded at shell start) | `dotfiles/bash/.bashrc` | Yes |
| Git config (user, aliases, defaults) | `dotfiles/git/.gitconfig` | No (re-read per command) |
| Git work-scoped overrides | `dotfiles/git/.gitconfig-work` | No |
| Claude universal CLAUDE.md (style, habits) | `dotfiles/claude-user/.claude/CLAUDE.md` | No (per-session) |
| Claude universal settings.json (plugins, theme, statusline) | `dotfiles/claude-user/.claude/settings.json` | No (Claude Code restart) |
| Domain-level Claude config (tone, conventions) | `dotfiles/claude-domains/<domain>/CLAUDE.md` → stows to `~/<domain>/CLAUDE.md` | No |
| Auto-memory (versioned) | `dotfiles/claude-user/.claude/projects/<encoded-cwd>/memory/` | No |
| Per-repo skills / subagents | `<repo>/.claude/{commands,agents}/` (lives in the repo, committed there) | No |
| Per-repo Claude context | `<repo>/CLAUDE.md` (lives in the repo) | No |
| GitHub notification routing | GitHub Settings UI (manual) | N/A |

**The routing rule:** anything in `dotfiles/` requires commit + push to sync across machines. Anything outside dotfiles is scoped to where it lives.

***

# Part 3: Multi-Agent Workflow via GitHub

This is the operating model that the architecture in Parts 1–2 enables. **GitHub is the shared substrate.** Different Claude surfaces play different roles, hand off through commits, and use the same source of truth per domain.

## The Model

Four roles, four surfaces, one substrate per domain:

| Role | Best for thinking/design | Best for execution | Outputs |
|------|--------------------------|--------------------|---------|
| **Planner** | claude.ai chat or Project | (outputs are documents) | Markdown files in `docs/analysis/` or `docs/plans/` |
| **Coordinator** | claude.ai chat or Project | Local Claude Code (`gh` + GraphQL — chat can't write to GitHub today) | GitHub Issues + Project board state |
| **Implementer** | Local Claude Code | Local Claude Code | Commits, PRs, file changes |
| **Autonomous Worker** | Web Claude Code | Web Claude Code | Branches, PRs, status updates on cloud-hosted sessions |

The Planner and Coordinator can do their *thinking* in claude.ai — analysis, drafting issue text, designing hierarchy. But every **write** to GitHub today happens through Claude Code, because claude.ai's GitHub connector is read-only and the chat surface can't reach `api.github.com` from its code execution sandbox. The handoff is: chat produces the design; local Claude Code executes the writes via `gh` CLI and GraphQL mutations. See [claude.ai's GitHub connector: read-only today](#claudeais-github-connector-read-only-today) in Part 5 for details and workarounds.

Roles aren't tied to specific Claude instances — any agent can take on any role. The naming captures *intent* so you know which surface fits which task.

## File Conventions

Every repo (across every domain) follows the same layout for non-code artifacts:

```
<repo>/
├── README.md            # Orientation: what this repo is, layout, doc pointers (humans first)
├── CLAUDE.md            # Agent behavior conventions for this repo
├── STATUS.md            # Handoff: what just happened + what's next + where to find things
├── docs/
│   ├── analysis/        # Planner outputs: <YYYY-MM-DD-topic>.md
│   ├── plans/           # Coordinator outputs: <topic>.md
│   ├── decisions/       # ADRs: <NNNN-title>.md
│   └── runbooks/        # Operational procedures
└── (code / data / whatever)
```

### Three-role doc separation

| Doc | Audience | What it answers | Volatility |
|---|---|---|---|
| **README.md** | Humans landing on the repo (GitHub web, fresh clone, future-you) | What is this? Who is it for? Where do the other docs live? | Low — stable framing |
| **CLAUDE.md** | Claude agents in this repo | How should agents behave here? What conventions apply? | Low/medium — stable instructions |
| **STATUS.md** | Next session / next agent | Where are we right now? What handoff signals? What's next? | High — updated every session |

They cover orthogonal concerns: orientation (README), behavior (CLAUDE), state (STATUS). Don't conflate them — when STATUS keeps growing past a screen, the parts that aren't volatile probably belong in README.

### Commit message prefixes

Lightweight semantic tags so subsequent agents can scan history quickly:

| Prefix | Meaning |
|--------|---------|
| `analysis:` | Planner committed an analysis doc |
| `plan:` | Coordinator committed a plan |
| `impl:` | Implementer doing the work (often referencing an issue: `impl: #42 add X`) |
| `status:` | STATUS.md update only |
| `feat:`, `fix:`, `docs:`, `refactor:`, `chore:` | Standard conventional commits for code |

### STATUS.md template

Three sections, all forward-pointing — no rolling history (git is the history):

```markdown
# STATUS — <repo>

**Last updated:** YYYY-MM-DD

## What just happened
(1–3 bullets from this session only)

## What's in progress
(Issues currently claimed by an active session — see Concurrency & Claiming.
 Format: `- #N — <brief> (claimed YYYY-MM-DD by session <name>)`)

## What's next
(1–3 concrete next actions, each linking to an issue or doc)

## Where to find things
(Pointers: functions/layout → README; active work → epic; design history → docs/decisions/; etc.)
```

The next agent reads STATUS first. README explains what the repo *is*; STATUS explains where the work *is* and what's *currently claimed*. They complement each other.

### README.md template

For a hub repo (one whose function generates ongoing build work — a planning/pipeline repo, a tooling repo, etc.):

```markdown
# <repo>

(One-sentence mission. Link to the substrate it operates on if external.)

## Functions

| Function | Label | What it builds |
|---|---|---|
| (3–5 functions max; "what am I building that leverages the substrate") |

## Layout

(Table of paths → contents. Pointer-heavy, no prose.)

## See also

- CLAUDE.md — agent conventions
- STATUS.md — current state
- (other guides, related repos, external boards)

## Out of scope

(Explicit non-scope items so they aren't filed accidentally.)
```

For a leaf repo (work happens here but no ongoing build queue — a domain repo like `home` or `ifl`): drop the Functions section, keep mission + layout + see-also.

The function model: ask "what am I building that leverages the substrate?" Not "what work happens here." Outputs (reports, board state, planning artifacts) are downstream consumption — they don't track as functions of the repo.

## GitHub Projects as Task Substrate

A GitHub Project (v2) with custom fields turns the issue tracker into a planning system. Status + Priority + Type + Category + Theme + Effort + dates give you enough dimensionality to plan real work: who's doing what, when, in what category, at what priority. The board's views (Kanban for daily, Table for bulk edits, Roadmap for timeline) are different slices of the same data.

### Recommended custom field schema

| Field | Type | Suggested values | Purpose |
|-------|------|------------------|---------|
| **Status** | Single-select | ToDo, In Progress, Done (plus Backlog and Pending Release for projects with release cadence) | Workflow state |
| **Priority** | Single-select | P0, P1, P2, P3 | Urgency. P0 = today, P3 = backlog |
| **Type** | GitHub built-in issue type | Bug, Feature, Task | What kind of work |
| **Category** | Single-select | Epic, User Story | Planning hierarchy level (parent items only — leaves use Type=Task and leave Category empty) |
| **Theme** | Single-select | (Your taxonomy — see below) | Horizontal categorization |
| **Effort** | Number | 1, 2, 3, 5, 8 | Optional estimation |
| **Start / End** | Date | YYYY-MM-DD | Optional scheduling |

**Theme** is the horizontal cut across your hierarchical structure. For work, it's typically product areas (Auth, Billing, Search, etc.). For personal, life domains (Family, Household, Legal, Health, Finance, etc.).

### Hierarchy via Category + sub-issues

The Category field denotes planning level. GitHub's sub-issue feature creates real parent/child relationships:

```
Epic: "Saturday dinner party for 8"          (Category=Epic, Theme=Household)
├── Story: "Menu + shopping"                  (Category=User Story)
│   ├── "Plan the menu"                       (Type=Task)
│   ├── "Grocery run Friday evening"          (Type=Task)
│   └── "Grab fresh herbs Saturday morning"   (Type=Task)
├── Story: "Prep + cook"                      (Category=User Story)
│   ├── "Marinade chicken Friday night"       (Type=Task)
│   └── "Start sauce at 4pm Saturday"         (Type=Task)
└── Story: "Hosting setup"                    (Category=User Story)
    ├── "Set the table by 6pm"                (Type=Task)
    └── "Build the playlist"                  (Type=Task)
```

Most work won't be this deep. Use hierarchy when it earns its keep.

### Closing keywords for automation

When a PR closes an issue, use `closes #N`, `fixes #N`, or `resolves #N` in the body. GitHub populates `closingIssuesReferences` and (if you set up GitHub Actions for it) the Status field auto-transitions on PR merge. Plain `#N` mentions are informational — no automation.

### One board per domain, or one shared board?

Start with **one shared board** if you're new to this. Easier to maintain, simpler mental model. As one domain accumulates enough volume that the shared board feels cluttered, spin off a domain-specific board.

## Templating Project Boards

If you already have a Project board with a schema you like (a work board, for example), don't recreate the schema by hand for new boards.

**Two related but distinct mechanisms:**

**The Template feature** — a project marked as a template appears in the org's "New project" dialog under Templates. Children created from it inherit views, custom fields, draft issues + field values, workflows (except auto-add), and insights. **Templates are an organization-only feature.** User accounts can't host templates.

**Copy a project** — works on any project regardless of template flag. Available in the UI under the project's ⋯ menu, or via the `copyProjectV2` GraphQL mutation. Lets you specify a target owner (org or user account). Useful when your source is in an org and your destination is your user account, or when you want one-off copies without going through the Template UI.

**Recommended pattern:**

1. Put your reusable schema in an org you control — e.g., `<your-org>/<purpose>-template`
2. Mark it as a template (via project Settings → Manage templates → Make template, or `markProjectV2AsTemplate` mutation)
3. To create a new working board: either use the org's "New project" → Templates dialog, or call `copyProjectV2` with the template's ID as `projectId` and the desired target as `ownerId`
4. After copy, adjust field options for the new context via `updateProjectV2Field` mutations (see API note)

**API note — editing single-select options.** There is no `updateProjectV2SingleSelectField` mutation (a natural guess that fails with "Field doesn't exist on type Mutation"). The real mutation is **`updateProjectV2Field`** with a `singleSelectOptions` argument — and it *replaces* the full option list, so include existing options you want to keep. Also: the `singleSelectOptions` array can't be passed via `gh api graphql -F` (it stringifies); pass the whole query+variables as a JSON body with `gh api graphql --input <file>`. To *add* fields, use `createProjectV2Field`; to flip the template flag, `markProjectV2AsTemplate`. All work identically on templates (they're regular ProjectV2 objects with a boolean flag).

**Auth note:** GitHub Apps (installation tokens) can't access user-level Projects v2 — a documented GitHub limitation. PATs and OAuth tokens (e.g., the token from `gh auth login`) work fine. For agent-driven flows using `gh api graphql`, this is a non-issue. For flows using a Claude GitHub App installation token, you'll need to either keep the project at the org level or use a different auth path.

The copy inherits fields, views, and field options. Items don't copy — the new board starts empty. After copying, adjust field options to fit the new context:

- Use `updateProjectV2Field` (with `singleSelectOptions`) to change Theme options to the new vocabulary
- Use the same mutation to simplify Status (drop values you don't need) — remember it replaces the full list
- Leave Priority, Type, Effort, Start/End as-is

This pattern saves significant manual configuration and ensures consistency across boards.

## Concurrency & Claiming

Multiple agents reading the same backlog (parallel local sessions, autonomous workers, scheduled jobs) need a way to avoid picking up the same work. The architecture uses a **two-layer claim** that reuses what's already there — no new fields, no bot accounts.

**Layer 1 — Lock signal (board Status):**

The agent's first action when starting work on an issue is to flip the board Status from `ToDo` → `In Progress` via `updateProjectV2ItemFieldValue`. Other agents read Status before claiming and skip anything not in `ToDo`. This is the queryable, board-visible lock.

**Layer 2 — Traceability (STATUS.md):**

The session adds the issue to its repo's `STATUS.md` under a "What's in progress" section, then commits the update with the `status:` prefix. Other sessions `git pull` and read STATUS.md (the first-read convention) and see what's claimed in human-readable form.

```markdown
## What's in progress

- #176 — /theme-operator Audit-Reconcile (claimed 2026-05-28 by session `substrate`)
- #180 — issue-reviewer PR-title citations (claimed 2026-05-28 by session `accounting`)
```

When the work lands (PR merged, issue closed), the session moves the entry from "What's in progress" to "What just happened" and commits.

**Claim flow:**

```
1. git pull (fresh STATUS.md)
2. Read STATUS.md "What's in progress" — see what other sessions are doing
3. Pick an issue from "What's next" (or planning's open queue)
4. Re-check the board Status — confirm still ToDo
5. Flip Status → In Progress
6. Update STATUS.md "What's in progress" with the issue ref + session name
7. Commit STATUS.md ("status: claim #N for <work>"), push
8. Do the work
9. When done: remove from "In progress", add to "What just happened", commit, push
```

**Stale claims:** if an agent dies mid-task, Status stays at `In Progress` with no PR landing. The simplest recovery is a periodic board-hygiene pass (e.g., `/project-sync` in QSI's pipeline) that surfaces stuck items and offers to revert them. Threshold is workload-dependent.

**Race window:** the gap between read and write is tiny and accepted. At handful-of-agents scale this is acceptable noise — the cost of strict locking (a distributed lock service, optimistic concurrency tokens) outweighs the cost of an occasional double-claim. Add stricter coordination only if it becomes a real problem.

**What's not covered here:** file-level conflicts (two agents editing the same file) — out of scope for this design; git handles it via merge conflicts.

## Working Patterns

Concrete workflows showing how the multi-agent model plays out.

### Pattern A: Plan in chat, implement locally

When you have an open-ended question that needs analysis before action.

1. **Planner (claude.ai chat or Project)** — analyze across repos via GitHub connector. Produce an analysis doc as an artifact or codeblock.
2. **Implementer (local Claude Code)** — "Create `docs/analysis/YYYY-MM-DD-topic.md` with this content: [paste]." Commit with `analysis:` prefix.
3. **Coordinator design (chat)** — review the analysis, identify discrete tasks, sketch issue titles, bodies, and field values. Output as a structured list (codeblock or committed `docs/plans/<topic>.md`).
4. **Coordinator execution (local Claude Code)** — paste or read the structured list, run your issue-creation skill or `gh issue create` + GraphQL field mutations to actually write the issues to GitHub.
5. **Implementer (local Claude Code)** — work the issues, commit with `impl:` prefix.

### Pattern B: Fire-and-forget parallel work

When you have multiple long-running tasks and don't want them all on your laptop.

1. **Planner (chat)** — frame each task as a self-contained brief.
2. **Autonomous Worker (web Claude Code)** — launch 2–3 cloud sessions, each with one brief. They run in cloud VMs, persist if you close the browser.
3. **You** — do other things. Check progress later.
4. **Implementer (local Claude Code)** — review what each cloud session produced, merge or revise, commit.

### Pattern C: Audit then remediate

When you need to find issues, then fix them.

1. **Planner (chat)** — run an audit. Produce findings.
2. **Coordinator (chat designs, local CC executes)** — chat structures findings into a prioritized issue list with field values; local Claude Code creates the issues.
3. **Implementer (local Claude Code)** — work through them.

### Pattern D: Daily startup ritual

When you sit down to work in a domain.

1. `cd ~/<domain>/<repo> && claude`
2. **Implementer's first action:** read `STATUS.md` to understand where things stand.
3. **You** — give direction based on what STATUS.md surfaced.
4. **Implementer** — work, commit with appropriate prefixes.
5. **Before ending:** update STATUS.md.

## CLAUDE.md Boilerplate

Drop this into every domain repo's `CLAUDE.md` so every agent knows the rules:

```markdown
## Multi-Agent Workflow

This repo participates in a multi-agent workflow over GitHub. Other Claude
sessions may have been here recently or be about to arrive. Conventions:

- **Read STATUS.md first.** It captures where things stand.
- **End every session by updating STATUS.md.** What changed, current state,
  open questions, handoff signals.
- **File layout:**
  - `docs/analysis/` — analysis docs (planner outputs)
  - `docs/plans/` — plans (coordinator outputs)
  - `docs/decisions/` — ADRs
  - `docs/runbooks/` — operational procedures
- **Commit prefixes:** `analysis:`, `plan:`, `impl:`, `status:`, plus standard
  `feat:`/`fix:`/`docs:`.
- **GitHub Issues are the task graph.** Open issues = pending work. Each
  work item gets an issue on the domain's Project board with Type, Priority,
  Category, Theme set.
- **Closing keywords (`closes #N`, `fixes #N`, `resolves #N`)** in PR bodies
  trigger automation. Plain `#N` mentions are informational only.
```

Domain-specific content goes after the boilerplate.

***

# Part 4: Migration Patterns

If you're already using Claude Code with some setup in place, you're migrating, not greenfield-installing. This section describes the **shape** of a safe migration — not a step-by-step plan. A Claude Code agent should read your current state and produce a plan specific to you, using these patterns as guidance.

## Safety practices

These apply throughout, regardless of where you're starting from.

**Snapshot first.** Before any structural change, copy critical files to a backup directory:

- Current `.bashrc`, `.bash_aliases`, `.bash_profile`, `.zshrc` (whichever apply)
- Current `.gitconfig` and any `.gitconfig-*` files
- Current `~/.claude/` contents
- A directory listing of where repos currently live
- A `git status` summary across all repos (to surface uncommitted work)

**Symlinks before physical moves.** When restructuring directory layout, create symlinks from the new locations to the old locations first. This lets you validate Claude Code resolution, run skills, do real work — all from the new paths — while the actual files stay where they were. Once you're confident, replace symlinks with physical moves (mv, not cp — keep the inode if your filesystem supports it).

**Verify after each phase.** Don't push through multiple phases hoping nothing broke. A test suite (described below) makes this cheap.

**Reversibility.** Every phase should leave a rollback path. The backups from "Snapshot first" plus symlinks-before-moves give you that.

## Migration phase shape

A typical migration walks through this sequence. Skip phases that don't apply to your starting state.

### 0. Pre-flight

- Capture snapshots
- Identify in-flight work across all repos (uncommitted changes, open branches, work-in-progress)
- Note any customizations in your current shell/git config that need to be preserved
- Decide on placeholder names that you'll use throughout: `<work-domain>`, `<personal-domain>`, etc.

### 1. Memory hygiene

If you've been using claude.ai over time, your account-level memory probably contains content that crosses domains — work details in personal contexts, sensitive personal info attached to work memories. Migrating to clean domain separation is a good time to clean this up.

- Add memory exclusions for sensitive topics (legal matters, health, finances, anything domain-specific that shouldn't surface in unrelated contexts)
- Sweep top-level claude.ai memories for cross-domain leakage
- Audit local Claude Code memory files for sensitive content stored under non-sensitive paths

### 2. GitHub structure

- Decide which orgs you need (Part 2: GitHub Home Strategy)
- Create the orgs you don't have yet
- Install the Claude GitHub App on each org so claude.ai can read them
- Configure notification routing so cross-domain mail goes to the right inboxes (most useful: per-org email routing if you use distinct work/personal addresses)

### 3. Directory restructure

- Create the new top-level structure (e.g., `~/work/`, `~/personal/`)
- Symlink existing repos into the new locations based on their remotes
- Validate Claude Code can find skills and config from the new locations
- Defer the physical move to the cleanup phase

### 4. Dotfiles repo + stow + test suite

This is the heart of the architecture.

- Create a `dotfiles` repo (on your user account or a personal org)
- Organize into packages (`claude-user/`, `claude-domains/`, `bash/`, `git/`)
- Write a `setup.sh` that runs stow operations
- Write a `verify.sh` test suite (next section) that confirms everything works
- Run setup, run verify, iterate until verify passes

### 5. Multi-agent scaffolding

For each domain repo:

- Scaffold `docs/{analysis,plans,decisions,runbooks}/` (with `.gitkeep` files to keep empty dirs in git)
- Create `CLAUDE.md` with the multi-agent boilerplate from Part 3 plus domain-specific content
- Create `STATUS.md` with current state
- Create or copy a Project board (use the Copy project pattern from Part 3 if you have an existing board to template from)
- Connect repos to the board

### 6. Workflow smoke test

Before declaring the architecture working, exercise the full pattern on one real task:

- Pick a concrete, small piece of actual work in a domain
- Plan it in chat (Planner role)
- Commit an analysis doc (Implementer)
- Create one or more issues with proper field values (Coordinator)
- Work an issue, commit with `impl:` prefix, push
- Update STATUS.md, commit with `status:`

If anything in this sequence feels clunky or reveals missing pieces, capture it as a future improvement and address before considering the migration complete.

### 7. Cleanup

- Replace symlinks with physical moves
- Update local git remote URLs if any have changed (e.g., username case changes)
- Re-run setup + verify to confirm nothing broke in the physical move
- Archive obsolete repos
- Commit the architecture documentation (and this guide, if you've adapted it) into one of your repos for future reference

## The verify.sh pattern

A test suite replaces "use it for a few days and see if it works" with concrete pass/fail probes. Typical sections:

```bash
#!/usr/bin/env bash
# verify.sh — confirms the multi-domain architecture is set up correctly.
# Exit 0 = all pass, non-zero = at least one failure.

# Section 1: Stow integrity
# - Every expected symlink exists at the target location
# - Every symlink resolves to a real file in the source repo

# Section 2: Universal layer cleanliness
# - ~/.claude/CLAUDE.md contains no domain-specific content
# - (Test: grep for known domain-specific terms; should return nothing)

# Section 3: Shell aliases load
# - Run a fresh interactive bash that sources .bashrc
# - Confirm each expected alias is defined

# Section 4: Git identity routing
# - cd into a personal-context repo, check user.email = personal address
# - cd into a work-context repo, check user.email = work address
# - The includeIf directive should make this automatic

# Section 5: Domain + repo layers exist
# - ~/<each-domain>/CLAUDE.md exists (domain layer, root file)
# - Each hub repo's <repo>/.claude/commands/ has the expected skills
# - (Optional) the domain-root .claude/ aggregation resolves if you use it

# Section 6: GitHub auth
# - gh auth status succeeds
# - Authenticated as the expected user

# Summary
# - Count pass/fail, print failure messages, exit appropriately
```

The script is idempotent and fast. Run it at the end of every migration phase and any time you're not sure if something is working.

## Tailoring This Pattern

**For a Claude Code agent helping someone migrate to this architecture:**

Before producing a phase-by-phase plan, inspect the user's environment and ask them to confirm assumptions. At minimum:

1. **Current directory layout.** Where do their repos live now? Is there an existing parent directory pattern, or are repos scattered?
2. **Existing dotfiles.** Is there already a dotfiles repo, a stow setup, an `~/.bashrc` with significant customizations? What's its current state?
3. **Domain count and names.** How many distinct domains? What names do they want for top-level directories? (Don't default to "work/personal" — let them name it.)
4. **GitHub structure.** What orgs exist now? What's their user account name? Are there cross-domain orgs?
5. **Identity strategy.** How many email addresses do they use? Do they want git identity routing, and if so, how should it route?
6. **Sensitive scope.** Are there topics or domains they want explicitly excluded from cross-domain context (legal matters, health, finances, family law, tenant disputes, etc.)?
7. **Existing project boards.** Do they already have a Project board they want to template from, or are they creating boards from scratch?
8. **Migration vs greenfield.** Are they restructuring existing work, or starting fresh? This determines whether you focus on safe migration (symlinks, snapshots) or initial setup.

Don't ask all eight in one turn. Ask the ones that matter most for the next decision, get the answer, proceed. Pace yourself to the user.

The output of this conversation should be a phase-by-phase plan with:

- Specific paths and names (based on their answers)
- Commands they can run (Claude Code can run most of them; manual UI steps clearly marked)
- Verification checks after each phase
- Checkpoints where they confirm before proceeding
- A tracker of action items, manual steps required, and follow-on work deferred

Treat each phase as independently shippable — they should be able to stop after any phase and have a working (if partial) system.

***

# Part 5: Reference

## Stow primer

GNU stow is a symlink farm manager. Given a source directory with packages (subdirectories), it creates symlinks in a target directory mirroring each package's internal structure.

```
source/                          target/ (after stow)
├── pkg1/                        ├── file-a -> source/pkg1/file-a
│   ├── file-a                   └── subdir/
│   └── subdir/                      └── file-b -> source/pkg1/subdir/file-b
│       └── file-b
└── pkg2/
```

Stow flags worth knowing:

- `-S` — stow (create symlinks)
- `-D` — unstow (remove symlinks)
- `-R` — restow (unstow then re-stow; useful after package changes)
- `-d <dir>` — source directory
- `-t <dir>` — target directory
- `-v` — verbose
- `-n` — dry run (preview without changes)

Stow refuses to overwrite real files (only symlinks under its management). Move real files to a backup before stowing if they exist at the target.

## Common pitfalls

**Notifications cross-talk.** Default GitHub notifications go to one email regardless of org. Set up per-org email routing in GitHub Settings → Notifications → Custom routing to keep work and personal mail separate.

**Memory leakage across domains.** Claude memory is account-scoped, not Project-scoped. Content from a personal chat can surface in a work chat if you haven't added explicit exclusions. Audit memory regularly and add exclusions for sensitive topics.

**Username case sensitivity in git remotes.** If you change a GitHub username's case (e.g., `Foo` → `foo`), existing local remotes still have the old case. Most operations work due to case-insensitive matching, but some tooling breaks. Update remotes with `git remote set-url` after a case change.

**Web Claude Code only sees the cloned repo.** This is why skills belong at the repo root's `.claude/` — a web session that clones the repo gets them automatically. The only thing web sessions miss is the domain-root `CLAUDE.md` and the optional domain-level skill aggregation (both live outside the repo). Cross-repo skills that reference siblings by relative path (`../other-repo/...`) also won't resolve in a web session, since the siblings aren't cloned. For those, accept a smaller cloud skill set or use a submodule.

**claude.ai connector not seeing a new org.** After installing the Claude GitHub App on a new org, the claude.ai connector cache can lag. Disconnect and reconnect the GitHub connector in claude.ai settings.

## When submodules become necessary

The architecture in this guide avoids submodules in most cases — directory-tree resolution does the job for local Claude Code. Submodules become useful when:

1. **Web Claude Code sessions need shared skills.** Cloud VMs only see one cloned repo. To make a skill available in a web session, it has to be in that repo — directly or via submodule.
2. **A skill is genuinely cross-domain.** A skill that runs in both work and personal contexts is a natural candidate for a shared-skills repo referenced as a submodule from each domain.

Submodule mechanics:

```bash
# Add a submodule to a repo
git submodule add <url> .claude/skills/shared
git commit -m "feat: add shared-skills submodule"

# Update the submodule pointer to a newer commit
cd .claude/skills/shared && git pull origin main && cd ../../..
git add .claude/skills/shared
git commit -m "chore: bump shared-skills"

# Clone with submodules included
git clone --recursive <url>
# Or post-clone:
git submodule update --init --recursive
```

## claude.ai's GitHub connector: read-only today

The GitHub connector available in claude.ai is read-only — it provides repo file contents to chat sessions but does not support GitHub writes. Specifically:

- ❌ Cannot create issues, comments, or PRs
- ❌ Cannot modify Project boards, fields, or field values
- ❌ Cannot mutate any GitHub state
- ✅ Can read repo files, READMEs, source code, structure

The underlying constraint: claude.ai's code execution sandbox blocks `api.github.com` at the network proxy layer. Even with a valid PAT, scripts in chat (including those packaged as skills) get HTTP 403. This means a "skill on claude.ai" can't reach the GitHub API for writes — it's the chat surface's network policy, not a skill capability gap. Skills running in local Claude Code have full network access and can write to GitHub freely via `gh` CLI or GraphQL.

**What this means for the multi-agent workflow:**

- **Planning, designing, drafting** all happen fine in claude.ai chat — analyses, issue text, hierarchy design, field values
- **Actual writes to GitHub** (creating issues, updating Project field values, marking templates) happen in Claude Code via `gh` CLI and `gh api graphql` mutations
- Hand off via copy/paste, structured codeblocks, or by having Claude Code read a `docs/plans/<topic>.md` that chat committed

**Workarounds:**

- **Third-party MCP shims** (e.g., Composio's connect-apps) proxy claude.ai to 500+ apps including GitHub. Adds a third-party trust boundary; evaluate against your auth policies.
- **Official GitHub MCP server** — stdio transport, works with local Claude Code. Drop-in alternative to gh CLI if you prefer MCP tooling.

**What to watch:** the GitHub MCP team is aware of the chat-side write gap (there's an open feature request from April 2026). A hosted remote GitHub MCP endpoint with OAuth — comparable to how Gmail/Calendar/Drive connectors work today — would close this gap. When it ships, claude.ai chat becomes able to write directly and the role table's design/execute split collapses.

## Glossary

| Term | Meaning |
|------|---------|
| **Surface** | A distinct Claude product entry point (claude.ai chat, local Claude Code, web Claude Code, etc.) |
| **Resolution walk** | How Claude Code finds config up the directory tree. CLAUDE.md merges from every ancestor; slash commands stop at the first repo boundary; memory is keyed to the exact launch cwd (no walk) |
| **Project boundary** | A directory with `CLAUDE.md` or `.git` at its root. Slash-command resolution does not walk above it — the reason skills must live at the repo root |
| **Universal layer** | `~/.claude/` — applies to every session regardless of where you cd'd |
| **Domain layer** | `~/<domain>/CLAUDE.md` (a root file) — applies inside one work/life domain |
| **Repo layer** | `<repo>/.claude/` (skills, agents) + `<repo>/CLAUDE.md` — applies inside one specific repo; where skills live |
| **Stow source** | A directory containing packages organized for stow (e.g., `claude-user/`, `bash/`) |
| **Stow target** | A destination directory receiving symlinks (typically `~/`) |
| **Project (claude.ai)** | A chat container with its own knowledge, instructions, and memory bucket |
| **Project board (GitHub)** | A v2 Project with custom fields used as a planning/task substrate |
| **Connector** | claude.ai's mechanism for pulling external data (GitHub, Google Drive, etc.) |
| **Substrate (multi-agent)** | The shared state — usually GitHub repo + Project board — that multiple Claude sessions read from and write to |
| **Closing keyword** | `closes #N` / `fixes #N` / `resolves #N` in a PR body; triggers GitHub's auto-link and status automation |

## Adapting This Guide

If you want to fork this guide for your own setup, the parts you'll customize:

- **Domain names** — pick names that fit your life (`~/work/`, `~/clients/`, `~/family/`, etc.)
- **Theme vocabulary** — Project board Theme options reflect your specific domains' subdivisions
- **Boilerplate text** — every reference to "the multi-agent conventions" can adopt your specific terminology if "Planner / Coordinator / Implementer" doesn't fit how you think about it
- **Phase sequence** — the migration shape in Part 4 is one ordering; if your situation calls for a different order, reorder freely

The load-bearing parts that should stay:

- The mental model in Part 1 (it's how Claude Code actually works)
- The three-layer pattern (universal → domain → repo)
- The convention of GitHub as the multi-agent substrate
- The verify.sh test suite pattern (replaces "hope it works")
- Safety practices in migration (snapshot first, symlinks before moves, verify between phases)

***

**End of guide.** Hand this to a Claude Code session along with a description of your current setup, and ask for a tailored migration plan.
