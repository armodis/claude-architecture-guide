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
- a rebase, merge, cherry-pick or revert stopped part-way;
- a failed sign-in probe.

A feature branch that tracks a different branch, such as one created from origin/main, is
compared with its own remote branch when one exists; the other branch's moves are reported
without blocking. --pull fast-forwards a clean checkout that is only behind its own remote
branch; nothing else is ever changed.

The config's "preflight" "probes" are cheap read commands, one per tool a run needs, each run
every time and reported pass or fail with its fix.

Exit codes: 0 all clear, 1 something blocks the run, 2 the check itself could not run (a
missing path, not a git checkout, a failed or timed-out fetch, a malformed config or a
$BOARD_CONFIG naming a missing file, nothing to check at all).

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
# A git run inside a hook or `rebase --exec` inherits these and would read another repo.
GIT_ENV_DROP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR")


class CantCheck(Exception):
    pass


def child_env():
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_DROP}
    env["GIT_TERMINAL_PROMPT"] = "0"  # an expired credential fails now instead of waiting for input
    return env


def git(path, *args, timeout=120):
    try:
        r = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=timeout,
                           env=child_env(), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise CantCheck(f"git {args[0]} timed out after {timeout}s")
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def load_section(path=None):
    """The board config's "preflight" section, checked for shape. A missing default config is an
    empty section; a $BOARD_CONFIG that names a missing file, or a malformed section, raises."""
    path = path or CONFIG_PATH
    if not os.path.exists(path):
        if os.environ.get("BOARD_CONFIG"):
            raise ValueError(f"BOARD_CONFIG names {path}, which doesn't exist")
        return {}
    with open(path) as f:
        cfg = json.load(f)
    sec = cfg.get("preflight", {}) if isinstance(cfg, dict) else None
    if not isinstance(sec, dict):
        raise ValueError('"preflight" must be an object with "repos" and "probes"')
    repos, probes = sec.get("repos", []), sec.get("probes", [])
    if not (isinstance(repos, list) and all(isinstance(r, str) for r in repos)):
        raise ValueError('"preflight" "repos" must be a list of paths')
    if not (isinstance(probes, list) and all(isinstance(q, dict) and isinstance(q.get("run"), str) for q in probes)):
        raise ValueError('"preflight" "probes" must be a list of objects, each with a "run" command')
    return sec


def toplevel(path):
    rc, out, _ = git(path, "rev-parse", "--show-toplevel")
    return out if rc == 0 else None


def counts(top, a, b):
    _, out, _ = git(top, "rev-list", "--left-right", "--count", f"{a}...{b}")
    ahead, behind = (int(x) for x in out.split())
    return ahead, behind


def describe(ahead, behind):
    """'up to date with', '2 ahead of', '1 behind', '2 ahead and 1 behind', to precede a branch name."""
    if not (ahead or behind):
        return "up to date with"
    parts = [s for s in (f"{ahead} ahead" if ahead else "", f"{behind} behind" if behind else "") if s]
    return " and ".join(parts) + (" of" if not behind else "")


def reason(err):
    """git's own reason for a failure, with the files it names, not its closing 'Aborting'."""
    lines = [l.strip() for l in err.splitlines() if l.strip() and l.strip().lower() not in ("aborting", "aborting.")]
    lines = [l for l in lines if not l.lower().startswith("please move or remove")]
    return " ".join(lines[:4]) if lines else "pull by hand"


def in_progress(top):
    """A rebase, merge, cherry-pick or revert stopped part-way, or None."""
    _, gitdir, _ = git(top, "rev-parse", "--git-dir")
    gitdir = os.path.join(top, gitdir)
    for marker, what in (("rebase-merge", "rebase"), ("rebase-apply", "rebase"), ("MERGE_HEAD", "merge"),
                         ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert")):
        if os.path.exists(os.path.join(gitdir, marker)):
            return what
    return None


def own_remote_branch(top, branch, upstream):
    """The branch's own remote branch: the upstream when it has the same name, else <remote>/<branch>
    on the upstream's remote, then on origin, then on any remote."""
    if upstream and upstream.endswith("/" + branch):
        return upstream
    _, remotes, _ = git(top, "remote")
    remotes = remotes.split()
    first = [r for r in remotes if upstream and upstream.startswith(r + "/")]
    for r in first + (["origin"] if "origin" in remotes else []) + remotes:
        if git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/{r}/{branch}")[0] == 0:
            return f"{r}/{branch}"
    return None


def check_repo(path, pull=False, fetch=True, label=None):
    """Returns (code, line, fix). code: CLEAR, BLOCKED or CANT."""
    name = label or os.path.basename(os.path.normpath(path)) or path
    if not os.path.isdir(path):
        return CANT, f"{name}: no such folder {path}", "check the path in the run or the config"
    try:
        top = toplevel(path)
        if not top:
            return CANT, f"{name}: {path} is not a git checkout", "check the path"
        if fetch:
            rc, _, err = git(top, "fetch", "--all", "--quiet")
            if rc:
                return CANT, f"{name}: fetch failed: {reason(err)}", "check the network and the remote's sign-in"
        _, status, _ = git(top, "status", "--porcelain")
        changed = [l for l in status.splitlines() if not l.startswith("??")]
        untracked = len(status.splitlines()) - len(changed)
        state = f"{len(changed)} changed" if changed else "clean"
        if untracked:
            state += f", {untracked} untracked"
        stopped = in_progress(top)
        if stopped:
            return BLOCKED, f"{name}: a {stopped} is stopped part-way, {state}", f"finish or abort the {stopped} in {top}"
        _, branch, _ = git(top, "symbolic-ref", "--quiet", "--short", "HEAD")
        if not branch:
            return CLEAR, f"{name}: detached HEAD, {state}", None
        rc, upstream, _ = git(top, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        upstream = upstream if rc == 0 else None
        own = own_remote_branch(top, branch, upstream)
        notes = []
        if upstream and own != upstream:  # tracks another branch, such as main: report its moves, never block on them
            _, moved = counts(top, "HEAD", upstream)
            if moved:
                notes.append(f"{upstream} has moved {moved}")
        tail = "".join(f"; {n}" for n in notes)
        if own is None:
            return CLEAR, f"{name}: {branch}, {state}, " + ("not pushed yet" if upstream else "no upstream") + tail, None
        ahead, behind = counts(top, "HEAD", own)
        head = f"{name}: {branch}, {state}, {describe(ahead, behind)} {own}" + tail
        if ahead and behind:
            return BLOCKED, f"{head} (diverged)", (f"rebase or merge {own} in {top}, then rerun; "
                                                   "if you rebased this branch on purpose, push it first")
        if behind and changed:
            return BLOCKED, head, f"commit or stash the changes in {top}, then pull"
        if behind and pull:
            rc, _, err = git(top, "merge", "--ff-only", "--quiet", own)
            if rc:
                return BLOCKED, f"{head}; fast-forward failed", reason(err)
            return CLEAR, f"{name}: {branch}, {state}, pulled {behind} from {own}" + tail, None
        if behind:
            return CLEAR, f"{head} (--pull fast-forwards it)", None
        return CLEAR, head, None
    except CantCheck as e:
        return CANT, f"{name}: {e}", "check the network and rerun"


def run_probe(p):
    """Returns (code, line, fix)."""
    try:
        r = subprocess.run(p["run"], shell=True, capture_output=True, text=True, timeout=60,
                           env=child_env(), stdin=subprocess.DEVNULL)
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
    name = p.get("name") or p["run"]
    return (CLEAR, f"{name}: signed in", None) if ok else (BLOCKED, f"{name}: probe failed ({p['run']})", p.get("fix") or "sign in again")


def targets_for(paths, section, cwd=None):
    """The current repo, plus the paths given; with no paths, the config's list instead. A path
    inside a repo counts as that repo."""
    here = toplevel(cwd or os.getcwd())
    out, seen = [], set()
    for p in ([here] if here else []) + list(paths or section.get("repos", [])):
        full = os.path.realpath(os.path.expanduser(p))
        key = (toplevel(full) if os.path.isdir(full) else None) or full
        if key not in seen:
            seen.add(key)
            out.append(full)
    return out


def labels_for(targets):
    """Folder names, widened to their parent where two share a name."""
    names = [os.path.basename(t) for t in targets]
    return [os.path.join(os.path.basename(os.path.dirname(t)), n) if names.count(n) > 1 else n
            for t, n in zip(targets, names)]


def preflight(paths, pull=False, section=None, cwd=None, fetch=True, out=print):
    section = {} if section is None else section
    targets, probes = targets_for(paths, section, cwd), section.get("probes", [])
    if not (targets or probes):
        out("✗ nothing to check: no current repo, no paths given, and no repos or probes in the config\n"
            "    fix: run it inside a repo, name the paths, or add a \"preflight\" section to the board config")
        out("preflight: could not check everything; fix the lines marked ✗")
        return CANT
    worst = CLEAR
    for p, label in zip(targets, labels_for(targets)):
        code, line, fix = check_repo(p, pull=pull, fetch=fetch, label=label)
        out(("✓ " if code == CLEAR else "✗ ") + line + (f"\n    fix: {fix}" if fix else ""))
        worst = max(worst, code)
    for probe in probes:
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
    # Hermetic: no user git config, and no repo found above the temp folder, so the controls
    # never fetch or fast-forward a real checkout that happens to contain it.
    env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(tmp)
    saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CEILING_DIRECTORIES")}
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    os.environ["GIT_CEILING_DIRECTORIES"] = os.path.dirname(tmp)
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

        # nothing to check exits 2; a probe alone is something to check
        code, log = run([], section={})
        check("nothing to check exits 2 (and the controls see no repo above their temp folder)",
              code == CANT and "nothing to check" in log, log)
        code, log = run([], section={"probes": [{"run": "true"}]})
        check("a probe alone is something to check", code == CLEAR, log)

        # a fetch that fails exits 2; a reachable remote does not
        x = repo("unreachable")
        sh(f"git remote set-url origin {os.path.join(tmp, 'gone.git')}", cwd=x)
        code, log = run([x], section={})
        check("a failed fetch exits 2", code == CANT and "fetch failed" in log, log)
        code, log = run([c], section={})
        check("a reachable remote fetches", code == CLEAR, log)

        # a merge stopped part-way blocks; once aborted, it is no longer reported
        m = repo("stopped")
        push_ahead("stopped")
        sh("echo mine >> f && git commit -qam mine && git fetch -q && (git merge -q origin/main || true)", cwd=m)
        code, log = run([m], section={})
        check("a merge stopped part-way blocks", code == BLOCKED and "merge is stopped part-way" in log, log)
        sh("git merge --abort", cwd=m)
        code, log = run([m], section={})
        check("an aborted merge is no longer reported", "stopped part-way" not in log, log)

        # a branch name with a slash finds its own remote branch
        s = repo("slash")
        sh("git checkout -q -b feat/x && git push -q -u origin feat/x", cwd=s)
        push_ahead("slash", branch="feat/x", path="k")
        sh("echo wip >> f", cwd=s)
        code, log = run([s], section={})
        check("a slash branch behind its own remote branch, dirty, blocks", code == BLOCKED and "origin/feat/x" in log, log)
        sh("git checkout -q -- f", cwd=s)
        code, log = run([s], pull=True, section={})
        check("the same branch, clean, is fast-forwarded", code == CLEAR and "pulled 1 from origin/feat/x" in log, log)
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
