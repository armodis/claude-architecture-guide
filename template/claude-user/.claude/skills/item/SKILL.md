---
name: item
description: File, groom, link, claim, finish or close an issue on a GitHub project board through the `board` command, with every required field set and the change read back. Use when the user asks to file an issue or task, add work to the board, set fields, move an item under a parent, link or block issues, claim or finish an item, or close one as done, not planned or duplicate.
---

# item

Every board write goes through `board` (`board --help` lists the commands, the plan format and the rules plans are checked against). Judgment produces a JSON change plan; `board check` shows the dry run and `board apply` writes it and reads back what landed.

**Inputs:** the user's request; the board config (`board boards`, or `board which` for the current repo's board, which `.` also names); the board's snapshot with its analysis notes (`board snapshot <board>`, refreshed automatically once older than a day); and, for each issue you change, a live read (`gh issue view`).

## Look first

- `board search <owner> <words>` for duplicates, open and closed, before filing anything. It searches titles live.
- `board tree <board> <owner/repo#n>` for the workstream a new item will join, so it lands at the right level.
- `board notes <board> <owner/repo#n>` for what earlier sessions concluded about an item. Notes marked STALE were written before the issue last changed: check them again before relying on them.

## File an issue

One `create` op per issue, with every field you can fill. `board check` refuses a create that's missing a required field and names what's missing:

- **Every issue:** Status, Priority, Theme, Complexity, and `type` (Task, Bug or Feature; a parent is Feature).
- **Effort** on Tasks and Stories. **Category** on parents, from the board's hierarchy (`board boards`, then the config).
- **parent** for everything below the board's top level, at a higher level than the new issue. Skipped levels are allowed; an upside-down link is refused.
- **Status:** Todo when it's ready: required fields set, a "Done when:" line in the body, and no open decision. Backlog otherwise, with what keeps it there said in the body.
- **Body:** what done looks like, and links to the evidence or discussion it came from. Mention issues of the same owner as `owner/repo#n`; an issue of another owner goes in a `relate` or `block` op, not in the text (the check refuses it).
- **Work only a person can do:** assign that person with `gh issue edit <n> --repo <owner/repo> --add-assignee <login>`, so agents skip it.

Use `"as": "name"` on a create and `"$name"` in later ops to build a parent and its children in one plan.

## Change, link, claim, finish, close

- **Fields and links:** `set_field`, `clear_field`, `attach` (moves the child if it has a parent), `detach`, `set_type`, `label`. Setting Category on a Task promotes it to Feature; clearing it demotes it back.
- **Relationships:** `relate` / `unrelate` with `other`, and `block` / `unblock` with `by`. The other issue may belong to any owner; nothing moves between boards.
- **Pull requests:** a pull request that closes no issue goes on the board with `add_pr`, which sets In Review.
- **Claim:** `board claim <board> <owner/repo#n> --status-md STATUS.md`. It refuses an item that isn't open and at Todo or that someone else holds, sets In Progress, assigns you, sets Agent to your `BOARD_AGENT` on a board with that field (refusing an item another agent holds), and adds the line, naming you, to the STATUS.md of the repo that holds the issue. Commit that line with a `status:` prefix.
- **Finish:** after the pull request that closes the issue merges, `board finish <board> <owner/repo#n> --status-md STATUS.md`. It sets Done, or Pending Release on a board whose repos release by tag, clears Responder, and keeps Agent as the record of who did the work. For work with no pull request, add `--close`. When several pull requests deliver one issue, each says `closes #N`: GitHub closes the issue at the first merge, and the repo's board workflow (`board guard`) keeps it at In Review until the last one merges. Without that workflow, say `refs #N` on all but the last.
- **Close:** `close` with `reason` completed, not_planned or duplicate (`duplicate_of` names the other issue). Read both bodies before closing one as a duplicate.
- **Notes:** record a conclusion worth keeping with `board note <board> <owner/repo#n> <kind> <text>`, for example `duplicate-candidate`, `scope`, `suggested-parent` or `readiness`.

## Check, then apply

1. `board check <board> plan.json` and read the dry run.
2. If it prints **needs review**, show the user the dry run and wait for their go; then `board apply <board> plan.json --approved`.
3. Otherwise `board apply <board> plan.json`.
4. Report what landed from the read-back, with a link to each issue. Exit code 3 means something outside the plan also changed on a board, such as a sub-issue auto-add or a board workflow closing the finished issue: report it. Expected workflow effects can be named as such.

## Ask, answer, hand over

Agents in any harness coordinate on the item itself. Set `BOARD_AGENT` (an option of the board's Agent field), `BOARD_MODEL` and `BOARD_SESSION` first; `board` signs each comment with them. `ask`, `answer`, `handoff` and `ack` refuse to run without `BOARD_AGENT`; `claim` without it leaves Agent unset and says so.

- **Ask:** `board ask <board> <item> <agent> review|question <text>` sets Responder and posts a marked comment; a review ask on an issue links its open pull request. Asking the config's operator also uses GitHub's own signal: a review request, or an @-mention for a question.
- **Answer:** `board answer <board> <item> [--verdict approve|changes] <text>`. With a verdict it posts a comment review on the pull request that opens with the verdict line, then answers the asker and clears Responder.
- **Hand over:** `board handoff <board> <item> <agent> <text> --status-md STATUS.md` sets Agent to the new agent and rewrites the STATUS.md line.
- **Read:** `board inbox` lists asks waiting on you, replies and handoffs on your items that you haven't answered, and the account's notifications on your items. `board ack <board> <item>` marks a reply read; on an item waiting on the operator, who answers on GitHub itself, it also clears Responder.
- Put `--` before text that starts with `-`.
- Write agent names in bold; an @-mention notifies the GitHub user of that name.
