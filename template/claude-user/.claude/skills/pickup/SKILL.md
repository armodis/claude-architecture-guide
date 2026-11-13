---
name: pickup
description: Choose the next ready item from a GitHub project board by the selection policy, check it is still free, and claim it through the `board` command. Use when the user says "pick up the next item", "what's next on the board", "work the queue", names a selection mode such as quick-wins, or starts an unattended run that should take ready work.
---

# pickup

**Inputs:** the board config (`board boards`, or `.` for the current repo's board); the board's snapshot with its analysis notes (`board snapshot <board>`, refreshed automatically once older than a day); the repo's STATUS.md "What's in progress"; and the user's filters: a repo, a label, or a named mode.

## Select

1. `git pull`, then read STATUS.md "What's in progress" in the repo, and run `board inbox`: answer what's waiting on you before taking new work.
2. `board select <board> [--repo owner/repo] [--label L] --count 20`. It returns Todo items ordered by Priority, then Effort, then age. It skips, with the reason: items another agent holds (Agent set), items assigned to someone, items blocked by an open issue, items missing a required field ("needs grooming"), and items already claimed in STATUS.md.
3. Narrow by mode when the user names one: **quick-wins** (Priority ≤ P1 and Effort ≤ 2), **focused-feature** (Priority ≤ P1 and Effort ≥ 5), **backlog-cleanup** (Effort ≤ 2).
4. Pick only from what `select` returned. An unattended run may also refine a Backlog item up to its open decision, record what it found with `board note`, and leave it in Backlog.
5. For each item skipped as "needs grooming", fill what the issue itself makes clear through the `item` skill, and list the rest for the user.
6. Read `board notes` on the chosen item; recheck any marked STALE.

## Claim

1. Read the chosen issue live (`gh issue view`) to confirm it is open and its scope still matches.
2. `board claim <board> <owner/repo#n> --status-md STATUS.md`. It refuses an item that is no longer at Todo or that someone else holds, sets In Progress, assigns you, and sets Agent to your `BOARD_AGENT`. Then commit STATUS.md with `status: claim #N` and push.
3. Tell the user what was claimed, why it came first, and what was skipped.
