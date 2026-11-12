---
name: pickup
description: Choose the next ready item from a GitHub project board by the selection policy, check it is still free, and claim it through the `board` command. Use when the user says "pick up the next item", "what's next on the board", "work the queue", names a selection mode such as quick-wins, or starts an unattended run that should take ready work.
---

# pickup

**Inputs:** the board config (`board boards`), the board's snapshot (`board snapshot <board>`, refreshed when older than 24 hours), the repo's STATUS.md "What's in progress", and the user's filters: a repo, a label, or a named mode.

## Select

1. `git pull`, then read STATUS.md "What's in progress" in the repo.
2. `board select <board> [--repo owner/repo] [--label L] --count 5`. It returns Todo items ordered by Priority, then Effort, then age, and lists the items it skipped and why.
3. Narrow by mode when the user names one: **quick-wins** (Priority ≤ P1 and Effort ≤ 2), **focused-feature** (Priority ≤ P1 and Effort ≥ 5), **backlog-cleanup** (Effort ≤ 2).
4. Skip an item that is assigned to a person, blocked by an open issue, or already in some STATUS.md "What's in progress". Pick only Todo items; an unattended run may refine a Backlog item up to its open decision and leave it in Backlog.
5. An item missing required fields is not picked: list it as "needs grooming", and fill what the issue itself makes clear through the `item` skill.

## Claim

1. Read the chosen issue live (`gh issue view`) to confirm it is open, still Todo and still unassigned.
2. `board claim <board> <owner/repo#n> --status-md STATUS.md`, then commit STATUS.md with `status: claim #N` and push.
3. Tell the user what was claimed, why it came first, and what was skipped.
