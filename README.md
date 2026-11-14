# task-mgmt: an operating model and tools for running personal and work domains with agents

**Purpose:** A working architecture for using Claude across multiple distinct life or work domains — keeping context appropriate, configuration shared where it should be shared, and isolated where it should be isolated.

**Audience:** Anyone using Claude Code (and adjacent Claude surfaces) who has more than one distinct domain of work — a day job and personal projects; multiple clients; work, family, and side ventures — and wants the agent to behave correctly in each without manual context-juggling.

**Status:** A pattern document, not a step-by-step plan. The architecture is concrete; the migration to get there is described as a pattern that a Claude Code session can tailor to your specific starting state.

***

## Adopting this — hand this URL to Claude Code

The fastest way to adopt this is to let a Claude Code session drive. Open Claude Code (terminal, or [claude.ai/code](https://claude.ai/code) on the web) and paste:

> Read the repo at https://github.com/armodis-ai/task-mgmt end to end. Then inspect my current setup — any existing `~/.claude`, dotfiles, git config, and GitHub account. Walk me through adopting this architecture: the domain **organization**, the config **substrate**, and the **GitHub side** (organizations, repos and project boards). Treat it as a fresh setup or a migration from existing Claude Code usage — check which, and tailor the plan to what I already have. Confirm each phase with me before changing anything.

The agent has enough here to do the work: this repo is the model, [`setup.sh`](setup.sh) + [`template/`](template/) deploy the substrate mechanically, and [`provision.py`](provision.py) puts the GitHub side in place: organizations, repos, project boards and the board config ([Setting up GitHub](#setting-up-github)). The template ships the operating skills that are the same everywhere, the [design loop](#the-design-loop) and the [board command and its skills](#the-board-command-and-skills); the agent authors the skills specific to your work with you.

**Prerequisites:** [Claude Code](https://code.claude.com/docs/en/overview), [GNU Stow](https://www.gnu.org/software/stow/), Python 3, `git` with `user.name` and `user.email` set, and [`gh`](https://cli.github.com/) logged in with the `repo`, `project`, `read:org` and `workflow` scopes (`gh auth login`, then `gh auth refresh -s project,read:org,workflow`).

***

## How to Use This Document

**If you're reading as a human:** read Parts 1–3 to get the mental model. Part 4 describes the migration shape; you'll likely hand it to a Claude Code session along with a description of your current setup and ask for a tailored plan.

**If you're a Claude Code agent helping someone adopt this architecture:** read end-to-end. Part 4 is a pattern, not a plan — your job is to inspect the user's environment (current directory layout, existing dotfiles, GitHub orgs, identity strategy, sensitive content scope), then produce a phase-by-phase plan specific to them. See the "Tailoring This Pattern" section at the end of Part 4 for what to ask before producing the plan.

***

## Quick start (run it)

This repo is both the written model and a runnable template. To stand up the architecture on your own machine:

```bash
git clone https://github.com/armodis-ai/task-mgmt
cd task-mgmt
$EDITOR substrate.conf          # your domains: DOMAINS=(work personal ...)
./setup.sh                      # stow + symlink into ~/: instructions, design loop, board command and skills
# one hub per owner (an organization or your user account): its ops repo holds the owner's config
mkdir -p ~/work/your-org/ops/.task-mgmt && cp hub.example.json ~/work/your-org/ops/.task-mgmt/config.json
mkdir -p ~/.config/task-mgmt && cp person.example.json ~/.config/task-mgmt/person.json
$EDITOR ~/work/your-org/ops/.task-mgmt/config.json   # your owner, repos and boards
$EDITOR ~/.config/task-mgmt/person.json              # you, your agents, and only the hubs you've created
./provision.py                  # rehearse: what exists, what would be created
./provision.py --live           # create the repos (the hub folder becomes the ops repo) and the boards
$EDITOR ~/work/your-org/ops/.task-mgmt/config.json   # add each new board's "number", as the report says
./provision.py --live           # now set each repo's workflow variables
./provision.py config           # write ~/.config/board/boards.json from the hubs
./verify.sh                     # confirm the wiring, and that GitHub matches the hubs
```

At the end, every owner your hubs describe has its repos (with the task-mgmt layout committed), its boards (copied from the templates, linked to their repos, with their Themes), and its boards in `~/.config/board/boards.json`. `/design-loop`, `board` and the `item`, `pickup`, `board-setup` and `preflight` skills work in every repo.

What ships in this repo:

- **[`setup.sh`](setup.sh)** — config-driven deployer. Set your domains at the top; it stows the universal Layer 0 into `~/.claude/`, links each domain's root `CLAUDE.md`, and optionally aggregates skill overlays. Idempotent; backs up real files to `~/.claude-substrate-backup/` before replacing.
- **[`provision.py`](provision.py)** — creates what's missing on GitHub from the hub configs your person layer lists ([`hub.example.json`](hub.example.json), [`person.example.json`](person.example.json)), sets each repo's board workflow variables, and generates the `board` config (`provision.py config`). Rehearses by default; `--live` applies. Re-runnable. A single [`github.json`](github.example.json) still works in place of hubs.
- **[`template/board/`](template/board/)** — the `board` command (into `~/.local/bin`), its daily refresh timer, and the shipped board defaults that `provision.py config` starts from.
- **[`verify.sh`](verify.sh)** — post-setup checks (symlink integrity, domain-neutral Layer 0, per-domain roots, and, when a person layer or `github.json` exists, a `provision.py` rehearsal and a check that the board config matches the hubs).
- **[`template/`](template/)** — the scaffold `setup.sh` stows from: a universal `claude-user/.claude/` (with the design loop skill, its reviewer and verifier agents, and its compaction hook), example `work` and `personal` domain roots, and shell/git dotfiles (including directory-based git-identity routing). Copy it into your own dotfiles repo, or run in place.
- **[`brief.html`](brief.html)** — a one-page visual overview of the whole architecture and the four concerns it addresses. View it rendered at **[armodis-ai.github.io/task-mgmt/brief.html](https://armodis-ai.github.io/task-mgmt/brief.html)** (GitHub Pages), or open the file locally.

- **[`template/claude-restore/`](template/claude-restore/)** — `claude-restore` and `claude-provider` (into `~/.local/bin`): keep named Claude Code sessions alive across reboots in tmux, and move them between the Anthropic API and Amazon Bedrock. The MIT license covers `template/claude-restore/` ([`LICENSE`](template/claude-restore/.local/share/claude-restore/LICENSE)); the rest of the repo is CC BY 4.0 ([`LICENSE`](LICENSE)). See its [README](template/claude-restore/.local/share/claude-restore/README.md).
- **[`AGENTS.md`](AGENTS.md)**, **[`STATUS.md`](STATUS.md)**, **[`docs/decisions/`](docs/decisions/)** — conventions for agents working on this repo, the handoff note they read first and update, and a home for decision records.

### Install a pinned release

Releases are git tags `vX.Y.Z`. To install one instead of a checkout:

```bash
tag=v0.2.0
sha=$(git ls-remote https://github.com/armodis-ai/task-mgmt "refs/tags/$tag" "refs/tags/$tag^{}" | awk -v p="refs/tags/$tag^{}" '$2==p{x=$1}{a=$1}END{print x?x:a}')
[ -n "$sha" ] || { echo "tag $tag not found" >&2; exit 1; }
dir=~/.local/share/task-mgmt/$tag
mkdir -p "$dir" && curl -fsSL "https://github.com/armodis-ai/task-mgmt/archive/$sha.tar.gz" | tar -xz --strip-components=1 -C "$dir"
printf 'repo=armodis-ai/task-mgmt\nversion=%s\nsha=%s\n' "$tag" "$sha" > "$dir/.task-mgmt-release"
cd "$dir" && ./setup.sh && ./verify.sh
```

`setup.sh` and `verify.sh` work from the extracted folder (no `.git` needed), and `verify.sh` prints the release from `.task-mgmt-release`. A change reaches an installation only when its pin moves: install the newer tag and re-run its `setup.sh`. Board workflows pin the `BOARD_REF` variable to that release's commit SHA.

Requires [GNU Stow](https://www.gnu.org/software/stow/) and [Claude Code](https://code.claude.com/docs/en/overview). The rest of this document explains *why* the pieces are shaped the way they are — read on for the mental model, then tailor the template to your own domains.

***

## Setting up GitHub

The board is the shared-state plane for the [multi-agent workflow](#part-3-multi-agent-workflow-via-github) — where independent agent sessions claim work and stay coordinated. Decide the shape first with [Organization, board, or repo?](#organization-board-or-repo): one organization per business, one board per product plus a company board, one repo per product.

**Configuration lives in three layers:**

| Layer | File | Holds |
|---|---|---|
| Hub | `<hub>/.task-mgmt/config.json` in one repo per owner (its `ops` repo) | The owner's repos and boards: each board's number, template, repos, hierarchy and Themes, and `"automation": false` on repos without the board workflow |
| Person | `~/.config/task-mgmt/person.json` | Who operates (`operator`), which agent families work (`agents`), the hub folders to read (`hubs`), and overrides of the shipped defaults (`defaults`) |
| Release | `template/board/.config/board/boards.example.json` | The shipped defaults: required fields, effort levels, fixture rules |

`provision.py config` merges them into `~/.config/board/boards.json`, the file `board` reads, without calling GitHub; `config --check` reports any difference. Edit a hub, not the generated file: commit the change in the hub repo, then run `provision.py --live` (for the repos' variables) and `provision.py config` on each machine.

For each owner in the hubs, `provision.py`:

1. **Checks the organization exists.** GitHub has no API to create one, so the report links the page where you create it ([github.com/account/organizations/new](https://github.com/account/organizations/new)); run it again afterwards.
2. **Creates each missing repo**, private unless `"public": true`, and pushes the [File Conventions](#file-conventions) layout from a local clone at the repo's `path` (default `~/<owner>/<repo>`; the folder must be empty, or hold only the hub's `.task-mgmt/`, which is committed with the layout): README, AGENTS.md, STATUS.md, `design/`, `docs/decisions/` and `.gitignore`, the board workflow, plus `backend/`, `frontend/`, `scripts/` and `.env.example` for `"kind": "product"`. It adds the `test-fixture` label.
3. **Copies each missing board** from its template, links the board's repos, adds its Themes (keeping existing options and their ids), and adds the Agent and Responder fields with your agents. A new board has no `number` in the hub yet: the report names it, you add it (and commit the hub), and the next run sets the variables that depend on it. `provision.py config` refuses a hub board without one.
4. **Checks the built-in workflows.** GitHub has no API to enable them, and a copy doesn't carry "Auto-add to project", so the report lists what's off with a link to that board's Workflows page. Set them as in step 4 of the checklist below, then run it again.
5. **Sets each repo's board automation variables:** `BOARD_CONFIG` (the defaults plus the boards that list the repo) and `BOARD_REF` (the commit SHA of the hub's `version` tag), compared in a rehearsal, set and read back with `--live`, and left alone where they're set at organization level. It checks for a token (a GitHub App's `BOARD_APP_ID` variable and `BOARD_APP_KEY` secret, or a `BOARD_TOKEN` secret) and reports one that's missing; the token is yours to create and add. Without a token the workflow says so and skips, which matters only for issues that several pull requests close and for repos that release by tag; a repo that needs neither is marked `"automation": false` and isn't checked.
6. **Checks the `board` config** matches what `provision.py config` would write.

It finds what exists by name, creates only what's missing, and exits 0 once everything matches the hubs, or 2 while steps remain. Read-only boards (`"read_only": true`, for an owner whose board no repo feeds yet) get no built-in workflow checks and no Agent or Responder fields.

**The test fixture.** `board`'s live test runs against standing `test-fixture` issues: one Epic, one User Story under it and at least two Tasks. Keep them in a `sandbox` repo with its own Sandbox board for each owner type you use (one organization, one user account), so the real boards and hub issue lists stay clean: list the repo (`"automation": false`) and the board in that owner's hub, and provision creates both.

**The templates** it copies from are public GitHub [Projects templates](https://docs.github.com/en/issues/planning-and-tracking-with-projects/managing-your-project/managing-project-templates-in-your-organization) with the fields and lifecycle this guide describes. You can also open one and choose **Copy**:

- **[[TEMPLATE] Strategic Portfolio](https://github.com/orgs/armodis-ai/projects/6)** — the company board: Objective down to User Story, with company Themes.
- **[[TEMPLATE] Product Roadmap](https://github.com/orgs/armodis-ai/projects/9)** — one product's board: Milestone, Epic and User Story levels, with the product's own Themes.
- **[[TEMPLATE] Personal Task Mgmt](https://github.com/orgs/armodis-ai/projects/7)** — the personal-domain analog.

**What a board needs, by hand or to check one.** `provision.py` and the [`board-setup`](template/claude-user/.claude/skills/board-setup/SKILL.md) skill set these; this is the list they work from:

1. **Create a Projects (v2) board** for the domain, spanning its repos, or one per product once a business has several (see [Organization, board, or repo?](#organization-board-or-repo)).
2. **Add the fields the policy reads:** `Status` (single-select: Todo · Backlog · In Progress · In Review · Done, plus Pending Release where repos release by tag), `Priority` (P0–P3), `Effort` (1, 2, 3, 5, 8: the amount of work), `Complexity` (Trivial · Low · Medium · Medium-High · High: how hard it is), and `Theme` (your product/platform pillars — you define the set). Add `Category` if you track a hierarchy (Epic / Story / Task). See [Recommended custom field schema](#recommended-custom-field-schema).
3. **Define function labels** (e.g. `area:pipeline`) on the repos whose issues the agents pick up, so the queue is filterable.
4. **Turn on the built-in workflows** (board menu → Workflows; the API can't enable them): Item closed → Done, Item reopened → In Progress, Pull request linked to issue → In Review, Pull request merged → Done, Auto-close issue, Item added to project (issues only) → Backlog, Auto-add sub-issues to project, and Auto-add to project (one per repo on paid plans; the Free plan allows one per board, so add other repos' issues yourself). "Item added to project" can overwrite a Status set at filing, so read Status back after adding an issue that should be Todo. Boards whose repos release by tag also need a release automation: see [Statuses, readiness and required fields](#statuses-readiness-and-required-fields).
5. **Add the repo automation** to each repo that feeds the board: copy [`template/repo/.github/workflows/board.yml`](template/repo/.github/workflows/board.yml), then in the repo's (or organization's) Settings > Secrets and variables > Actions add a token, a `BOARD_CONFIG` variable (the board config JSON), and a `BOARD_REF` variable holding the task-mgmt commit SHA to run the board command from (`provision.py --live` sets both variables). The workflow runs that command with the board token, so pin it and bump it when you take a new task-mgmt release; unpinned, it runs task-mgmt's `main` and warns. For an organization board, the token is a GitHub App installed on the organization and the repos that feed the board, with organization Projects read and write and repository Issues, Pull requests and Contents read: its id as the `BOARD_APP_ID` variable and its private key as the `BOARD_APP_KEY` secret, and the workflow mints a short-lived token each run. For a user board, which Apps can't reach, it's a personal access token with the `repo` and `project` scopes as the `BOARD_TOKEN` secret. A repo whose issues each have one pull request, and that doesn't release by tag, can skip this.
6. **Adopt the working rules** from [Part 3](#part-3-multi-agent-workflow-via-github): read `STATUS.md` first, claim by flipping `Status → In Progress` and assigning yourself, select by `Priority, Effort, Created`, implement in a [git worktree](https://git-scm.com/docs/git-worktree), escalate irreversible/outward-facing actions to a human.

The visual [brief.html](brief.html) "Portfolio Mgmt" panel is a one-screen version of this. Once one board is configured to your liking you can [save it as an org Projects template](https://docs.github.com/en/issues/planning-and-tracking-with-projects/managing-your-project/managing-project-templates-in-your-organization) and point a hub board's `template` at it.

***

## Optional add-on: watch your agents from your phone (tmux-rc)

Once you're running several agents at once, you'll want to see them without sitting at the terminal. **[tmux-rc](https://github.com/armodis/tmux-rc)** (by [Shapor Naghibzadeh](https://github.com/shapor)) is a small local daemon that reads a `tmux` pane, classifies what each agent is doing, and serves a **phone dashboard** — status at a glance, alerts when an agent is blocked on a question, and tap-to-answer straight back into the pane. Unlike Claude Code's built-in `/remote-control`, it observes the *terminal*, so it's vendor-agnostic: any agent (Claude Code, Codex, Gemini CLI, …), any model provider for the summarization pass.

It's **independent of the substrate above** — a separate forkable project, not a dependency. Fork it, then follow its README to run the daemon or install the `systemd --user` units. Needs `tmux`, Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and Google Vertex credentials for the classification pass.

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

Two facts do most of the work in task-mgmt:

1. **Local Claude Code resolves config from the directory tree** — but the three resolution mechanisms behave differently (see Config Resolution below). CLAUDE.md merges up the whole tree; slash commands stop at the first repo boundary; memory is keyed to the exact launch directory. The practical upshot: **launch from inside the repo you're working on.**
2. **Web Claude Code only sees the single repo you clone.** Anything you want available in a web session has to be in that repo's `.claude/`. Team skills committed there come along; user-level operating skills in `~/.claude/skills/` don't, so a repo that needs them in the cloud carries a copy (see [Stow Operations](#stow-operations)).

## Config Resolution

Three mechanisms resolve config, and they do **not** all walk the tree the same way. The differences determine where you launch `claude` and where you put skills.

| Mechanism | What it loads | Walk behavior |
|-----------|---------------|---------------|
| **Instruction files** (`CLAUDE.md`, `AGENTS.md`) | Every `CLAUDE.md` from cwd up to `~`, plus `~/.claude/CLAUDE.md`; with the setting below, every `AGENTS.md` on the same walk | **Merges all.** Walks up through every ancestor; closer wins on conflicts. |
| **User-level skills** (`~/.claude/skills/`, `~/.claude/agents/`) | Every skill and subagent installed for the user | **No walk.** Loaded in every local session, whatever folder it started in. |
| **Slash commands** (`.claude/commands/`, `.claude/skills/`) | Commands and skills from a `.claude/` reachable from cwd | **Stops at the first project boundary.** A directory containing `CLAUDE.md` or `.git` is treated as a project root; the walk does not cross above it. |
| **Auto-memory** (`~/.claude/projects/<encoded-cwd>/memory/`) | One directory, keyed by the exact launch cwd | **No walk.** Each cwd has its own memory bucket; subdirectories don't inherit a parent's memory. |

The load-bearing consequence: **a repo is a project boundary** (it has both `CLAUDE.md` and `.git`). Skills defined *above* a repo — e.g., in `~/work/.claude/` — will **not** be found when you launch `claude` from inside `~/work/some-repo/`. So skills go in one of two places: **user level** (`~/.claude/skills/`) for operating skills that work in every repo, such as the design loop and the board skills, and **the repo root's `.claude/`** for a team's own skills, which web Claude Code (cloning a single repo) also picks up.

CLAUDE.md, by contrast, composes exactly as you'd hope. A session in `~/work/some-repo/` loads, merged:

1. `~/work/some-repo/CLAUDE.md` — repo context
2. `~/work/CLAUDE.md` — **domain layer** (note: a root `CLAUDE.md`, not `~/work/.claude/CLAUDE.md` — see below)
3. `~/.claude/CLAUDE.md` — **universal layer** (formatting, communication style, working habits)

**Domain-level CLAUDE.md goes at the domain root** (`~/work/CLAUDE.md`), not inside a `.claude/` subdir. The walk reliably picks up a root `CLAUDE.md` at each ancestor level; a `~/work/.claude/CLAUDE.md` does not load the same way. (Only `~/.claude/CLAUDE.md` — the universal user-level file — is special.)

**AGENTS.md at the repo root, and the setting this architecture requires.** The repo-level instruction file should be `AGENTS.md`, the cross-vendor name Codex and other coding agents also read; Claude Code reads it too (since 2.1.277). But by default Claude Code reads `AGENTS.md` only as a *fallback* — when no `CLAUDE.md` (or `.claude/CLAUDE.md`, or `CLAUDE.local.md`) exists in the working directory **or any directory above it**. A domain-root `CLAUDE.md` is exactly such a file, so on a machine set up per this guide every repo's `AGENTS.md` is silently ignored unless you change one setting. Set **Project instructions** to `claude-md-and-agents-md` (`/config`, or in `~/.claude/settings.json`):

```json
{ "pluginConfigs": { "agents-md@builtin": { "options": { "instructionFiles": "claude-md-and-agents-md" } } } }
```

Then both files load on the walk, each directory's `CLAUDE.md` first and its `AGENTS.md` after. The template `settings.json` ships this, and `verify.sh` checks for it. The universal and domain layers stay `CLAUDE.md`: they are Claude Code concepts — Codex's global file is `~/.codex/AGENTS.md`, and it never reads above the repository root — so renaming them buys nothing. A relative `@AGENTS.md` import in a parent `CLAUDE.md` resolves against that file's own directory, not the repo, so it cannot stand in for the setting.

Memory follows the launch cwd. Launch from `~/work/some-repo/` and memory comes from the bucket keyed to that path; launch from `~/work/` and it's a different bucket. Pick one launch point per context and stay consistent, or you'll scatter memory across buckets.

## Scoping Strategy

The architecture in task-mgmt assumes you have **distinct domains** that should not bleed into each other. The most common shape:

- **Work** — your day job, where you spend most professional time
- **Personal** — everything else, often subdivided

You may have more (multiple clients, multiple businesses, family vs. household vs. building projects). The mechanism is the same regardless of count.

The hardest part isn't technical — it's discipline:

- Always start a chat in the right Project (claude.ai)
- Always `cd` into the right domain (Claude Code)

The system can't enforce that. But it can make the right thing easy: per-domain shortcut aliases (`cwork`, `cpersonal`), domain-rooted Project boards, and visible cues in your shell prompt all reduce the friction of being in the right place.

## The Three-Layer Pattern

Universal → Domain → Repo. Each layer adds specificity — but remember from Config Resolution that the layers compose cleanly for **instruction files** (with the `claude-md-and-agents-md` setting) while **skills resolve from user level and the repo root only**.

**Universal layer (`~/.claude/`)** — applies everywhere. Things true regardless of context:

- Output style (file references, markdown formatting, lists vs prose)
- Communication preferences (terse vs verbose, when to confirm, when to act)
- Working habits (commit conventions, test-first preferences, etc.)

**Domain layer (`~/<domain>/CLAUDE.md`)** — a root `CLAUDE.md` at the domain dir, applies inside one domain:

- Domain-specific conventions, tone, and vocabulary (e.g., a different register for personal vs work)
- A map of the domain's repos

(Domain-level **skills** don't resolve via the walk — the repo boundary blocks them. A skill every repo needs goes at user level; a skill one domain's repos share goes in that domain's hub repo, or in a domain-root `.claude/` aggregation used from the domain root as a deliberate convenience — see below.)

**Repo layer (`<repo>/.claude/` + `<repo>/AGENTS.md`)** — applies to one repo, and is where skills actually live:

- Team skills (`.claude/skills/` or `.claude/commands/`) and subagents (`.claude/agents/`) — committed in the repo, standard Claude Code layout, found when you launch from inside the repo
- Repo context in `AGENTS.md` — the cross-vendor file; a `CLAUDE.md` still works for Claude alone, but `AGENTS.md` is what Codex and the others read too

The rule of thumb for instruction files: **put a setting at the highest layer where it's still true.** Skills follow the same rule with two places to choose from: user level for skills that are the same in every repo, and the repo for skills about that repo's work. Skills that span a team's repos live in the repo you launch from to do that cross-repo work (a planning/hub repo), referencing siblings by relative path (`../other-repo/...`).

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
├── work/                                     ← your businesses, or your day job
│   ├── CLAUDE.md                            ← work domain layer (root file, not .claude/)
│   ├── .claude/                             ← OPTIONAL: aggregated skills for domain-root launches
│   ├── <org>/                               ← one folder per GitHub organization
│   │   ├── AGENTS.md                        ← that organization's rules, read beneath the domain layer
│   │   ├── <product>/                       ← one repo per product, a monorepo (see File Conventions)
│   │   └── ops/                             ← company-wide tooling and planning
│   └── <other-org>/
│
└── personal/                                 ← everything else
    ├── CLAUDE.md                            ← personal domain layer (root file, not .claude/)
    ├── dotfiles/                            ← your dotfiles repo (stow source for ~/ + domain CLAUDE.md backups)
    ├── <hub-repo>/                          ← a personal planning repo, if you keep one (its own skills at its .claude/)
    ├── <domain1>/                           ← personal subdomain repos
    ├── <domain2>/
    └── ...
```

Adapt names to your preferences. The load-bearing shape: universal config at `~/`, a root `CLAUDE.md` at each domain dir, an `AGENTS.md` at each repo root, **operating skills at user level** (`~/.claude/skills/`, stowed, so every session sees them), and **team skills committed at each repo's own `.claude/`**. The domain `.claude/` aggregation is an optional convenience for cross-repo launches.

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
- **Stow operating skills at user level; commit team skills in their repo.** Skills that run the operating model (the design loop, board operations) are generic, so they're stowed into `~/.claude/skills/`, which every session loads whatever folder it started in. Skills for one team or repo live in that repo's `.claude/` and are committed there, where teammates get them on clone. Keep skills out of domain-level `.claude/` folders and out of stow wrappers around a repo's `.claude/`: a session started inside a repo doesn't see the domain level, so skills there silently go missing.
- **Cloud sessions** (claude.ai/code) see only the cloned repo, not `~/.claude/`. A repo that needs an operating skill there carries a copy: copy (or vendor as a git submodule and symlink) the skill's folder into `.claude/skills/<name>/` and its agents into `.claude/agents/`, and commit them. The design loop's compaction hook and its token-cost report read local session transcripts, so they work only in local sessions.

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
| Per-repo agent context | `<repo>/AGENTS.md` (lives in the repo; read by Claude Code with the `claude-md-and-agents-md` setting, and by Codex) | No |
| GitHub notification routing | GitHub Settings UI (manual) | N/A |

**The routing rule:** anything in `dotfiles/` requires commit + push to sync across machines. Anything outside dotfiles is scoped to where it lives.

***

# Part 3: Multi-Agent Workflow via GitHub

This is the operating model that the architecture in Parts 1–2 enables. **GitHub is the shared substrate.** Different Claude surfaces play different roles, hand off through commits, and use the same source of truth per domain.

## The Model

Four roles, four surfaces, one substrate per domain:

| Role | Best for thinking/design | Best for execution | Outputs |
|------|--------------------------|--------------------|---------|
| **Planner** | claude.ai chat or Project | (outputs are documents) | Markdown files in a design run's folder, `design/<YYYY-MM-DD-slug>/` |
| **Coordinator** | claude.ai chat or Project | Local Claude Code (`gh` + GraphQL — chat can't write to GitHub today) | GitHub Issues + Project board state |
| **Implementer** | Local Claude Code | Local Claude Code | Commits, PRs, file changes |
| **Autonomous Worker** | Web Claude Code | Web Claude Code | Branches, PRs, status updates on cloud-hosted sessions |

The Planner and Coordinator can do their *thinking* in claude.ai — analysis, drafting issue text, designing hierarchy. But every **write** to GitHub today happens through Claude Code, because claude.ai's GitHub connector is read-only and the chat surface can't reach `api.github.com` from its code execution sandbox. The handoff is: chat produces the design; local Claude Code executes the writes via `gh` CLI and GraphQL mutations. See [claude.ai's GitHub connector: read-only today](#claudeais-github-connector-read-only-today) in Part 5 for details and workarounds.

Roles aren't tied to specific Claude instances — any agent can take on any role. The naming captures *intent* so you know which surface fits which task.

## File Conventions

Every repo (across every domain) follows the same layout for non-code artifacts:

```
<repo>/
├── README.md                # Orientation: what this repo is, layout, doc pointers (humans first)
├── AGENTS.md                # Agent behavior conventions for this repo (cross-vendor name)
├── STATUS.md                # Handoff: what just happened + what's next + where to find things
├── design/
│   └── <YYYY-MM-DD-slug>/   # One folder per design-loop run
│       ├── framing.md       # Goal, requirements, done when, out of scope, assumptions
│       ├── facts.md         # Questions settled by checks, each with its evidence
│       ├── decisions.md     # Judgment calls: options, recommendation, the operator's ruling
│       ├── contract.md      # What gets built, and the acceptance tests
│       ├── cost.md          # Tokens the run spent (cost-log.tsv holds the step marks)
│       ├── evidence/        # Logs, probe output and reviews that the records cite
│       └── scratch/         # Working files, gitignored (design/*/scratch/)
├── docs/                    # Durable docs for readers: how-to, reference, explanation
│   ├── decisions/           # ADRs: <NNNN-title>.md, append-only
│   └── runbooks/            # Operational procedures, when the repo has any
└── (code / data / whatever)
```

A design run's folder is its whole record: the [design loop](#the-design-loop) writes it, and a later session reads it to see what was decided and why. Work small enough to skip the loop needs no folder.

**A product repo is a monorepo.** One repo holds every part of one product, so a change across parts lands as one pull request:

```
<product>/
├── README.md, AGENTS.md, STATUS.md
├── design/                  # design-loop runs, as above
├── docs/                    # reader docs and ADRs, as above
├── backend/                 # server, API and data model, with its tests
├── frontend/                # web app, with its tests
├── scripts/                 # developer and operations scripts
├── docker-compose.yml       # the local stack, when there is one
└── .env.example             # the settings the app reads; the real .env stays out of git
```

Tests sit beside the code they test. Split a part into its own repo only when several products share it or it ships on its own schedule ([Organization, board, or repo?](#organization-board-or-repo)).

**Superseded records move, they don't stay.** A record that a later version replaces (a reader doc rewritten, an ADR's draft once the final lands) moves to a sibling `archive/` directory in the same commit that lands its replacement, and its first lines point forward to what replaced it. A status line reading "SUPERSEDED" is not enough: a fresh session reading the directory cannot tell which file is current and will read both (observed 2026-10-09: a cold-start test session read a superseded Direction beside its replacement and carried one stale clause into an otherwise correct answer). The current version keeps the plain name; nothing else in the repo should link into `archive/` except the replacement's own "written from" line.

A decision ledger is the exception: a later ruling is added under the earlier one as a dated revisit, so the ledger keeps the history and still reads as current.

**Scratch is not a record.** Anything a session writes while working (probe raw output, agent briefs, intermediate JSON) goes under a gitignored scratch root (`design/<run>/scratch/` inside a design run, `.scratch/<run-name>/` otherwise, or the harness's scratchpad), never under `docs/`. Findings worth keeping are promoted into the run's `facts.md` or `evidence/` by their author; everything else is regenerable and stays unversioned.

### Three-role doc separation

| Doc | Audience | What it answers | Volatility |
|---|---|---|---|
| **README.md** | Humans landing on the repo (GitHub web, fresh clone, future-you) | What is this? Who is it for? Where do the other docs live? | Low — stable framing |
| **AGENTS.md** | Coding agents in this repo (Claude Code, Codex, …) | How should agents behave here? What conventions apply? | Low/medium — stable instructions |
| **STATUS.md** | Next session / next agent | Where are we right now? What handoff signals? What's next? | High — updated every session |

They cover orthogonal concerns: orientation (README), behavior (AGENTS), state (STATUS). Don't conflate them — when STATUS keeps growing past a screen, the parts that aren't volatile probably belong in README.

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
 Format, as `board claim` writes it: `- [owner/repo#N](issue URL) <title> — claimed YYYY-MM-DD by <agent> (session <id>)`)

## What's next
(1–3 concrete next actions. Annotate each issue with `(P_, E_)` from the
 board for quick human scanning — matches the agent selection policy.)

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

For a leaf repo (work happens here but no ongoing build queue — a domain repo, such as one for household admin): drop the Functions section, keep mission + layout + see-also.

The function model: ask "what am I building that leverages the substrate?" Not "what work happens here." Outputs (reports, board state, planning artifacts) are downstream consumption — they don't track as functions of the repo.

## GitHub Projects as Task Substrate

A GitHub Project (v2) with custom fields turns the issue tracker into a planning system. Status + Priority + Type + Category + Theme + Effort + Complexity + dates give you enough dimensionality to plan real work: who's doing what, when, in what category, at what priority. The board's views (Kanban for daily, Table for bulk edits, Roadmap for timeline) are different slices of the same data.

### Recommended custom field schema

| Field | Type | Suggested values | Purpose |
|-------|------|------------------|---------|
| **Status** | Single-select | Todo, Backlog, In Progress, In Review, Done (plus Pending Release where repos release by tag) | Workflow state and readiness |
| **Priority** | Single-select | P0, P1, P2, P3 | Urgency. P0 = today, P3 = backlog |
| **Type** | GitHub built-in issue type | Bug, Feature, Task | What kind of work |
| **Category** | Single-select | Epic, User Story | Planning hierarchy level (parent items only — leaves use Type=Task and leave Category empty) |
| **Theme** | Single-select | (Your taxonomy — see below) | Horizontal categorization |
| **Effort** | Number | 1, 2, 3, 5, 8 | Amount of work; orders the queue |
| **Complexity** | Single-select | Trivial, Low, Medium, Medium-High, High | How hard the work is; guides which model takes it (harder work to the more capable model) |
| **Start / End** | Date | YYYY-MM-DD | Optional scheduling |

**Theme** is the horizontal cut across your hierarchical structure. For work, it's typically product areas (Auth, Billing, Search, etc.). For personal, life domains (Family, Household, Legal, Health, Finance, etc.).

### Statuses, readiness and required fields

Status carries readiness, so a Kanban view works unchanged:

- **Backlog:** not ready. An open decision, missing detail, or not yet prioritised. Agents never execute Backlog items; they may refine one up to its open decision.
- **Todo:** ready. Required fields are set, what done looks like is stated, and no decision is open.
- **In Progress:** claimed. The claim assigns the issue to the login the claimant works under.
- **In Review:** a pull request that closes the issue is open.
- **Pending Release:** merged on a board whose repos release by tag, waiting for the release.
- **Done:** finished, or closed as not planned or duplicate.

Work only a person can do is assigned to that person while it's still in Todo or Backlog; blocked work is marked with GitHub's "blocked by" relationship. Agents pick up Todo items that are unassigned and not blocked, and assign them at the claim.

**Required fields.** An agent files every issue with every field it can fill:

- **Every issue:** Status, Priority, Theme, Complexity, and Type (Task, Bug or Feature; parents are Feature).
- **By level:** Effort on Tasks and Stories; Category on parents; a parent link below the top level, except on levels a board lists in `parent_optional` (a personal board's standalone Tasks, for example).
- **By status:** an assignee from In Progress on; what done looks like before Todo.
- **Optional:** dates, and a Team field if you add one.

**Done and releases.** In a repo with no release process, a merged closing pull request means Done. On a board whose repos all release by tag, the issue still closes on merge, but that board's "Item closed" workflow sets Pending Release instead of Done; a release workflow moves released items to Done, and whoever closes an issue as not planned or duplicate sets it to Done. GitHub closes an issue when the *first* pull request that says `closes #N` merges, even while others that close it are open. The issue may stay closed; the board Status is what tracks the work. When several pull requests deliver one issue, each says `closes #N`, and `board guard` (run by the repo's board workflow on every merge) keeps the issue at In Review until the last one merges, then sets Done, or Pending Release on a tag-release board. In a repo without the workflow's token, say `refs #N` on all but the last. The workflow is [`template/repo/.github/workflows/board.yml`](template/repo/.github/workflows/board.yml); it needs a token that can write to Projects — a GitHub App for an organization board (the workflow mints its token each run), or a personal access token with the `repo` and `project` scopes for a user board — because the default `GITHUB_TOKEN` can't.

### The board command and skills

Agents read and change boards through one command, [`board`](template/board/.local/bin/board): Python standard library over `gh api graphql`, with each board's differences in `~/.config/board/boards.json` (owner, hierarchy, statuses, the repos that feed it, whether they release by tag, read-only). `provision.py config` generates it from the hub configs and the shipped defaults in [`boards.example.json`](template/board/.config/board/boards.example.json) (see [Setting up GitHub](#setting-up-github)).

- **Reads** work from a snapshot of each board in `~/.local/state/board`: `snapshot`, `tree`, `select`, `hygiene`. A snapshot older than a day is pulled again on read, and a daily timer (`board-refresh.timer`, enabled by `setup.sh`) keeps them fresh. `search` is a live title search. Inside a repo, `.` names the repo's board.
- **Writes** are JSON change plans: `check` prints the dry run, and `apply` writes the plan and reads back every write and every configured board. A plan that is hard to undo (close, reparent, change level or type, remove, edit options, cross owners, or touch many items) waits for `--approved`.
- **Rules** every plan is checked against:
  - the required fields at create, and again before Todo, along with a "Done when:" line;
  - no upside-down parent links;
  - no mentions of another owner's issues in text it writes, since `relate` and `block` link across owners without writing into their timelines;
  - promotion and demotion change the issue type with the level.
- **Claims:** `claim` refuses an item that isn't open at Todo or that someone else holds, then sets In Progress, assigns you, and adds the STATUS.md line; `finish` sets Done (Pending Release on a tag-release board) and removes it.
- **Hygiene** reports:
  - missing required fields;
  - stale claims;
  - orphans and level problems;
  - Status that disagrees with the issue's state;
  - linked pull requests that disagree with In Review;
  - issues closed while a closing pull request is still open;
  - open pull requests that close no issue and aren't on the board.
- **Analysis notes:** `note` appends a finding to an item's record (kind, text, who, when, and the issue's `updatedAt` at the time); `notes` reads them back, marking any written before the issue last changed. A refresh keeps them.
- **Pull requests and releases:**
  - `add_pr` puts a pull request that closes no issue on the board at In Review.
  - [`template/repo/.github/workflows/board.yml`](template/repo/.github/workflows/board.yml) runs `board guard` when a pull request merges: an issue that another open pull request also closes goes back to In Review (it stays closed), and goes to Done or Pending Release when the last one merges.
  - On a tag-release repo, the same workflow runs `board release` when a release is published, which moves released items from Pending Release to Done.
- **Tests:** `python3 -m unittest discover -s tests/board` runs the offline suite against a made-up config; [`tests/board/live_fixture.py`](tests/board/live_fixture.py) runs the commands against a real board's labelled test fixture.

Three skills run the common tasks on top of it: [`item`](template/claude-user/.claude/skills/item/SKILL.md) files, grooms, links, claims and closes issues with the required fields; [`pickup`](template/claude-user/.claude/skills/pickup/SKILL.md) selects the next ready item and claims it; [`board-setup`](template/claude-user/.claude/skills/board-setup/SKILL.md) sets a board up to this schema. Before a build or a scheduled run, [`preflight`](template/claude-user/.claude/skills/preflight/SKILL.md) checks that every checkout the run touches is clean and current and that the tools it needs are signed in, so the run fails at the start rather than halfway.

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

When a PR closes an issue, use `closes #N`, `fixes #N`, or `resolves #N` in the body. GitHub populates `closingIssuesReferences` and, with the board's built-in workflows on, the Status field moves on PR merge. Plain `#N` mentions are informational — no automation.

### Organization, board, or repo?

Three containers, three questions. Decide them in this order. This section covers work in organizations you own; for whether a repo belongs in your user account, your own organization or someone else's, see [GitHub Home Strategy](#github-home-strategy).

| Container | Use a separate one for | Signal it's time |
|---|---|---|
| **Organization** | Each business, or anything that may change hands | A distinct legal entity; a product you may sell or spin off; outside collaborators, investors or customers who need their own access; regulated data (health, financial) that calls for its own access controls and audit |
| **Project board** | Each product, plus one for company-wide work | Its own roadmap, priorities and Themes. Two products that share nothing would mix unrelated Themes in one dropdown |
| **Repo** | Each product, as one repo (a monorepo for that product) | Split a piece out only when several products share it, or it ships on its own schedule |

**Boards.** A business with one product can run on one board. Once it has two products, give each product its own board and keep a company board for what spans them, such as operations tooling and strategy. Agents file each issue on the board of the product it belongs to, and company-wide work on the company board. A company-level parent item can parent a product Epic: sub-issue links are between issues, whichever board each sits on. With the "Auto-add sub-issues to project" workflow on, linking a product Epic under a company item pulls the Epic's whole subtree onto the company board too, and unlinking later leaves the pulled items in place. Decide which board holds the detail before you link; to keep it on the product board alone, turn that workflow off on the company board. For personal domains, start with **one shared board** and spin off a domain board when the shared one feels cluttered.

**Repos: monorepo or many repos.** A monorepo keeps all of a product's code in one repository: backend, frontend, docs and tests. A change across parts lands as one pull request, issues and history live in one place, and agents find everything from one checkout. Its costs show at scale: the repo grows large, access is all or nothing, and builds eventually need tooling to test only what changed. Many repos give each part separate ownership, access and release schedules, at the cost of coordinating changes across repos and keeping versions in step. For a small team where agents do much of the work, one repo per product is the default.

**Moving later.** GitHub transfers repos between organizations with their history, issues and pull requests; issue types carry over only where the new organization has a matching type. Project boards can't change owner, and item field values (Status, Priority, Theme, Effort) live on the board: export them, copy the board to the new owner, add the items again and re-enter the values. So if a sale or spin-off is already likely, start the product in its own organization. Otherwise start it inside its business's organization: the repo moves cleanly later, and the board is rebuilt.

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

**API note — editing single-select options.** There is no `updateProjectV2SingleSelectField` mutation (a natural guess that fails with "Field doesn't exist on type Mutation"). The real mutation is **`updateProjectV2Field`** with a `singleSelectOptions` argument — and it *replaces* the full option list, so include each option you want to keep, with its `id`. An option sent without its `id` is recreated, and items set to it are cleared. Also: the `singleSelectOptions` array can't be passed via `gh api graphql -F` (it stringifies); pass the whole query+variables as a JSON body with `gh api graphql --input <file>`. To *add* fields, use `createProjectV2Field`; to flip the template flag, `markProjectV2AsTemplate`. All work identically on templates (they're regular ProjectV2 objects with a boolean flag).

**Auth note:** GitHub Apps (installation tokens) can't access user-level Projects v2 — a documented GitHub limitation. PATs and OAuth tokens (e.g., the token from `gh auth login`) work fine. For agent-driven flows using `gh api graphql`, this is a non-issue. For flows using a Claude GitHub App installation token, you'll need to either keep the project at the org level or use a different auth path.

The copy inherits fields, views, and field options. Items don't copy — the new board starts empty. After copying, adjust field options to fit the new context:

- Use `updateProjectV2Field` (with `singleSelectOptions`) to change Theme options to the new vocabulary
- Use the same mutation to simplify Status (drop values you don't need) — remember it replaces the full list
- Leave Priority, Type, Effort, Start/End as-is
- Turn on the "Auto-add to project" workflow in the web UI (board menu → Workflows), then set its repository and filter. Copies don't carry it, and the API can read and delete workflows but not create or enable them. Each auto-add workflow covers one repository; the Free plan allows one per board (Pro and Team five, Enterprise twenty), and it adds only new or updated items, so add other repos' issues and existing ones yourself

This pattern saves significant manual configuration and ensures consistency across boards.

## Concurrency & Claiming

Multiple agents reading the same backlog (parallel local sessions, autonomous workers, scheduled jobs, agents in other harnesses) need a way to avoid picking up the same work. The architecture uses a **two-layer claim**: the board's Status and Agent fields, and the repo's STATUS.md.

**Layer 1 — Lock signal (board Status):**

The agent's first action when starting work on an issue is `board claim`, which flips the board Status from `Todo` → `In Progress` and sets the **Agent** field to the claiming agent. Other agents read Status and Agent before claiming and skip anything not in `Todo` or held by another agent. This is the queryable, board-visible lock. Agent stands in for the assignee because every agent can act as one GitHub account: the assignee names the account, and Agent names which agent holds the work.

**Layer 2 — Traceability (STATUS.md):**

The session adds the issue to its repo's `STATUS.md` under a "What's in progress" section, then commits the update with the `status:` prefix. Other sessions `git pull` and read STATUS.md (the first-read convention) and see what's claimed in human-readable form.

```markdown
## What's in progress

- [acme/planning#176](https://github.com/acme/planning/issues/176) Audit-Reconcile — claimed 2026-05-28 by claude (session 4f2a…)
- [acme/planning#180](https://github.com/acme/planning/issues/180) PR-title citations — claimed 2026-05-28 by codex
```

When the work lands (PR merged, issue closed), the session moves the entry from "What's in progress" to "What just happened" and commits.

**Claim flow:**

```
1. git pull (fresh STATUS.md)
2. Read STATUS.md "What's in progress" — see what other sessions are doing
3. Pick an issue from "What's next" (or planning's open queue)
4. Re-check the board Status — confirm still Todo
5. Flip Status → In Progress and assign the issue to yourself
6. Update STATUS.md "What's in progress" with the issue ref + session name
7. Commit STATUS.md ("status: claim #N for <work>"), push
8. Do the work
9. When done: remove from "In progress", add to "What just happened", commit, push
```

**Stale claims:** if an agent dies mid-task, Status stays at `In Progress` with no PR landing. The simplest recovery is a periodic board-hygiene pass (e.g., a `project-sync` skill) that surfaces stuck items and offers to revert them. Threshold is workload-dependent.

**Race window:** the gap between read and write is tiny and accepted. At handful-of-agents scale this is acceptable noise — the cost of strict locking (a distributed lock service, optimistic concurrency tokens) outweighs the cost of an occasional double-claim. Add stricter coordination only if it becomes a real problem.

### Working across agents and harnesses

Any number of agent sessions, from any harness or model provider, coordinate through the board, issues, pull requests and STATUS.md, with commands every harness can run. Nothing depends on one harness's own messaging.

**Identity.** The agents share one GitHub machine account, and the operator keeps their own. GitHub's terms allow one free machine account per person, and a paid account per agent family buys nothing an agent uses. Each harness's environment carries the agent's identity:

- `GH_CONFIG_DIR`: a `gh` login folder for the machine account, so the token stays out of committed settings;
- `GIT_AUTHOR_*` and `GIT_COMMITTER_*`: the machine account's name and noreply address;
- `BOARD_AGENT`, `BOARD_MODEL` and `BOARD_SESSION`: the names `board` signs with.

The operator's own terminal sets none of these, so it stays the operator.

**Two fields** on every board, created by `board setup-agents` (or `provision.py`) from two keys you add to the board config's `defaults`:

```json
"agents": ["claude", "codex"],
"operator": {"name": "Pat", "login": "your-github-login"}
```

Names are one word (letters, digits, `.`, `_`, `-`), because comment markers carry them.

| Field | Means | Set by | Cleared by |
|---|---|---|---|
| Agent | who owns the item | `claim`, `handoff` | kept as the record after `finish` |
| Responder | who is asked to review or answer | `ask` | `answer`, `finish` |

**The exchange.** Each step posts a signed comment carrying a marker (`<!-- board:ask from=claude to=codex kind=review -->`), which `board inbox` reads:

```
claude:  board claim . acme/app#12 --status-md STATUS.md
claude:  (opens a pull request that closes #12)
claude:  board ask . acme/app#12 codex review "Ready for review."
codex:   board inbox                  → acme/app#12  review from claude
codex:   board answer . acme/app#12 --verdict approve "Reads right; tests pass."
claude:  board inbox                  → acme/app#12  answer (approve) from codex
claude:  (merges) board finish . acme/app#12 --status-md STATUS.md
```

**Reviews between agents.** One account can't approve its own pull requests, so an agent's review is a comment review that opens with a verdict line (`**Verdict: approve**` or `**Verdict: changes requested**`). A pull request merges after another agent's approve verdict or the operator's approval. GitHub can't enforce that rule on a Free plan's private repos, so agents follow it by instruction. Agents ask the operator through GitHub's own review request, and the operator's comments reach the machine account's notifications, which the inbox shows.

**Waking an agent.** Agents run `board inbox` at session start and between tasks. `board inbox --agent <name> --json` gives a poller one entry per waiting marker, keyed by its comment, so a local dispatcher can start or nudge the agent named.

**The operator answers on GitHub itself**, in a review or a comment. The agent that asked runs `board ack`, which also clears Responder when it names the operator.

**Agent names** like `claude` or `codex` are often real GitHub users, so they are written in bold, not as @-mentions.

**What's not covered here:** file-level conflicts (two agents editing the same file) — out of scope for this design; git handles it via merge conflicts.

### Selecting work

Claiming is half the answer. The other half is "which item to claim." With **Priority** (P0/P1/P2/P3) and **Effort** (1/2/3/5/8) on the board, an agent can apply a deterministic selection policy without further input.

**Default sort:**

1. Filter: open issues with the relevant function label (e.g., `planning:pipeline`), `Status = Todo`, unassigned, not blocked, and not already in any session's STATUS.md "What's in progress." Backlog is never selected.
2. Sort: `Priority ASC` (P0 → P3), then `Effort ASC` (1 → 8 within priority), then `Created ASC`.
3. Agent takes the head.

Highest urgency first; within urgency, smallest size first. Naturally clears small high-priority items before graduating to bigger ones — fast wins, low context cost.

**Named modes** an operator can specify in the prompt (e.g., "work the planning queue, quick-wins mode"):

| Mode | Filter on top of default | Use case |
|---|---|---|
| *(default)* | none — head of sorted list | "What's next" — pick the top item |
| `quick-wins` | Priority ≤ P1 AND Effort ≤ 2 | Clear small high-priority work, multiple in one session |
| `focused-feature` | Priority ≤ P1 AND Effort ≥ 5 | Pick one big-ticket item, commit |
| `backlog-cleanup` | Effort ≤ 2 (any priority) | Burn down the small-item tail |

**Field-completeness precondition:**

The policy only works if the required fields are set ([Statuses, readiness and required fields](#statuses-readiness-and-required-fields)): Priority, Theme, Complexity and Type on everything, Effort on Tasks and Stories. Agents **skip with warning** any issue missing one — surface them in the session summary as "needs grooming" rather than picking them. This forces field discipline upstream, where it belongs. A board-hygiene rule (`board hygiene`) flags issues with missing fields.

Don't default-treat missing values (e.g., "missing → P2, E3") — it rewards leaving fields empty and corrodes the policy over time.

## The design loop

Complex work is easy to mis-frame, and the expensive mistakes are the ones made before any code. The design loop is a skill that runs that work in a fixed order, so the operator spends attention only on judgment calls and agents settle everything a check can answer. It ships in [`template/claude-user/.claude/skills/design-loop/`](template/claude-user/.claude/skills/design-loop/SKILL.md), and `setup.sh` installs it at user level, so `/design-loop` works in every repo.

0. **Frame** with the operator: goal, requirements, done when, out of scope, assumptions, and the assumption most likely to be wrong. The operator confirms.
1. **Thin rail and probes:** build the thinnest end-to-end slice against the real system. Two `design-triage` reviewers on different models read the run cold, sort every open question into fact or judgment, and settle the facts with checks.
2. **Direction gate:** the operator rules on the judgment calls. Full calls come with neutral options, evidence and a separate recommendation; small ones go with the recommendation unless the operator objects.
3. **More probes and tests:** each decision becomes a test where it can.
4. **Contract gate:** the operator approves the contract: scope, decisions and the acceptance tests with their commands.
5. **Build** to the tests. Reversible mid-build decisions are recorded and the build continues; irreversible or outward-facing ones come to the operator first.
6. **Verify:** a `design-verifier` agent runs every acceptance test itself and reports met, not met or unverifiable, with evidence.

Each run keeps its record in `design/<YYYY-MM-DD-slug>/` ([File Conventions](#file-conventions)), including the tokens it spent (`cost.md`, from the session transcripts). After a compaction, a `SessionStart` hook prints the active run's framing so the session stays on goal.

## Decision Review: Green/Blue Doc Escalation

Agents hit decision points the conventions route to a human — an ambiguous structural call, a low-confidence classification, a borderline judgment, conflicting inputs. The default is to **pause and ask the operator**: a synchronous human-in-the-loop (HITL) gate. That gate bottlenecks autonomous and parallel work — cloud workers and scheduled jobs stall on it, and the human arrives to a cold question they have to reconstruct context for.

Most of these are **reversible judgment calls** — the kind a competent engineer resolves in a short design discussion, not a safety-critical commitment. What's missing at the agent layer isn't *a human* — it's *structured deliberation*: an adversarial check and a recorded rationale. A single agent deciding unilaterally reproduces the failure mode the HITL gate guards against (one perspective, nothing written down).

**Convention: when an agent reaches a decision the conventions would route to a human, it convenes a bounded agent team that runs a two-gate design review, records the outcome, and proceeds — instead of blocking.** The human reviews the record asynchronously. The shape borrows from the Google engineering design-doc culture ([Design Docs at Google](https://www.industrialempathy.com/posts/design-docs-at-google/)), run as two color-coded gates:

| Gate | Doc | Frames | Reviewed for | On approval |
|------|-----|--------|--------------|-------------|
| 1 | **Green Doc** (strategy) | problem, goals, non-goals, ≥2 options + trade-offs, open questions | are we solving the right problem; is the direction sound | choose a path → advance to Blue |
| 2 | **Blue Doc** (blueprint) | the chosen path in execution detail: exact changes, sequencing, blast radius, rollback | correctness, scale, safety — can it execute cleanly | agents execute |

**Roles** (the Driver and Decider may be the orchestrating session; the **Reviewers must be independent agent contexts** — separate subagents, not the session wearing a second hat. Same-session self-review isn't adversarial and reduces to a single-agent decision):

- **Driver / Author** — frames the decision, writes the Green Doc then the Blue Doc.
- **Reviewers (2–3, adversarial, distinct lenses)** — Green: critique direction / product-fit; Blue: critique correctness / scale / safety. Prompted to refute, not rubber-stamp.
- **Decider / Moderator** — runs the discussion, watches for premature convergence, approves each gate, records the decision + rationale, gives the go or escalates on non-convergence.

**The team operates in two phases, in this order:** (1) **independent critique** — each Reviewer reads the doc cold in its own context, no cross-talk, capturing uncorrelated objections; then (2) **moderated discussion** — Reviewers and Driver see each other's critiques and reconcile, the Decider moderates to consensus or escalation. The order is load-bearing: free discussion *first* lets the first confident voice anchor the rest into a false consensus (groupthink), which is the very failure the independence guards against. Reveal independently, then discuss.

**Where the record lands:** the `decisions.md` of the run's folder, `design/<YYYY-MM-DD-slug>/` (one folder per decision when no run is open); promote to an ADR in `docs/decisions/` when the decision is architectural. This is the asynchronous-review surface — the human audits, overrides, or learns from it after the fact.

**What still escalates to a real human** (the convention replaces the *routine, reversible* gate, not human-owned calls):

- Irreversible / destructive actions (deleting non-recreatable data, force-push, history rewrites).
- Outward-facing actions (external comms, publishing to third parties, closing or editing artifacts owned by others).
- Decisions the team **can't converge** on within a bounded number of rounds — escalate, but now with the Green/Blue docs attached, so the human starts from a fully-framed decision.

In those cases the review still runs and produces the *recommendation*; the human confirms the irreversible/outward step. Bound the loop with a fixed reviewer count, a single decider, and a max-rounds cap — hitting the cap triggers the escalation escape hatch rather than looping.

## Working Patterns

Concrete workflows showing how the multi-agent model plays out.

### Pattern A: Plan in chat, implement locally

When you have an open-ended question that needs analysis before action.

1. **Planner (claude.ai chat or Project)** — analyze across repos via GitHub connector. Produce an analysis doc as an artifact or codeblock.
2. **Implementer (local Claude Code)** — "Create `design/YYYY-MM-DD-topic/research.md` with this content: [paste]." (A run folder can hold research inputs beside its standard files.) Commit with `analysis:` prefix.
3. **Coordinator design (chat)** — review the analysis, identify discrete tasks, sketch issue titles, bodies, and field values. Output as a structured list (codeblock, or a file committed to the run's `design/` folder).
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

### Pattern E: Resolve a decision instead of blocking on it

When work hits a decision that would normally pause for the operator — and the decision is reversible (see Decision Review above for what isn't).

1. **Driver** — frame the decision and author the Green Doc (problem, goals, non-goals, ≥2 options + trade-offs). Commit it to a run folder under `design/` with `analysis:`.
2. **Reviewers** — adversarially critique the direction; the Driver revises until the Decider approves the strategy gate.
3. **Driver** — author the Blue Doc (the chosen path in execution detail) in the same record; **Reviewers** scrutinize correctness/scale/safety; **Decider** approves the blueprint gate.
4. **Implementer** — execute the Blue Doc. The committed record is the human's asynchronous-review surface.
5. **If the team can't converge, or the action is irreversible/outward-facing** — escalate to the human with both docs attached.

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
  - `design/<YYYY-MM-DD-slug>/` — one folder per design-loop run
    (`scratch/` inside it is gitignored)
  - `docs/` — durable docs for readers
  - `docs/decisions/` — ADRs
- **Commit prefixes:** `analysis:`, `plan:`, `impl:`, `status:`, plus standard
  `feat:`/`fix:`/`docs:`.
- **GitHub Issues are the task graph.** Open issues = pending work. Each
  work item gets an issue on its Project board (the domain's, or its
  product's) with Type, Priority,
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

- Scaffold `design/` and `docs/decisions/` (with `.gitkeep` files to keep empty dirs in git), and gitignore `design/*/scratch/`
- Create `CLAUDE.md` with the multi-agent boilerplate from Part 3 plus domain-specific content
- Create `STATUS.md` with current state
- Create or copy a Project board, one per product once a business has several (use the Copy project pattern from Part 3 if you have an existing board to template from)
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
# - ~/.claude/skills/ has the operating skills; each hub repo's .claude/ has its team skills
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

**Web Claude Code only sees the cloned repo.** Team skills committed at the repo root's `.claude/` come along; user-level skills, the domain-root `CLAUDE.md` and the optional domain-level skill aggregation don't (all live outside the repo). Cross-repo skills that reference siblings by relative path (`../other-repo/...`) also won't resolve in a web session, since the siblings aren't cloned. For those, carry a copy in the repo ([Stow Operations](#stow-operations)) or accept a smaller cloud skill set.

**claude.ai connector not seeing a new org.** After installing the Claude GitHub App on a new org, the claude.ai connector cache can lag. Disconnect and reconnect the GitHub connector in claude.ai settings.

## When submodules become necessary

The architecture in task-mgmt avoids submodules in most cases — directory-tree resolution does the job for local Claude Code. Submodules become useful when:

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
- Hand off via copy/paste, structured codeblocks, or by having Claude Code read a file in a `design/` run folder that chat committed

**Workarounds:**

- **Third-party MCP shims** (e.g., Composio's connect-apps) proxy claude.ai to 500+ apps including GitHub. Adds a third-party trust boundary; evaluate against your auth policies.
- **Official GitHub MCP server** — stdio transport, works with local Claude Code. Drop-in alternative to gh CLI if you prefer MCP tooling.

**What to watch:** the GitHub MCP team is aware of the chat-side write gap (there's an open feature request from April 2026). A hosted remote GitHub MCP endpoint with OAuth — comparable to how Gmail/Calendar/Drive connectors work today — would close this gap. When it ships, claude.ai chat becomes able to write directly and the role table's design/execute split collapses.

## Glossary

| Term | Meaning |
|------|---------|
| **Surface** | A distinct Claude product entry point (claude.ai chat, local Claude Code, web Claude Code, etc.) |
| **Resolution walk** | How Claude Code finds config up the directory tree. CLAUDE.md merges from every ancestor; slash commands stop at the first repo boundary; memory is keyed to the exact launch cwd (no walk) |
| **Project boundary** | A directory with `CLAUDE.md` or `.git` at its root. Slash-command resolution does not walk above it — the reason skills live at user level or at the repo root |
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

## Adapting task-mgmt

If you want to fork this repo for your own setup, the parts you'll customize:

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

**End of task-mgmt model.** Hand this to a Claude Code session along with a description of your current setup, and ask for a tailored migration plan.
