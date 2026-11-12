---
name: board-setup
description: Set up a GitHub project board for the operating model — create or copy it from a template, set the fields and statuses, turn on the built-in workflows, link its repos, and add it to the `board` config. Use when the user asks to create, copy or configure a project board, set up a board for a new product, or check that a board matches the guide's schema.
---

# board-setup

For a whole setup (organizations, repos and boards from a config file), run the guide's `provision.py` and use this skill for what it reports and for one-off boards.

**Inputs:** the owner (organization or user), the template to copy if there is one, the repos that feed the board, and the board config at `~/.config/board/boards.json` (copy `boards.example.json` beside it on first use).

## 1. Create or copy

- Copy a template with `copyProjectV2` (`gh api graphql`), or from the template's page in the web UI. The copy keeps fields, views and workflows except "Auto-add to project"; items don't copy.
- Link each repo: `linkProjectV2ToRepository`.

## 2. Fields

| Field | Options |
|---|---|
| Status | Todo, Backlog, In Progress, In Review, Done; add Pending Release on a board whose repos release by tag |
| Priority | P0, P1, P2, P3 |
| Effort | number: 1, 2, 3, 5, 8 (amount of work) |
| Complexity | Trivial, Low, Medium, Medium-High, High (how hard it is) |
| Theme | the board's own areas; a product board gets the product's, a company board its functions |
| Category | the hierarchy levels above Task, for example Milestone, Epic, User Story |

Add missing options with a `board` plan (`add_options`), which keeps every existing option and its id. When you call `updateProjectV2Field` yourself, send each kept option with its `id`: an option sent without one is recreated and the items set to it are cleared.

## 3. Workflows (web UI only)

The API can read workflows but not create or enable them. Open the board's menu → Workflows and set:

- Item closed → Done (Pending Release on a board whose repos release by tag)
- Item reopened → In Progress
- Pull request linked to issue → In Review
- Pull request merged → Done
- Auto-close issue: on
- Item added to project: issues only → Backlog
- Auto-add sub-issues to project: on
- Auto-add to project: one per repo, filtered to `is:issue` (the Free plan allows one per board)

Read them back afterwards: `gh api graphql` on the project's `workflows { nodes { name enabled } }`.

## 4. Config

Add the board to `boards.json`: `owner`, `owner_type`, `number`, `hierarchy` (Category levels, top first), `outside_hierarchy`, and `read_only` for a board agents may only read. Then `board fields <board>` and `board snapshot <board>` to confirm the command can read it.

## 5. Report

List what was set, what needs the web UI, and the board's URL.
