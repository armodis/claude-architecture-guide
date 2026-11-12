#!/usr/bin/env python3
"""Token spend for a design-loop run, by step and model, from Claude Code transcripts.

  cost.py mark <run-dir> <step> [--at <iso-time>]   record that <step> starts now (or at <iso-time>)
  cost.py mark <run-dir> closed                      record that the run has ended
  cost.py report <run-dir>                           sum usage per step; rewrite the report block in cost.md

A run's steps are recorded in <run-dir>/cost-log.tsv (started_utc, step, session_id).
Marking any step also links the current session to the run. A step runs from its mark
to the next mark; the last step runs to the `closed` mark, or to now while the run is open.
A session's usage counts only from its first mark in the run.

Usage comes from each linked session's transcript and its subagents' transcripts:
~/.claude/projects/<slug>/<session>.jsonl and <session>/subagents/*.jsonl. They exist only
on the machine that ran the session, so `report` refuses to run, and leaves cost.md alone,
when any linked session's transcript is missing. Transcripts repeat a message's usage on
several lines; each message id counts once, using its last line. Other work done in a
linked session during a step's window is counted too.
"""
import collections
import datetime as dt
import glob
import json
import os
import sys

PROJECTS = os.path.expanduser("~/.claude/projects")
START, END = "<!-- report:start -->", "<!-- report:end -->"
FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
HEAD = ("input", "cache write", "cache read", "output")
CLOSED = "closed"


def now():
    return dt.datetime.now(dt.timezone.utc)


def parse_ts(s):
    t = dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def log_path(run):
    if not os.path.isdir(run):
        sys.exit(f"no run folder at {run}")
    return os.path.join(run, "cost-log.tsv")


def read_log(run):
    path = log_path(run)
    rows = []
    if os.path.exists(path):
        for n, line in enumerate(open(path), 1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            try:
                ts, step, sid = parts
                rows.append((parse_ts(ts), step.strip(), sid.strip()))
            except ValueError:
                sys.exit(f"{path}:{n}: expected <iso-time>TAB<step>TAB<session-id>, got {line!r}")
    # by time; marks in the same second keep their order in the file
    return [r for _, r in sorted(enumerate(rows), key=lambda x: (x[1][0], x[0]))]


def mark(run, step, at=None):
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        sys.exit("CLAUDE_CODE_SESSION_ID is not set; run this from inside a Claude Code session")
    path = log_path(run)
    ts = parse_ts(at) if at else now()
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write("# started_utc\tstep\tsession_id\n")
        f.write(f"{ts.isoformat(timespec='seconds')}\t{step}\t{sid}\n")
    print(f"marked {step} at {ts.isoformat(timespec='seconds')} in session {sid}")


def transcripts(sid):
    main = glob.glob(os.path.join(PROJECTS, "*", f"{sid}.jsonl"))
    subs = glob.glob(os.path.join(PROJECTS, "*", sid, "subagents", "*.jsonl"))
    return main, subs


def messages(paths):
    """Yield (timestamp, model, usage) once per assistant message."""
    last = {}
    for path in paths:
        for line in open(path):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            m = d.get("message")
            if d.get("type") != "assistant" or not isinstance(m, dict) or "usage" not in m:
                continue
            key = m.get("id") or d.get("requestId") or d.get("uuid")
            last[key] = (parse_ts(d["timestamp"]), m.get("model", "?"), m["usage"])
    return last.values()


def report(run):
    log = read_log(run)
    steps = [r for r in log if r[1] != CLOSED]
    if not steps:
        sys.exit(f"no steps marked in {run}/cost-log.tsv")
    # Each step runs until the next mark of any kind. A step marked after `closed` reopens the
    # run, so the run ends at the last mark only when that mark is `closed`.
    marks = log  # read_log sorts by time, keeping file order within a second
    closed = marks[-1][0] if marks[-1][1] == CLOSED else None
    windows = [(ts, marks[i + 1][0] if i + 1 < len(marks) else now(), step)
               for i, (ts, step, _) in enumerate(marks) if step != CLOSED]

    first_mark = {}
    for ts, _, sid in log:
        first_mark.setdefault(sid, ts)
    found = {sid: transcripts(sid) for sid in first_mark}
    missing = [sid for sid, (main, _) in found.items() if not main]
    if missing:
        sys.exit("no transcript on this machine for session(s) " + ", ".join(missing)
                 + "; cost.md left unchanged. Run the report where those sessions ran.")

    totals = collections.defaultdict(lambda: [0, 0, 0, 0])
    for sid, (main, subs) in found.items():
        for ts, model, usage in messages(main + subs):
            if ts < first_mark[sid]:
                continue
            for start, stop, step in windows:
                if start <= ts < stop:
                    t = totals[(step, model)]
                    for i, k in enumerate(FIELDS):
                        t[i] += usage.get(k) or 0
                    break

    order = list(dict.fromkeys(step for _, _, step in windows))
    lines = ["| Step | Model | " + " | ".join(HEAD) + " |",
             "|---|---|" + "---:|" * len(HEAD)]
    grand = [0, 0, 0, 0]
    for step in order:
        for (s, model), t in sorted(totals.items()):
            if s == step:
                lines.append(f"| {step} | {model} | " + " | ".join(f"{v:,}" for v in t) + " |")
                grand = [a + b for a, b in zip(grand, t)]
    lines.append("| **Total** | | " + " | ".join(f"**{v:,}**" for v in grand) + " |")
    lines.append("")
    state = (f"Run closed {closed.isoformat(timespec='seconds')}." if closed
             else "Run still open: the last step is counted up to now.")
    lines.append(f"Generated {now().isoformat(timespec='seconds')} from {len(found)} session(s) "
                 f"and their subagents. {state}")
    table = "\n".join(lines)

    path = os.path.join(run, "cost.md")
    text = open(path).read() if os.path.exists(path) else f"# Cost\n\n{START}\n{END}\n"
    if START in text and END in text:
        head, rest = text.split(START, 1)
        text = head + START + "\n" + table + "\n" + END + rest.split(END, 1)[1]
    else:
        text = text.rstrip("\n") + f"\n\n{START}\n{table}\n{END}\n"
    open(path, "w").write(text)
    print(table)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) in (3, 5) and a[0] == "mark" and (len(a) == 3 or a[3] == "--at"):
        mark(a[1], a[2], a[4] if len(a) == 5 else None)
    elif len(a) == 2 and a[0] == "report":
        report(a[1])
    else:
        sys.exit(__doc__)
