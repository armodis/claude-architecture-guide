#!/usr/bin/env python3
"""preflight — check that every checkout a run touches is safe to work in, before the run starts.

  preflight.py [PATH ...] [--pull] [--no-config]
  preflight.py --controls

Repos checked: the current repo, plus the paths given; with no paths, the board config's
"preflight" "repos" list instead. Each is fetched, then reported: its branch, clean or changed,
and ahead and behind its remote branch.

What blocks (exit 1):

- uncommitted changes while behind the branch's own remote branch;
- a branch that has diverged from its own remote branch (a fast-forward can't fix it);
- a failed sign-in probe.

A feature branch that tracks a different branch, such as one created from origin/main, is
compared with its own remote branch when one exists; the other branch's moves are reported
without blocking. --pull fast-forwards a clean checkout that is only behind its own remote
branch; nothing else is ever changed.

The config's "preflight" "probes" are cheap read commands, one per tool a run needs, each run
every time and reported pass or fail with its fix.

Exit codes: 0 all clear, 1 something blocks the run, 2 the check itself could not run (a
missing path, not a git checkout, a failed or timed-out fetch, an unreadable config).

Config: the "preflight" section of the board config ($BOARD_CONFIG or
~/.config/board/boards.json), all optional:

  "preflight": {
    "repos": ["~/work/acme-co/ops"],
    "probes": [{"name": "GitHub", "run": "gh api user -q .login", "fix": "gh auth login"}]
  }
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

CLEAR, BLOCKED, CANT = 0, 1, 2
CONFIG_PATH = os.environ.get("BOARD_CONFIG") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "board", "boards.json")


class CantCheck(Exception):
    pass


def git(path, *args, timeout=120):
    try:
        r = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CantCheck(f"git {args[0]} timed out after {timeout}s")
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def load_section(path=None):
    path = path or CONFIG_PATH
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f).get("preflight", {})


def toplevel(path):
    rc, out, _ = git(path, "rev-parse", "--show-toplevel")
    return out if rc == 0 else None


def counts(top, a, b):
    _, out, _ = git(top, "rev-list", "--left-right", "--count", f"{a}...{b}")
    ahead, behind = (int(x) for x in out.split())
    return ahead, behind


def describe(ahead, behind):
    if not (ahead or behind):
        return "up to date with"
    return ", ".join(s for s in (f"{ahead} ahead" if ahead else "", f"{behind} behind" if behind else "") if s) + " of"


def reason(err):
    """git's own reason for a failure, not its closing 'Aborting'."""
    lines = [l.strip() for l in err.splitlines() if l.strip() and l.strip().lower() != "aborting"]
    return lines[0] if lines else "pull by hand"


def check_repo(path, pull=False, fetch=True):
    """Returns (code, line, fix). code: CLEAR, BLOCKED or CANT."""
    name = os.path.basename(os.path.normpath(path)) or path
    if not os.path.isdir(path):
        return CANT, f"{name}: no such folder {path}", "check the path in the run or the config"
    try:
        top = toplevel(path)
        if not top:
            return CANT, f"{name}: {path} is not a git checkout", "check the path"
        if fetch:
            rc, _, err = git(top, "fetch", "--quiet")
            if rc:
                return CANT, f"{name}: fetch failed: {reason(err)}", "check the network and the remote's sign-in"
        _, branch, _ = git(top, "symbolic-ref", "--quiet", "--short", "HEAD")
        _, status, _ = git(top, "status", "--porcelain")
        changed = [l for l in status.splitlines() if not l.startswith("??")]
        untracked = len(status.splitlines()) - len(changed)
        state = f"{len(changed)} changed" if changed else "clean"
        if untracked:
            state += f", {untracked} untracked"
        if not branch:
            return CLEAR, f"{name}: detached HEAD, {state}", None
        rc, upstream, _ = git(top, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if rc:
            return CLEAR, f"{name}: {branch}, {state}, no upstream", None
        remote = upstream.split("/", 1)[0]
        own = upstream if upstream == f"{remote}/{branch}" else None
        if own is None and git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}")[0] == 0:
            own = f"{remote}/{branch}"
        notes = []
        if own != upstream:  # tracks another branch, such as main: report its moves, never block on them
            _, moved = counts(top, "HEAD", upstream)
            if moved:
                notes.append(f"{upstream} has moved {moved}")
        if own is None:
            return CLEAR, f"{name}: {branch}, {state}, not pushed yet" + (f"; {notes[0]}" if notes else ""), None
        ahead, behind = counts(top, "HEAD", own)
        head = f"{name}: {branch}, {state}, {describe(ahead, behind)} {own}" + "".join(f"; {n}" for n in notes)
        if ahead and behind:
            return BLOCKED, f"{head} (diverged)", f"rebase or merge {own} in {top}, then rerun"
        if behind and changed:
            return BLOCKED, head, f"commit or stash the changes in {top}, then pull"
        if behind and pull:
            rc, _, err = git(top, "merge", "--ff-only", "--quiet", own)
            if rc:
                return BLOCKED, f"{head}; fast-forward failed", reason(err)
            return CLEAR, f"{name}: {branch}, {state}, pulled {behind} from {own}" + "".join(f"; {n}" for n in notes), None
        if behind:
            return CLEAR, f"{head} (--pull fast-forwards it)", None
        return CLEAR, head, None
    except CantCheck as e:
        return CANT, f"{name}: {e}", "check the network and rerun"


def run_probe(p):
    """Returns (code, line, fix)."""
    try:
        r = subprocess.run(p["run"], shell=True, capture_output=True, text=True, timeout=60)
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
    name = p.get("name") or p["run"]
    return (CLEAR, f"{name}: signed in", None) if ok else (BLOCKED, f"{name}: probe failed ({p['run']})", p.get("fix") or "sign in again")


def targets_for(paths, section, cwd=None):
    """The current repo, plus the paths given; with no paths, the config's list instead."""
    here = toplevel(cwd or os.getcwd())
    out, seen = [], set()
    for p in ([here] if here else []) + list(paths or section.get("repos", [])):
        full = os.path.realpath(os.path.expanduser(p))
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def preflight(paths, pull=False, section=None, cwd=None, fetch=True, out=print):
    section = {} if section is None else section
    worst = CLEAR
    for p in targets_for(paths, section, cwd):
        code, line, fix = check_repo(p, pull=pull, fetch=fetch)
        out(("✓ " if code == CLEAR else "✗ ") + line + (f"\n    fix: {fix}" if fix else ""))
        worst = max(worst, code)
    for probe in section.get("probes", []):
        code, line, fix = run_probe(probe)
        out(("✓ " if code == CLEAR else "✗ ") + line + (f"\n    fix: {fix}" if fix else ""))
        worst = max(worst, code)
    out({CLEAR: "preflight: all clear", BLOCKED: "preflight: blocked; fix the lines marked ✗ before the run",
         CANT: "preflight: could not check everything; fix the lines marked ✗"}[worst])
    return worst


# ---------------------------------------------------------------- controls

def controls(out=print):
    """Each check two-sided: a case that must fire, and a clean case that must not. Offline:
    every remote is a bare repo in a temp folder, removed afterwards."""
    tmp = tempfile.mkdtemp(prefix="preflight-controls-")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com", GIT_CONFIG_GLOBAL=os.devnull)
    saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL",)}
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    results = []

    def sh(cmd, cwd=tmp):
        subprocess.run(cmd, shell=True, cwd=cwd, env=env, check=True, capture_output=True)

    def repo(name):
        """A clone of a fresh origin, plus a second clone that can push ahead of it."""
        sh(f"git init -q --bare -b main {name}.git && git clone -q {name}.git {name} && "
           f"cd {name} && echo a > f && git add f && git commit -qm a && git push -q origin main && cd .. && "
           f"git clone -q {name}.git {name}-other")
        return os.path.join(tmp, name)

    def push_ahead(name, branch="main", path="f"):
        sh(f"cd {name}-other && git fetch -q && git checkout -q -B {branch} origin/{branch} && "
           f"echo b >> {path} && git add {path} && git commit -qm b && git push -q origin {branch}")

    def head(path):
        return git(path, "rev-parse", "HEAD")[1]

    def run(paths, **kw):
        lines = []
        code = preflight(paths, cwd=tmp, out=lines.append, **kw)
        return code, "\n".join(lines)

    def check(name, ok, detail=""):
        results.append(ok)
        out(("PASS " if ok else "FAIL ") + name + ("" if ok else f"\n  {detail}"))

    try:
        # dirty and behind blocks and is not pulled; clean and current passes
        d = repo("dirty")
        push_ahead("dirty")
        sh("echo local >> f", cwd=d)
        before = head(d)
        code, log = run([d], pull=True, section={})
        check("dirty and behind blocks, exit 1", code == BLOCKED, log)
        check("dirty and behind is not pulled", head(d) == before, log)
        c = repo("current")
        code, log = run([c], pull=True, section={})
        check("clean and current is clear, exit 0", code == CLEAR, log)

        # clean and behind: reported without --pull, fast-forwarded with it
        b = repo("behind")
        push_ahead("behind")
        before = head(b)
        code, log = run([b], section={})
        check("clean and behind is reported without --pull", code == CLEAR and "1 behind" in log and head(b) == before, log)
        code, log = run([b], pull=True, section={})
        check("clean and behind is fast-forwarded with --pull", code == CLEAR and "pulled 1" in log
              and head(b) == git(b, "rev-parse", "@{u}")[1], log)
        code, log = run([c], section={})
        check("clean and current is not reported behind", "behind" not in log, log)

        # a failing probe blocks with its fix; a passing probe is clear
        code, log = run([], section={"probes": [{"name": "tool", "run": "false", "fix": "sign in to tool"}]})
        check("failing probe blocks with its fix", code == BLOCKED and "fix: sign in to tool" in log, log)
        code, log = run([], section={"probes": [{"name": "tool", "run": "true", "fix": "sign in to tool"}]})
        check("passing probe is clear", code == CLEAR and "signed in" in log, log)

        # a missing path exits 2; an existing one does not
        code, log = run([os.path.join(tmp, "nowhere")], section={})
        check("missing path exits 2", code == CANT, log)
        code, log = run([c], section={})
        check("existing path does not exit 2", code != CANT, log)

        # paths given replace the config list; with no paths, the list is checked
        code, log = run([c], section={"repos": [os.path.join(tmp, "nowhere")]})
        check("paths given replace the config list", code == CLEAR and "nowhere" not in log, log)
        code, log = run([], section={"repos": [os.path.join(tmp, "nowhere")]})
        check("with no paths, the config list is checked", code == CANT and "nowhere" in log, log)

        # a feature branch tracking main: main's moves are reported, not blocking
        f = repo("feature")
        sh("git checkout -q -b feat --track origin/main && echo w > g && git add g && git commit -qm w && echo wip >> f", cwd=f)
        push_ahead("feature")
        code, log = run([f], section={})
        check("a dirty feature branch tracking main is not blocked when main moves",
              code == CLEAR and "origin/main has moved 1" in log, log)
        sh("git push -q origin feat", cwd=f)
        push_ahead("feature", branch="feat", path="h")
        code, log = run([f], section={})
        check("a dirty feature branch behind its own remote branch blocks", code == BLOCKED and "origin/feat" in log, log)

        # diverged from its own remote branch blocks; a branch only ahead does not
        v = repo("diverged")
        push_ahead("diverged")
        sh("echo z >> f && git commit -qam z", cwd=v)
        code, log = run([v], pull=True, section={})
        check("diverged from its own remote branch blocks", code == BLOCKED and "rebase or merge" in log, log)
        a = repo("ahead")
        sh("echo z >> f && git commit -qam z", cwd=a)
        code, log = run([a], section={})
        check("only ahead is clear", code == CLEAR and "1 ahead" in log, log)

        # an untracked file that stops a fast-forward shows git's reason
        u = repo("untracked")
        push_ahead("untracked", path="new")
        sh("echo mine > new", cwd=u)
        code, log = run([u], pull=True, section={})
        check("a blocked fast-forward shows git's reason", code == BLOCKED and "overwritten" in log, log)
        os.remove(os.path.join(u, "new"))
        code, log = run([u], pull=True, section={})
        check("without the untracked file the fast-forward runs", code == CLEAR and "pulled 1" in log, log)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    out(f"{sum(results)}/{len(results)} controls passed")
    return CLEAR if results and all(results) else BLOCKED


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    unknown = flags - {"--pull", "--no-config", "--controls", "--help"}
    if "--help" in flags or unknown:
        print(__doc__)
        return CANT if unknown else CLEAR
    if "--controls" in flags:
        return controls()
    try:
        section = {} if "--no-config" in flags else load_section()
    except (OSError, ValueError) as e:
        print(f"✗ board config {CONFIG_PATH}: {e}")
        return CANT
    return preflight(args, pull="--pull" in flags, section=section)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
