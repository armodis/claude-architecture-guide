---
name: board-setup
description: Set up a GitHub project board for the operating model — create or copy it from a template, set the fields and statuses, turn on the built-in workflows, link its repos, add it to the `board` config, and add the board automation workflow to its repos. Use when the user asks to create, copy or configure a project board, set up a board for a new product, or check that a board matches the board schema.
---

# board-setup

For a whole setup (organizations, repos and boards from a config file), run task-mgmt's `provision.py` and use this skill for what it reports and for one-off boards.

**Inputs:** the owner (organization or user), the template to copy, the repos that feed the board, whether those repos release by tag, and the board config at `~/.config/board/boards.json`.

## 1. Create or copy

- Copy a template with `copyProjectV2` (`gh api graphql`), or from the template's page in the web UI. The copy keeps fields, views and workflows except "Auto-add to project"; items don't copy.
- Link each repo: `linkProjectV2ToRepository`.

## 2. Config

Add the board to the owner's hub config (`<hub>/.task-mgmt/config.json`, under `owner.boards`), then run `provision.py config` to regenerate `boards.json` so `board` can work on it. Without hubs, add it to `boards.json` directly. The entry carries:

- `number`, plus `owner` and `owner_type` (`organization` or `user`) in `boards.json`; a hub entry takes them from the hub's owner.
- `repos`: the repos that feed it, so `board .` and `board which` find it from inside a repo.
- `hierarchy`: the Category levels, top first; `outside_hierarchy` for levels off the ladder; `parent_optional` for levels that may stand alone (for example `["Task"]` on a personal board).
- `release`: `none`, or `tags` when its repos release by tag (in a hub, `"release": "tags"` on the repo).
- `statuses` (in `boards.json` only), only to rename one (for example `{"done": "Shipped"}`); the rest keep their defaults.
- `read_only: true` for a board agents may only read.

Delete any example boards you don't use: `apply` and `claim` read back every configured board, and a placeholder makes them fail. Then `board fields <board>` and `board snapshot <board>` to confirm the command can read it.

## 3. Fields

| Field | Options |
|---|---|
| Status | Todo, Backlog, In Progress, In Review, Done; add Pending Release on a board whose repos release by tag |
| Priority | P0, P1, P2, P3 |
| Effort | number: 1, 2, 3, 5, 8 (amount of work) |
| Complexity | Trivial, Low, Medium, Medium-High, High (how hard it is) |
| Theme | the board's own areas; a product board gets the product's, a company board its functions |
| Category | the hierarchy levels above Task, for example Milestone, Epic, User Story |
| Agent | the agents named in the config's `agents`, plus its `operator`: who owns the item |
| Responder | the same options: the agent asked to review or answer, cleared once it responds |

Create Agent and Responder with `board setup-agents <board>` (`--dry-run` first): it creates them, or adds the options they are missing, from the config's `agents` and `operator`, keeping existing options and their ids. Create any other missing field with `createProjectV2Field` (`gh api graphql`). Add missing options with a `board` plan (`add_options`), which keeps every existing option and its id. When you call `updateProjectV2Field` yourself, for example to drop the templates' `Placeholder` Theme once real Themes exist, send each kept option with its `id`: an option sent without one is recreated and the items set to it are cleared.

## 4. Workflows (web UI only)

The API can read workflows but not create or enable them. Open the board's menu → Workflows and set:

- Item closed → Done, or Pending Release on a board whose repos release by tag
- Item reopened → In Progress
- Pull request linked to issue → In Review
- Pull request merged → Done
- Auto-close issue: on
- Item added to project: issues only → Backlog (`board` re-sets a Status a plan gave after this fires)
- Auto-add sub-issues to project: on
- Auto-add to project: filtered to `is:issue`, one per repo (the Free plan allows one per board; add other repos' issues yourself)

Read them back afterwards: `gh api graphql` on the project's `workflows { nodes { name enabled } }`.

## 5. Repo automation

Copy task-mgmt's `template/repo/.github/workflows/board.yml` into each repo. When a pull request merges, it keeps the board Status of the issues it closes right (`board guard`: In Review while another closing pull request is open, Done or Pending Release after the last) and, on a published release, moves released items to Done (`board release`). Its header lists the secret and variables the repo needs; setting the secret is the user's to do.

## 6. Report

List what was set, what needs the web UI or a secret, and the board's URL.
