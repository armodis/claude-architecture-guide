#!/usr/bin/env python3
"""provision.py — put GitHub in place for the operating model: organizations, repos, project
boards and the `board` config.

  ./provision.py [github.json]          rehearse: report what exists and what would be created
  ./provision.py [github.json] --live   create what's missing, then report again

Reads github.json (copy github.example.json and edit it). For each owner it:

  1. checks the organization exists (GitHub has no API to create one: the report links the page);
  2. creates each missing repo, private by default, from the guide's layout committed first in a
     local clone at <path> (README.md, AGENTS.md, STATUS.md, design/, docs/decisions/, .gitignore,
     the board workflow in .github/workflows/, and backend/, frontend/, scripts/ for a product
     repo), then pushed by `gh repo create --source --push`; and adds the test-fixture label;
  3. copies each missing board from its template, links its repos, and sets its Themes;
  4. checks each board's built-in workflows are enabled (GitHub has no API to enable them:
     the report links each board's Workflows page);
  5. adds each board to the `board` config ($BOARD_CONFIG or ~/.config/board/boards.json), with
     its repos and release setting, keeping boards already there; an existing entry that points
     at a different project is reported.

Re-runnable: it finds what exists by name and only creates what's missing. A --live run ends
with a fresh rehearsal, so the report reads back what landed. Needs `gh`, logged in with the
`repo`, `project`, `read:org` and `workflow` scopes, `git` with user.name and user.email set, and python3.

Exit codes: 0 everything in place; 1 an error; 2 steps remain (rehearsal, or something only the
web UI can do).
"""
import json, os, subprocess, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS = ["Item closed", "Item reopened", "Pull request linked to issue", "Pull request merged",
             "Auto-close issue", "Item added to project", "Auto-add sub-issues to project", "Auto-add to project"]
CONFIG_PATH = os.environ.get("BOARD_CONFIG") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "board", "boards.json")
FIXTURE_LABEL = ("test-fixture", "ededed", "Standing test issues for the board command")
EXAMPLE_BOARDS = os.path.join(HERE, "template", "board", ".config", "board", "boards.example.json")
WORKFLOW = os.path.join(HERE, "template", "repo", ".github", "workflows", "board.yml")
THEME_COLORS = ["BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PINK", "PURPLE", "GRAY"]


class ProvisionError(Exception):
    pass


def read_json(path):
    with open(path) as f:
        return json.load(f)


class GH:
    """Thin wrapper over `gh`. Tests replace it with a fake."""

    def run(self, args, input=None, cwd=None, check=True):
        r = subprocess.run(["gh", *args], input=input, capture_output=True, text=True, cwd=cwd)
        if check and r.returncode:
            raise ProvisionError(f"gh {' '.join(args[:3])}: {r.stderr.strip() or r.stdout.strip()}")
        return r

    def graphql(self, query, **variables):
        out = json.loads(self.run(["api", "graphql", "--input", "-"],
                                  input=json.dumps({"query": query, "variables": variables})).stdout or "{}")
        if out.get("errors"):
            raise ProvisionError(f"GitHub: {out['errors'][0].get('message')}")
        return out["data"]

    def rest(self, path):
        """GET a REST path; None on 404, ProvisionError on any other failure."""
        r = self.run(["api", path], check=False)
        if r.returncode == 0:
            return json.loads(r.stdout)
        if "404" in r.stderr or "Not Found" in r.stderr:
            return None
        raise ProvisionError(f"gh api {path}: {r.stderr.strip()}")

    def is_empty(self, name):
        """Whether a repo has no commits: GitHub answers 409 for its commit list."""
        r = self.run(["api", f"repos/{name}/commits?per_page=1"], check=False)
        return r.returncode != 0 and ("409" in r.stderr or "empty" in r.stderr.lower())

    def scopes(self):
        """The token's OAuth scopes, or None when GitHub doesn't report them (fine-grained tokens)."""
        r = self.run(["api", "-i", "user"], check=False)
        for line in r.stdout.splitlines():
            if line.lower().startswith("x-oauth-scopes:"):
                return {x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()}
        return None

    def git_identity(self):
        r = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True)
        return r.stdout.strip()

    def git(self, args, cwd):
        r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
        if r.returncode:
            raise ProvisionError(f"git {' '.join(args[:2])}: {r.stderr.strip()}")


OWNER_Q = """query($l:String!){repositoryOwner(login:$l){__typename id login}}"""
BOARDS_Q = """query($l:String!,$t:String!,$a:String){repositoryOwner(login:$l){
  ... on Organization{projectsV2(first:100, query:$t, after:$a){pageInfo{hasNextPage endCursor} nodes{id number title url closed}}}
  ... on User{projectsV2(first:100, query:$t, after:$a){pageInfo{hasNextPage endCursor} nodes{id number title url closed}}}}}"""
TEMPLATE_Q = """query($l:String!,$n:Int!){organization(login:$l){projectV2(number:$n){id title template}}}"""
BOARD_Q = """query($p:ID!){node(id:$p){... on ProjectV2{number url
  repositories(first:50){nodes{nameWithOwner}}
  workflows(first:20){nodes{name enabled}}
  fields(first:50){nodes{... on ProjectV2SingleSelectField{id name options{id name color description}}}}}}}"""
COPY_M = """mutation($p:ID!,$o:ID!,$t:String!){copyProjectV2(input:{projectId:$p,ownerId:$o,title:$t,includeDraftIssues:false}){projectV2{id number url}}}"""
LINK_M = """mutation($p:ID!,$r:ID!){linkProjectV2ToRepository(input:{projectId:$p,repositoryId:$r}){repository{id}}}"""
OPTIONS_M = """mutation($f:ID!,$o:[ProjectV2SingleSelectFieldOptionInput!]){updateProjectV2Field(input:{fieldId:$f,singleSelectOptions:$o}){projectV2Field{... on ProjectV2SingleSelectField{id}}}}"""


def load(path):
    try:
        cfg = read_json(path)
    except OSError:
        raise ProvisionError(f"no config at {path}: copy github.example.json to github.json and edit it")
    except ValueError as e:
        raise ProvisionError(f"{path}: not valid JSON ({e})")
    if not isinstance(cfg, dict) or not isinstance(cfg.get("owners"), list) or not cfg["owners"]:
        raise ProvisionError(f"{path}: needs an object with a non-empty \"owners\" list")
    names = set()
    for o in cfg["owners"]:
        if not isinstance(o, dict):
            raise ProvisionError(f"{path}: each owner is an object")
        for k in ("login", "type"):
            if not o.get(k):
                raise ProvisionError(f"{path}: an owner is missing \"{k}\"")
        if o["type"] not in ("organization", "user"):
            raise ProvisionError(f"{path}: owner {o['login']}: type must be organization or user")
        for r in o.get("repos", []):
            if not isinstance(r, dict) or not r.get("name"):
                raise ProvisionError(f"{path}: a repo of {o['login']} is missing \"name\"")
            if "automation" in r and not isinstance(r["automation"], bool):
                raise ProvisionError(f"{path}: repo {r['name']}: automation must be true or false")
            if r.get("release", "none") not in ("none", "tags"):
                raise ProvisionError(f"{path}: repo {r['name']}: release must be none or tags")
        repos = {r["name"] for r in o.get("repos", [])}
        for b in o.get("boards", []):
            if not isinstance(b, dict):
                raise ProvisionError(f"{path}: each board of {o['login']} is an object")
            for k in ("name", "title", "template"):
                if not b.get(k):
                    raise ProvisionError(f"{path}: a board of {o['login']} is missing \"{k}\"")
            t = b["template"]
            if not isinstance(t, dict) or not t.get("owner") or not isinstance(t.get("number"), int):
                raise ProvisionError(f"{path}: board {b['name']}: template needs an organization \"owner\" and a \"number\" "
                                     "(Projects templates live in organizations)")
            if b["name"] in names:
                raise ProvisionError(f"{path}: two boards are named {b['name']!r}; board names must be unique")
            names.add(b["name"])
            missing = [r for r in b.get("repos", []) if r not in repos]
            if missing:
                raise ProvisionError(f"{path}: board {b['name']} links repos not listed under {o['login']}: {missing}")
    return cfg


# ─── Repo scaffold ──────────────────────────────────────────────────────────

def scaffold(owner, repo):
    """The files a new repo starts with, as {path: text}. Empty folders carry a .gitkeep."""
    name, kind, desc = repo["name"], repo.get("kind", "plain"), repo.get("description", "")
    layout = ["| [`design/`](design/) | One folder per design-loop run (`<YYYY-MM-DD-slug>/`); `scratch/` inside each is gitignored |",
              "| [`docs/`](docs/) | Durable docs for readers |",
              "| [`docs/decisions/`](docs/decisions/) | ADRs, append-only |"]
    files = {"design/.gitkeep": "", "docs/decisions/.gitkeep": ""}
    ignore = ["design/*/scratch/", ".scratch/", "__pycache__/"]
    if kind == "product":
        layout += ["| [`backend/`](backend/) | Server, API and data model, with its tests |",
                   "| [`frontend/`](frontend/) | Web app, with its tests |",
                   "| [`scripts/`](scripts/) | Developer and operations scripts |"]
        files.update({"backend/.gitkeep": "", "frontend/.gitkeep": "", "scripts/.gitkeep": "",
                      ".env.example": "# Settings the app reads. Copy to .env, which stays out of git.\n"})
        ignore.append(".env")
    files["README.md"] = (f"# {name}\n\n{desc or 'One sentence on what this repo is for.'}\n\n## Layout\n\n"
                          "| Path | Contents |\n|---|---|\n" + "\n".join(layout) +
                          "\n\n## See also\n\n- [AGENTS.md](AGENTS.md) — agent conventions\n- [STATUS.md](STATUS.md) — current state\n")
    files["AGENTS.md"] = (f"# {name} — agent conventions\n\n"
                          "- Read [STATUS.md](STATUS.md) first; update it before leaving.\n"
                          "- Design complex work with `/design-loop`: one folder per run under `design/<YYYY-MM-DD-slug>/`.\n"
                          "- Read and change the project board with `board` and the `item` and `pickup` skills.\n"
                          "- Implementation goes on a feature branch and lands by pull request with `closes #N`.\n"
                          "- Commit prefixes: `analysis:`, `plan:`, `impl:`, `status:`, plus `feat:` / `fix:` / `docs:` / `chore:`.\n")
    files["STATUS.md"] = (f"# STATUS — {name}\n\n## What just happened\n\n- Repo created with the guide's layout.\n\n"
                          "## What's in progress\n\n(none)\n\n## What's next\n\n- File the first issues on the board.\n\n"
                          "## Where to find things\n\n- Layout → [README.md](README.md)\n- Conventions → [AGENTS.md](AGENTS.md)\n")
    files[".gitignore"] = "\n".join(ignore) + "\n"
    if os.path.exists(WORKFLOW):
        with open(WORKFLOW) as f:
            files[".github/workflows/board.yml"] = f.read()
    return files


# ─── Steps ──────────────────────────────────────────────────────────────────

class Run:
    def __init__(self, gh, cfg, live, config_path=CONFIG_PATH, out=print):
        self.gh, self.cfg, self.live, self.config_path, self.out = gh, cfg, live, config_path, out
        self.todo, self.manual, self.entries = [], [], {}
        try:
            self.defaults = read_json(config_path).get("defaults", {})
        except (OSError, ValueError):
            self.defaults = {}
        self.fixture_label = (self.defaults.get("fixture") or {}).get("label") or FIXTURE_LABEL[0]

    def say(self, mark, text):
        self.out(f"  {mark} {text}")

    def pending(self, text):
        self.todo.append(text)
        self.say("+" if self.live else "·", ("creating " if self.live else "would create ") + text)

    def by_hand(self, text):
        self.manual.append(text)
        self.say("!", text)

    def owner(self, o):
        login, typ = o["login"], o["type"]
        self.out(f"\n== {login} ({typ}) ==")
        node = self.gh.graphql(OWNER_Q, l=login)["repositoryOwner"]
        if not node:
            if typ == "organization":
                self.by_hand(f"create the organization {login} at https://github.com/account/organizations/new, then run this again")
            else:
                raise ProvisionError(f"user {login} not found")
            return
        want = "Organization" if typ == "organization" else "User"
        if node["__typename"] != want:
            raise ProvisionError(f"{login} is a {node['__typename'].lower()}, not a {typ}")
        self.say("✓", f"{typ} {login}")
        repo_ids = {}
        for r in o.get("repos", []):
            repo_ids[r["name"]] = self.repo(login, r, typ)
        release = {r["name"]: r.get("release", "none") for r in o.get("repos", [])}
        for b in o.get("boards", []):
            found, after = [], None
            while True:  # GitHub's search matches words loosely; page through and keep exact titles
                page = self.gh.graphql(BOARDS_Q, l=login, t=b["title"], a=after)["repositoryOwner"]["projectsV2"]
                found += page["nodes"]
                if not (page.get("pageInfo") or {}).get("hasNextPage"):
                    break
                after = page["pageInfo"]["endCursor"]
            boards = {p["title"]: p for p in found if not p["closed"] and p["title"] == b["title"]}
            self.board(login, typ, node["id"], boards, b, repo_ids, release)

    def repo(self, owner, r, typ="organization"):
        name = f"{owner}/{r['name']}"
        found = self.gh.rest(f"repos/{name}")
        if found:
            rid = found["node_id"]
            empty = self.gh.is_empty(name)
            if empty:
                self.by_hand(f"repo {name} exists but is empty: push its layout (or delete it and run this again)")
            else:
                self.say("✓", f"repo {name}")
        else:
            path = os.path.expanduser(r.get("path") or os.path.join("~", owner, r["name"]))
            if os.path.exists(path) and (not os.path.isdir(path) or os.listdir(path)):
                raise ProvisionError(f"{path} exists and isn't an empty folder; set \"path\" for {name}")
            if not self.gh.git_identity():
                raise ProvisionError("git has no user.email; set user.name and user.email before creating repos")
            scopes = self.gh.scopes()
            if scopes is not None and "workflow" not in scopes and os.path.exists(WORKFLOW):
                raise ProvisionError("the gh token lacks the workflow scope, which pushing .github/workflows/ needs: "
                                     "gh auth refresh -s workflow")
            self.pending(f"repo {name} ({'public' if r.get('public') else 'private'}, {r.get('kind', 'plain')} layout, at {path})")
            if not self.live:
                return None
            os.makedirs(path, exist_ok=True)
            for rel, text in scaffold(owner, r).items():
                os.makedirs(os.path.join(path, os.path.dirname(rel)), exist_ok=True)
                with open(os.path.join(path, rel), "w") as f:
                    f.write(text)
            g = self.gh.git
            g(["init", "-q", "-b", "main"], path)
            g(["add", "."], path)
            g(["commit", "-q", "-m", "chore: repo layout from the architecture guide"], path)
            self.gh.run(["repo", "create", name, "--public" if r.get("public") else "--private",
                         "--description", r.get("description", ""), "--source", path, "--remote", "origin", "--push"])
            rid = self.gh.rest(f"repos/{name}")["node_id"]
            self.say("✓", f"repo {name} created, layout pushed from {path}")
        label = self.fixture_label
        if self.gh.rest(f"repos/{name}/labels/{urllib.parse.quote(label, safe='')}") is None:
            self.pending(f"label {label} on {name}")
            if self.live:
                self.gh.run(["label", "create", label, "--repo", name, "--color", FIXTURE_LABEL[1],
                             "--description", FIXTURE_LABEL[2]])
        if found and not empty:
            self.automation(name, r, typ)
        return rid

    def automation(self, name, r, typ="organization"):
        """The board workflow keeps Status right for issues with several closing pull requests and
        moves released items to Done. It needs a token (a GitHub App's BOARD_APP_ID variable and
        BOARD_APP_KEY secret, or a BOARD_TOKEN secret) and the BOARD_CONFIG variable, at repo or
        organization level, and should pin the board command with the BOARD_REF variable. Adding
        them is the owner's to do, so they are reported, never set.
        A repo marked "automation": false in github.json is skipped."""
        if r.get("automation") is False:
            return
        if self.gh.rest(f"repos/{name}/contents/.github/workflows/board.yml") is None:
            self.by_hand(f"{name}: copy template/repo/.github/workflows/board.yml into the repo (needed for issues "
                         "with several closing pull requests, and for tag releases; or set \"automation\": false)")
            return
        try:
            have = self.actions_names(name, typ == "organization")
        except ProvisionError:
            self.by_hand(f"{name}: couldn't read its Actions secrets and variables with this token; check by hand that "
                         "it has a token (BOARD_APP_ID and BOARD_APP_KEY, or BOARD_TOKEN) and BOARD_CONFIG")
            return
        missing = []
        if not ({"var:BOARD_APP_ID", "secret:BOARD_APP_KEY"} <= have or "secret:BOARD_TOKEN" in have):
            missing.append("a token: variable BOARD_APP_ID and secret BOARD_APP_KEY (a GitHub App, for an organization "
                           "board) or secret BOARD_TOKEN (a personal access token with repo and project)")
        if "var:BOARD_CONFIG" not in have:
            missing.append("variable BOARD_CONFIG (the board config JSON)")
        if missing:
            self.by_hand(f"{name}: add {'; and '.join(missing)} in Settings > Secrets and variables > Actions; "
                         "until then the board workflow skips")
        if "var:BOARD_REF" not in have:
            self.by_hand(f"{name}: set variable BOARD_REF to the guide commit SHA to run the board command from; "
                         "without it the board workflow runs the guide's main and warns")

    def actions_names(self, name, org):
        """Secret and variable names visible to a repo's Actions: its own, and for a repo in an
        organization the organization's shared with it (GitHub rejects that lookup, 422, for a
        user's repo)."""
        out = set()
        lists = [("secret", "actions/secrets", "secrets"), ("var", "actions/variables", "variables")]
        if org:
            lists += [("secret", "actions/organization-secrets", "secrets"), ("var", "actions/organization-variables", "variables")]
        for kind, path, key in lists:
            page = 1
            while True:  # 100 is GitHub's page limit
                d = self.gh.rest(f"repos/{name}/{path}?per_page=100&page={page}") or {}
                items = d.get(key, [])
                out |= {f"{kind}:{x['name']}" for x in items}
                if len(items) < 100:
                    break
                page += 1
        return out

    def board(self, owner, typ, owner_id, boards, b, repo_ids, release=None):
        p = boards.get(b["title"])
        if not p:
            t = b["template"]
            org = self.gh.graphql(TEMPLATE_Q, l=t["owner"], n=t["number"])["organization"]
            src = (org or {}).get("projectV2")
            if not src:
                raise ProvisionError(f"board {b['name']}: template {t['owner']} #{t['number']} not found (it must be an "
                                     "organization's project you can read)")
            self.pending(f"board \"{b['title']}\" from template {t['owner']} #{t['number']}")
            if not self.live:
                return
            p = self.gh.graphql(COPY_M, p=src["id"], o=owner_id, t=b["title"])["copyProjectV2"]["projectV2"]
        d = self.gh.graphql(BOARD_Q, p=p["id"])["node"]
        self.say("✓", f"board \"{b['title']}\" #{d['number']} {d['url']}")
        linked = {x["nameWithOwner"] for x in d["repositories"]["nodes"]}
        for rn in b.get("repos", []):
            full = f"{owner}/{rn}"
            if full in linked:
                continue
            self.pending(f"link {full} to board #{d['number']}")
            if self.live and repo_ids.get(rn):
                self.gh.graphql(LINK_M, p=p["id"], r=repo_ids[rn])
        fields = {f["name"]: f for f in d["fields"]["nodes"] if f}
        if b.get("themes"):
            self.themes(d, fields.get("Theme"), b["themes"])
        off = [w["name"] for w in d["workflows"]["nodes"] if w["name"] in WORKFLOWS and not w["enabled"]]
        have = {w["name"] for w in d["workflows"]["nodes"]}
        off += [w for w in WORKFLOWS if w not in have]
        if off:
            self.by_hand(f"turn on in {d['url']}/workflows: {', '.join(off)}")
        levels = [o["name"] for o in (fields.get("Category") or {}).get("options", [])]
        repos = [f"{owner}/{rn}" for rn in b.get("repos", [])]
        tags = any((release or {}).get(rn) == "tags" for rn in b.get("repos", []))
        self.entries[b["name"]] = {"owner": owner, "owner_type": typ, "number": d["number"], "repos": repos,
                                   "release": "tags" if tags else "none", "hierarchy": levels, "outside_hierarchy": [],
                                   **({"read_only": True} if b.get("read_only") else {})}

    def themes(self, d, field, themes):
        if not field:
            raise ProvisionError(f"board #{d['number']} has no Theme field")
        have = [o["name"] for o in field["options"]]
        new = [t for t in themes if t not in have]
        drop = [o for o in field["options"] if o["name"] == "Placeholder" and "Placeholder" not in themes]
        if not new and not drop:
            return
        self.pending(f"Themes on board #{d['number']}: {', '.join(new) or '(none new)'}"
                     + ("; drop the template's Placeholder" if drop else ""))
        if self.live:
            keep = [{k: o[k] for k in ("id", "name", "color", "description")} for o in field["options"] if o not in drop]
            self.gh.graphql(OPTIONS_M, f=field["id"],
                            o=keep + [{"name": t, "color": THEME_COLORS[i % len(THEME_COLORS)], "description": ""}
                                      for i, t in enumerate(new)])

    def write_config(self):
        try:
            cur = read_json(self.config_path)
        except OSError:
            cur = read_json(EXAMPLE_BOARDS)
            cur["boards"] = {}
        except ValueError as e:
            raise ProvisionError(f"{self.config_path}: not valid JSON ({e})")
        have = cur.get("boards", {})
        for k, v in self.entries.items():
            old = have.get(k)
            if old and any(old.get(x, v[x]) != v[x] for x in ("owner", "owner_type", "number")):
                self.by_hand(f"board config entry {k!r} points at {old.get('owner')} #{old.get('number')}, not "
                             f"{v['owner']} #{v['number']}: fix or remove it in {self.config_path}")
            elif old:
                same = {"repos": lambda a, b: sorted(a) == sorted(b)}  # repo order doesn't matter; level order does
                drift = [x for x in ("repos", "release", "hierarchy")
                         if x in old and not same.get(x, lambda a, b: a == b)(old[x], v[x])]
                if "repos" not in old and v["repos"]:
                    drift.append("repos")
                if drift:
                    self.by_hand(f"board config entry {k!r} differs from GitHub in {', '.join(drift)}: set "
                                 + "; ".join(f"{x} = {json.dumps(v[x])}" for x in drift) + f" in {self.config_path}")
        add = {k: v for k, v in self.entries.items() if k not in have}
        if not add:
            if self.entries:
                self.say("✓", f"board config {self.config_path}")
            return
        self.pending(f"board config entries {', '.join(add)} in {self.config_path}")
        if self.live:
            cur.setdefault("boards", {}).update(add)
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w") as f:
                f.write(json.dumps(cur, indent=2) + "\n")

    def go(self):
        for o in self.cfg["owners"]:
            self.owner(o)
        self.out("\n== board config ==")
        self.write_config()
        self.out("")
        if self.todo and not self.live:
            self.out(f"{len(self.todo)} to create: run again with --live.")
        if self.todo and self.live:
            self.out("Reading back what landed:")
            again = Run(self.gh, self.cfg, False, self.config_path, self.out)
            return again.go()
        if self.manual:
            self.out(f"{len(self.manual)} step(s) to do by hand (marked !); run this again after them.")
        if not self.todo and not self.manual:
            self.out("Everything is in place.")
        return 2 if (self.manual or (self.todo and not self.live)) else 0


def main(argv):
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    live = "--live" in argv
    args = [a for a in argv if a != "--live"]
    bad = [a for a in args if a.startswith("-")]
    if bad or len(args) > 1:
        print(f"provision: unexpected {' '.join(bad or args[1:])}; see --help", file=sys.stderr)
        return 1
    path = args[0] if args else os.path.join(HERE, "github.json")
    try:
        cfg = load(path)
        print(("Applying " if live else "Rehearsing ") + path)
        return Run(GH(), cfg, live).go()
    except ProvisionError as e:
        print(f"provision: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"provision: {e.filename} not found (needs gh and git on PATH)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
