#!/usr/bin/env python3
"""Live acceptance test for `board`, run against a board's standing test fixture.

  python3 tests/board/live_fixture.py <board> [<board>...] [--create] [--read-only <board>]

Uses your board config ($BOARD_CONFIG or ~/.config/board/boards.json) and a fresh state folder.
Each named board needs a fixture: issues labelled `test-fixture` and titled "[Test fixture] ...",
with one Epic, one User Story under it, and at least two Tasks under the Story, in one repo.
`board-setup` and the guide describe it; the test finds it by label and level.

Writes to GitHub only on fixture issues, and puts them back with `board reset-fixture` at the
end. With --create it also files one throwaway fixture issue, then detaches, closes (not
planned) and archives it, to exercise create; leave it off unless create changed.
--read-only <board> checks that a read-only board snapshots and refuses a write.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "..", "..", "template", "board", ".local", "bin", "board")
TMP = tempfile.mkdtemp(prefix="board-live-")
ENV = dict(os.environ, XDG_STATE_HOME=TMP, PYTHONDONTWRITEBYTECODE="1")
results = []


def run(*args, ok=(0,)):
    r = subprocess.run([sys.executable, BOARD, *args], capture_output=True, text=True, env=ENV)
    if r.returncode not in ok:
        print(r.stdout[-1500:], r.stderr[-800:], sep="\n")
    return r


def write_plan(ops):
    path = os.path.join(TMP, f"plan-{len(results)}-{os.getpid()}.json")
    with open(path, "w") as f:
        json.dump(ops, f)
    return path


def plan(board, ops, *flags, ok=(0,)):
    return run("apply", board, write_plan(ops), *flags, ok=ok)


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f'{"PASS" if cond else "FAIL"}  {name}' + (f"  ({str(detail)[-400:]})" if detail and not cond else ""))


def snap(board):
    run("snapshot", board)
    with open(os.path.join(TMP, "board", f"{board}.json")) as f:
        s = json.load(f)
    return {e["ref"]: e for e in s["items"] if "ref" in e and not e["archived"]}


def fixture(items):
    fx = {r: e for r, e in items.items() if "test-fixture" in e["labels"] and e["title"].startswith("[Test fixture]")}
    epic = next((r for r, e in fx.items() if e["fields"].get("Category") == "Epic"), None)
    story = next((r for r, e in fx.items() if e["fields"].get("Category") == "User Story" and e["parent"] == epic), None)
    tasks = sorted((r for r, e in fx.items() if e["parent"] == story and not e["fields"].get("Category")
                    and e["state"] == "OPEN"), key=lambda r: int(r.split("#")[1]))
    return epic, story, tasks


def main(argv):
    create = "--create" in argv
    ro = argv[argv.index("--read-only") + 1] if "--read-only" in argv else None
    boards = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--read-only")]
    if not boards and not ro:
        sys.exit(__doc__)
    for board in boards:
        items = snap(board)
        epic, story, tasks = fixture(items)
        if not (epic and story and len(tasks) >= 2):
            check(f"{board}: fixture found (Epic, Story, two Tasks)", False, f"epic={epic} story={story} tasks={tasks}")
            continue
        check(f"{board}: fixture found", True)
        t1, t2 = tasks[0], tasks[1]
        repo = t1.split("#")[0]
        f = json.loads(run("fields", board).stdout)
        check(f"{board}: fields read", {"Status", "Priority", "Effort", "Category"} <= set(f["fields"]))

        if create:
            r = plan(board, [{"op": "create", "repo": repo, "title": "[Test fixture] Throwaway: created and closed by the live test",
                              "body": "Created by the live test to exercise create; closed and archived straight after.",
                              "type": "Task", "parent": story, "labels": ["test-fixture"], "fields": {"Priority": "P3"},
                              "as": "tmp"},
                             {"op": "detach", "child": "$tmp"}, {"op": "close", "item": "$tmp", "reason": "not_planned"},
                             {"op": "remove", "item": "$tmp"}])
            check(f"{board}: create, detach, close and archive a throwaway", r.returncode in (0, 3) and "MISMATCH" not in r.stdout,
                  r.stdout)

        out = run("tree", board, epic).stdout
        check(f"{board}: tree shows the workstream with counts", t1 in out and "counts:" in out, out)

        bulk = [{"op": "set_field", "item": t, "field": k, "value": v} for t in (t1, t2) for k, v in (("Priority", "P2"), ("Effort", 2))]
        d = run("check", board, write_plan(bulk))
        check(f"{board}: dry run writes nothing", d.returncode == 0 and "nothing written" in d.stdout, d.stdout)
        r = plan(board, bulk)
        check(f"{board}: bulk edit read back", r.returncode == 0 and "every read-back matched" in r.stdout, r.stdout)

        # relationships, live: relate both ways, block and its effect on select, then remove
        r = plan(board, [{"op": "relate", "item": t1, "other": t2}, {"op": "block", "item": t2, "by": t1}])
        check(f"{board}: relate and block read back", r.returncode == 0 and r.stdout.count(" ok") >= 2, r.stdout)
        plan(board, [{"op": "set_field", "item": t, "field": "Status", "value": "Todo"} for t in (t1, t2)])
        sel = run("select", board, "--repo", repo, "--include-fixture", "--count", "20", ok=(0, 1))
        check(f"{board}: select skips the blocked task", f"skipped {t2}: blocked by {t1}" in sel.stderr, sel.stderr)
        r = plan(board, [{"op": "unrelate", "item": t1, "other": t2}, {"op": "unblock", "item": t2, "by": t1}])
        check(f"{board}: unrelate and unblock read back", r.returncode == 0 and "MISMATCH" not in r.stdout, r.stdout)

        # rules refused at check time
        r = run("check", board, write_plan([{"op": "attach", "parent": t1, "child": story}]), ok=(1,))
        check(f"{board}: upside-down attach refused", r.returncode == 1 and "lower one" in r.stderr, r.stderr)
        r = run("check", board, write_plan([{"op": "create", "repo": repo, "title": "[Test fixture] x",
                                             "body": "see someone-else/repo#1", "labels": ["test-fixture"]}]), ok=(1,))
        check(f"{board}: another owner's mention refused", r.returncode == 1 and "another owner" in r.stderr, r.stderr)

        # claim and finish, recorded in a STATUS.md copy; claim assigns and refuses a second claim
        md = os.path.join(TMP, f"STATUS-{board}.md")
        with open(md, "w") as fh:
            fh.write("# STATUS\n\n## What's in progress\n\n- Nothing in flight.\n\n## What's next\n")
        c = run("claim", board, t1, "--status-md", md)
        items = snap(board)
        with open(md) as fh:
            text = fh.read()
        check(f"{board}: claim sets In Progress, assigns, records STATUS.md",
              c.returncode == 0 and items[t1]["fields"].get("Status") == "In Progress" and items[t1]["assignees"] and t1 in text,
              c.stdout + c.stderr)
        again = run("claim", board, t1, ok=(1,))
        check(f"{board}: a second claim is refused", again.returncode == 1 and "not 'Todo'" in again.stderr, again.stderr)
        fin = run("finish", board, t1, "--status-md", md)
        items = snap(board)
        with open(md) as fh:
            text = fh.read()
        check(f"{board}: finish sets Done and clears STATUS.md", fin.returncode in (0, 3) and t1 not in text
              and items[t1]["fields"].get("Status") == "Done", fin.stdout)
        subprocess.run(["gh", "issue", "edit", t1.split("#")[1], "--repo", repo, "--remove-assignee", "@me"],
                       capture_output=True)

        # with the board's "Auto-close issue" workflow on, Done closes the issue; otherwise hygiene flags it
        h = run("hygiene", board, "--include-fixture").stdout
        closed = snap(board)[t1]["state"] == "CLOSED"
        check(f"{board}: Done closes the issue, or hygiene reports it open", closed or f"{t1}  Status is Done but the issue is open" in h, h)

        # notes
        n = run("note", board, t2, "readiness", "ready once Task 1 lands", "--by", "live-test")
        shown = run("notes", board, t2).stdout
        check(f"{board}: note appended and read back", n.returncode == 0 and "ready once Task 1 lands" in shown, shown)

        # promote (type follows the level), reparent, then back
        r = plan(board, [{"op": "set_field", "item": t2, "field": "Category", "value": "User Story"},
                         {"op": "attach", "parent": epic, "child": t2}], "--approved")
        items = snap(board)
        check(f"{board}: promotion sets Feature and reparents", r.returncode in (0, 3) and items[t2]["issue_type"] == "Feature"
              and items[t2]["parent"] == epic, r.stdout)
        r = plan(board, [{"op": "clear_field", "item": t2, "field": "Category"}, {"op": "attach", "parent": story, "child": t2}],
                 "--approved")
        items = snap(board)
        check(f"{board}: demotion sets Task and reparents back", r.returncode in (0, 3) and items[t2]["issue_type"] == "Task"
              and items[t2]["parent"] == story, r.stdout)

        r = plan(board, [{"op": "close", "item": t2, "reason": "duplicate", "duplicate_of": t1}])
        check(f"{board}: close as duplicate read back", r.returncode in (0, 3) and "closed as DUPLICATE ok" in r.stdout, r.stdout)
        r = plan(board, [{"op": "reopen", "item": t2}])
        check(f"{board}: reopen read back", r.returncode in (0, 3), r.stdout)

        r = run("reset-fixture", board, ok=(0, 3))
        check(f"{board}: reset-fixture restores the resting state", r.returncode in (0, 3), r.stdout)
        r = run("reset-fixture", board)
        check(f"{board}: fixture at rest afterwards", "already at rest" in r.stdout, r.stdout)

    if ro:
        r = run("snapshot", ro)
        check(f"{ro}: snapshot works", r.returncode == 0)
        r = run("check", ro, write_plan([{"op": "reopen", "item": "x/y#1"}]), ok=(1,))
        check(f"{ro}: writes refused (read-only)", r.returncode == 1 and "read-only" in r.stderr, r.stderr)

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
