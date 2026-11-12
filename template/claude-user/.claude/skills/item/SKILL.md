---
name: item
description: File, groom, claim, finish or close an issue on a GitHub project board through the `board` command, with every required field set and the change read back. Use when the user asks to file an issue or task, add work to the board, set fields, move an item under a parent, claim or finish an item, or close one as done, not planned or duplicate.
---

# item

Every board write goes through `board` (`board --help` lists the commands and the plan format). Judgment produces a JSON change plan; `board check` shows the dry run and `board apply` writes it and reads back what landed.

**Inputs:** the user's request, the board named in the board config (`board boards` lists them), and the board's snapshot (`board snapshot <board>`, at most 24 hours old; take a fresh one if it is older).

## Look first

- `board search <owner> <words>` for duplicates, open and closed, before filing anything.
- `board tree <board> <owner/repo#n>` for the workstream a new item will join, so it lands at the right level.

## File an issue

Write a plan with one `create` op per issue and every field you can fill:

- **Every issue:** Status, Priority, Theme, Complexity, and `type` (Task, Bug or Feature; a parent is Feature).
- **Effort** on Tasks and Stories. **Category** on parents, from the board's hierarchy in the config.
- **parent** for everything below the board's top level. Link a child only under a higher level.
- **Status:** Todo when it is ready (required fields set, what done looks like stated in the body, no open decision); Backlog otherwise. Say in the body what keeps it in Backlog.
- **Body:** what done looks like, and links to the evidence or discussion it came from. Refer to issues of another owner by full URL in a comment you post yourself, not in text the plan writes.

Use `"as": "name"` on a create and `"$name"` in later ops to build a parent and its children in one plan.

## Change, claim, finish, close

- **Fields and links:** `set_field`, `clear_field`, `attach` (moves the child if it has a parent), `detach`, `set_type`, `label`.
- **Claim:** `board claim <board> <owner/repo#n> --status-md STATUS.md` sets In Progress and adds the line to the STATUS.md of the repo that holds the issue. Commit that line with a `status:` prefix.
- **Finish:** `board finish <board> <owner/repo#n> --close --status-md STATUS.md`. When a pull request closes the issue, let the merge close it instead and finish without `--close`.
- **Close:** `close` with `reason` completed, not_planned or duplicate (`duplicate_of` names the other issue). Read both bodies before closing one as a duplicate.

## Check, then apply

1. `board check <board> plan.json` and read the dry run.
2. If it prints **needs review**, show the user the dry run and wait for their go; then `board apply <board> plan.json --approved`.
3. Otherwise `board apply <board> plan.json`.
4. Report what landed from the read-back, with a link to each issue. Exit code 3 means something outside the plan also changed on a board (for example a sub-issue auto-add): report it.
