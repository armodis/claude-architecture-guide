#!/usr/bin/env python3
"""provision.py — put GitHub in place for the operating model: organizations, repos, project
boards and the `board` config.

  ./provision.py [github.json]          rehearse: report what exists and what would be created
  ./provision.py [github.json] --live   create what's missing, then report again

Reads github.json (copy github.example.json and edit it). For each owner it:

  1. checks the organization exists (GitHub has no API to create one: the report links the page);
  2. creates each missing repo, private by default, with the guide's layout committed in a local
     clone at <path> (README.md, AGENTS.md, STATUS.md, design/, docs/decisions/, .gitignore, and
     backend/, frontend/, scripts/ for a product repo), and the `test-fixture` label;
  3. copies each missing board from its template, links its repos, and sets its Themes;
  4. checks each board's built-in workflows are enabled (GitHub has no API to enable them:
     the report links each board's Workflows page);
  5. adds each board to the `board` config ($BOARD_CONFIG or ~/.config/board/boards.json),
     keeping boards already there.

Re-runnable: it finds what exists by name and only creates what's missing. Needs `gh`, logged in
with the `repo`, `project` and `read:org` scopes.

Exit codes: 0 everything in place; 1 an error; 2 steps remain (rehearsal, or something only the
web UI can do).
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS = ["Item closed", "Item reopened", "Pull request linked to issue", "Pull request merged",
             "Auto-close issue", "Item added to project", "Auto-add sub-issues to project", "Auto-add to project"]
CONFIG_PATH = os.environ.get("BOARD_CONFIG") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "board", "boards.json")
FIXTURE_LABEL = ("test-fixture", "ededed", "Standing test issues for the board command")


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
        r = self.run(["api", path], check=False)
        return json.loads(r.stdout) if r.returncode == 0 else None

    def git(self, args, cwd):
        r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
        if r.returncode:
            raise ProvisionError(f"git {' '.join(args[:2])}: {r.stderr.strip()}")


OWNER_Q = """query($l:String!){repositoryOwner(login:$l){__typename id login
  ... on Organization{projectsV2(first:100){nodes{id number title url closed}}}
  ... on User{projectsV2(first:100){nodes{id number title url closed}}}}}"""
TEMPLATE_Q = """query($l:String!,$n:Int!){organization(login:$l){projectV2(number:$n){id title template}}}"""
BOARD_Q = """query($p:ID!){node(id:$p){... on ProjectV2{number url
  repositories(first:50){nodes{nameWithOwner}}
  workflows(first:20){nodes{name enabled}}
  fields(first:50){nodes{... on ProjectV2SingleSelectField{id name options{id name color description}}}}}}}"""
REPO_Q = """query($o:String!,$n:String!){repository(owner:$o,name:$n){id}}"""
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
    if not isinstance(cfg.get("owners"), list) or not cfg["owners"]:
        raise ProvisionError(f"{path}: needs a non-empty \"owners\" list")
    for o in cfg["owners"]:
        for k in ("login", "type"):
            if not o.get(k):
                raise ProvisionError(f"{path}: an owner is missing \"{k}\"")
        if o["type"] not in ("organization", "user"):
            raise ProvisionError(f"{path}: owner {o['login']}: type must be organization or user")
        repos = {r["name"] for r in o.get("repos", [])}
        for b in o.get("boards", []):
            for k in ("name", "title", "template"):
                if not b.get(k):
                    raise ProvisionError(f"{path}: a board of {o['login']} is missing \"{k}\"")
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
    return files


# ─── Steps ──────────────────────────────────────────────────────────────────

class Run:
    def __init__(self, gh, cfg, live, config_path=CONFIG_PATH, out=print):
        self.gh, self.cfg, self.live, self.config_path, self.out = gh, cfg, live, config_path, out
        self.todo, self.manual, self.entries = [], [], {}

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
            repo_ids[r["name"]] = self.repo(login, r)
        boards = {p["title"]: p for p in node["projectsV2"]["nodes"] if not p["closed"]}
        for b in o.get("boards", []):
            self.board(login, typ, node["id"], boards, b, repo_ids)

    def repo(self, owner, r):
        name = f"{owner}/{r['name']}"
        found = self.gh.graphql(REPO_Q, o=owner, n=r["name"])["repository"]
        if found:
            self.say("✓", f"repo {name}")
            rid = found["id"]
        else:
            self.pending(f"repo {name} ({'public' if r.get('public') else 'private'}, {r.get('kind', 'plain')} layout)")
            if not self.live:
                return None
            path = os.path.expanduser(r.get("path") or os.path.join("~", owner, r["name"]))
            if os.path.exists(path) and os.listdir(path):
                raise ProvisionError(f"{path} exists and isn't empty; set \"path\" for {name}")
            self.gh.run(["repo", "create", name, "--public" if r.get("public") else "--private",
                         "--description", r.get("description", "")])
            os.makedirs(path, exist_ok=True)
            for rel, text in scaffold(owner, r).items():
                os.makedirs(os.path.join(path, os.path.dirname(rel)), exist_ok=True)
                with open(os.path.join(path, rel), "w") as f:
                    f.write(text)
            g = self.gh.git
            g(["init", "-q", "-b", "main"], path)
            g(["add", "."], path)
            g(["commit", "-q", "-m", "chore: repo layout from the architecture guide"], path)
            g(["remote", "add", "origin", f"https://github.com/{name}.git"], path)
            g(["push", "-q", "-u", "origin", "main"], path)
            rid = self.gh.graphql(REPO_Q, o=owner, n=r["name"])["repository"]["id"]
            self.say("✓", f"repo {name} created, layout pushed from {path}")
        label = FIXTURE_LABEL[0]
        if self.gh.rest(f"repos/{name}/labels/{label}") is None:
            self.pending(f"label {label} on {name}")
            if self.live:
                self.gh.run(["label", "create", label, "--repo", name, "--color", FIXTURE_LABEL[1],
                             "--description", FIXTURE_LABEL[2]])
        return rid

    def board(self, owner, typ, owner_id, boards, b, repo_ids):
        p = boards.get(b["title"])
        if not p:
            t = b["template"]
            self.pending(f"board \"{b['title']}\" from template {t['owner']} #{t['number']}")
            if not self.live:
                return
            src = self.gh.graphql(TEMPLATE_Q, l=t["owner"], n=t["number"])["organization"]["projectV2"]
            if not src:
                raise ProvisionError(f"template {t['owner']} #{t['number']} not found")
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
        self.entries[b["name"]] = {"owner": owner, "owner_type": typ, "number": d["number"],
                                   "hierarchy": levels, "outside_hierarchy": [],
                                   **({"read_only": True} if b.get("read_only") else {})}

    def themes(self, d, field, themes):
        if not field:
            raise ProvisionError(f"board #{d['number']} has no Theme field")
        have = [o["name"] for o in field["options"]]
        new = [t for t in themes if t not in have]
        if not new:
            return
        self.pending(f"Themes on board #{d['number']}: {', '.join(new)}")
        if self.live:
            keep = [{k: o[k] for k in ("id", "name", "color", "description")} for o in field["options"]]
            self.gh.graphql(OPTIONS_M, f=field["id"],
                            o=keep + [{"name": t, "color": "GRAY", "description": ""} for t in new])

    def write_config(self):
        try:
            cur = read_json(self.config_path)
        except OSError:
            cur = read_json(os.path.join(HERE, "template", "board", ".config", "board", "boards.example.json"))
            cur["boards"] = {}
        except ValueError as e:
            raise ProvisionError(f"{self.config_path}: not valid JSON ({e})")
        add = {k: v for k, v in self.entries.items() if k not in cur.get("boards", {})}
        if not add:
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
        if self.manual:
            self.out(f"{len(self.manual)} step(s) need the web UI (marked !); run this again after them.")
        if not self.todo and not self.manual:
            self.out("Everything is in place.")
        return 2 if (self.manual or (self.todo and not self.live)) else 0


def main(argv):
    live = "--live" in argv
    args = [a for a in argv if a != "--live"]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    path = args[0] if args else os.path.join(HERE, "github.json")
    try:
        cfg = load(path)
        print(("Applying " if live else "Rehearsing ") + path)
        code = Run(GH(), cfg, live).go()
        if live and code == 0:
            return 0
        return code
    except ProvisionError as e:
        print(f"provision: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
