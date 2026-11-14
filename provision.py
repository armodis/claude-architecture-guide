#!/usr/bin/env python3
"""provision.py — put GitHub in place for the operating model: organizations, repos, project
boards, the board workflow's variables and the `board` config.

  ./provision.py                        rehearse every hub the person layer lists
  ./provision.py [github.json]          rehearse from a github.json instead
  ./provision.py [github.json] --live   create what's missing (and set variables), then report again
  ./provision.py config [--out PATH]    write boards.json from the person layer and its hubs
  ./provision.py config --check         compare that with the existing boards.json; exit 1 if it differs

Inputs:

  - The person layer, ~/.config/task-mgmt/person.json ($TASK_MGMT_PERSON overrides the path; copy
    person.example.json): {"operator", "agents", "hubs": [hub folders], "defaults": {overrides}}.
  - Each hub's <hub>/.task-mgmt/config.json (copy hub.example.json): {"version", "blocks", "owner"}.
    "owner" is an owner entry as in github.example.json; its boards also carry the board config
    keys provision can't find on GitHub: "number", "hierarchy", "outside_hierarchy", "fixture_rest",
    "parent_optional", "org_label", "xref_fields" and "read_only".
  - Or a github.json (copy github.example.json): {"owners": [owner entries]}.

`config` calls nothing on GitHub. Its defaults are the release's shipped defaults (boards.example.json),
then the person layer's "defaults" key by key, then its "agents" and "operator"; each hub board
becomes a board entry, and a board without "number" is an error (run provision to find it).

For each owner, provision:

  1. checks the organization exists (GitHub has no API to create one: the report links the page);
  2. creates each missing repo, private by default, from task-mgmt's repo layout committed first in a
     local clone at <path> (README.md, AGENTS.md, STATUS.md, design/, docs/decisions/, .gitignore,
     the board workflow in .github/workflows/, and backend/, frontend/, scripts/ for a product
     repo), then pushed by `gh repo create --source --push`; and adds the test-fixture label;
  3. checks each repo with the board workflow has a token (reported, never set) and, from hubs,
     the BOARD_CONFIG variable (the generated defaults plus the boards that list the repo) and
     BOARD_REF (the commit SHA of the hub's "version" tag in armodis-ai/task-mgmt, or the sha= in
     .task-mgmt-release beside this script): a rehearsal compares their contents, --live sets them;
     from a github.json it checks only that they exist;
  4. copies each missing board from its template, links its repos, and sets its Themes; a hub
     board's "number" is checked against the board GitHub finds;
  5. checks each board's built-in workflows are enabled (GitHub has no API to enable them:
     the report links each board's Workflows page), except on read-only boards;
  6. from a github.json, adds each board to the `board` config ($BOARD_CONFIG or
     ~/.config/board/boards.json), with its repos and release setting, keeping boards already
     there; an existing entry that points at a different project is reported. From hubs, it
     reports a board config that differs from what `config` would write.

Re-runnable: it finds what exists by name and only creates what's missing. A --live run ends
with a fresh rehearsal, so the report reads back what landed. Needs `gh`, logged in with the
`repo`, `project`, `read:org` and `workflow` scopes, `git` with user.name and user.email set, and python3.

Exit codes: 0 everything in place; 1 an error (or, for config --check, a difference); 2 steps
remain (rehearsal, or something only the web UI can do).
"""
import json, os, re, subprocess, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS = ["Item closed", "Item reopened", "Pull request linked to issue", "Pull request merged",
             "Auto-close issue", "Item added to project", "Auto-add sub-issues to project", "Auto-add to project"]
CONFIG_PATH = os.environ.get("BOARD_CONFIG") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "board", "boards.json")
FIXTURE_LABEL = ("test-fixture", "ededed", "Standing test issues for the board command")
EXAMPLE_BOARDS = os.path.join(HERE, "template", "board", ".config", "board", "boards.example.json")
WORKFLOW = os.path.join(HERE, "template", "repo", ".github", "workflows", "board.yml")
THEME_COLORS = ["BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PINK", "PURPLE", "GRAY"]
PRODUCT_REPO = "armodis-ai/task-mgmt"
RELEASE_FILE = os.path.join(HERE, ".task-mgmt-release")
HUB_CONFIG = os.path.join(".task-mgmt", "config.json")
# Board config keys a hub board carries because provision can't find them on GitHub, and their types.
HUB_BOARD_KEYS = {"number": int, "hierarchy": list, "outside_hierarchy": list, "fixture_rest": dict,
                  "parent_optional": list, "org_label": str, "xref_fields": list, "read_only": bool}
EXTRA_BOARD_KEYS = ("fixture_rest", "parent_optional", "org_label", "xref_fields", "read_only")


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

    def ls_remote(self, url, *refs):
        """`git ls-remote` output: one "<sha>\t<ref>" line per ref found."""
        r = subprocess.run(["git", "ls-remote", url, *refs], capture_output=True, text=True)
        if r.returncode:
            raise ProvisionError(f"git ls-remote {url}: {r.stderr.strip()}")
        return r.stdout


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
FIELD_M = """mutation($p:ID!,$n:String!,$o:[ProjectV2SingleSelectFieldOptionInput!]){createProjectV2Field(input:{projectId:$p,
  dataType:SINGLE_SELECT,name:$n,singleSelectOptions:$o}){projectV2Field{... on ProjectV2FieldCommon{id}}}}"""
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
        check_owner(o, path, names)
    return cfg


def check_owner(o, path, names):
    """Validate one owner entry; `names` collects board names, which are unique across owners."""
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
        for k, typ in HUB_BOARD_KEYS.items():
            if k in b and (not isinstance(b[k], typ) or (typ is int and isinstance(b[k], bool))):
                raise ProvisionError(f"{path}: board {b['name']}: {k} must be {TYPE_NAMES[typ]}")
        if b["name"] in names:
            raise ProvisionError(f"{path}: two boards are named {b['name']!r}; board names must be unique")
        names.add(b["name"])
        missing = [r for r in b.get("repos", []) if r not in repos]
        if missing:
            raise ProvisionError(f"{path}: board {b['name']} links repos not listed under {o['login']}: {missing}")


TYPE_NAMES = {int: "a number", list: "a list", dict: "an object", str: "a string", bool: "true or false"}


def person_path():
    return os.environ.get("TASK_MGMT_PERSON") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "task-mgmt", "person.json")


def load_person(path=None):
    """The person layer: who operates, which agents work, which hubs to read, and default overrides."""
    path = path or person_path()
    try:
        p = read_json(path)
    except OSError:
        raise ProvisionError(f"no person layer at {path}: copy person.example.json there (or set TASK_MGMT_PERSON), "
                             "or pass a github.json")
    except ValueError as e:
        raise ProvisionError(f"{path}: not valid JSON ({e})")
    if not isinstance(p, dict):
        raise ProvisionError(f"{path}: needs an object with \"hubs\"")
    hubs = p.get("hubs")
    if not isinstance(hubs, list) or not hubs or not all(isinstance(h, str) and h for h in hubs):
        raise ProvisionError(f"{path}: \"hubs\" must be a non-empty list of hub folders")
    agents = p.get("agents", [])
    if not isinstance(agents, list) or not all(isinstance(a, str) and a for a in agents):
        raise ProvisionError(f"{path}: \"agents\" must be a list of names")
    op = p.get("operator")
    if op is not None and not (isinstance(op, str) and op or isinstance(op, dict) and (op.get("name") or op.get("login"))):
        raise ProvisionError(f"{path}: \"operator\" must be a name or an object with \"name\" and \"login\"")
    if not isinstance(p.get("defaults", {}), dict):
        raise ProvisionError(f"{path}: \"defaults\" must be an object")
    return dict(p, hubs=[os.path.expanduser(h) for h in hubs], path=path)


def load_hub(folder, names):
    """A hub's .task-mgmt/config.json, with its path."""
    path = os.path.join(folder, HUB_CONFIG)
    try:
        h = read_json(path)
    except OSError:
        raise ProvisionError(f"no hub config at {path}: copy hub.example.json there and edit it, "
                             "or remove the hub from the person layer")
    except ValueError as e:
        raise ProvisionError(f"{path}: not valid JSON ({e})")
    if not isinstance(h, dict) or not isinstance(h.get("owner"), dict):
        raise ProvisionError(f"{path}: needs an object with an \"owner\" entry")
    if "version" in h and not (isinstance(h["version"], str) and h["version"]):
        raise ProvisionError(f"{path}: \"version\" must be a release tag such as v1.2.3")
    if not isinstance(h.get("blocks", []), list):
        raise ProvisionError(f"{path}: \"blocks\" must be a list")
    check_owner(h["owner"], path, names)
    return dict(h, path=path)


def load_hubs(person):
    names, logins, hubs = set(), {}, []
    for folder in person["hubs"]:
        h = load_hub(folder, names)
        login = h["owner"]["login"]
        if login in logins:
            raise ProvisionError(f"{logins[login]} and {h['path']} both name owner {login}; one hub per owner")
        logins[login] = h["path"]
        hubs.append(h)
    return hubs


def from_person(path=None):
    """The provision input read from the person layer's hubs: one owner per hub."""
    person = load_person(path)
    hubs = load_hubs(person)
    return {"owners": [h["owner"] for h in hubs], "person": person, "hubs": hubs}


def shipped_defaults():
    return read_json(EXAMPLE_BOARDS).get("defaults", {})


def merged_defaults(person, shipped=None):
    """The release's defaults, then the person layer's overrides key by key, then its agents and operator."""
    d = json.loads(json.dumps(shipped if shipped is not None else shipped_defaults()))
    d.update(json.loads(json.dumps(person.get("defaults") or {})))
    for k in ("agents", "operator"):
        if k in person:
            d[k] = person[k]
    return d


def board_entry(owner, b):
    """The board config entry for a hub board; "number" is None when the hub doesn't give it."""
    release = {r["name"]: r.get("release", "none") for r in owner.get("repos", [])}
    e = {"owner": owner["login"], "owner_type": owner["type"], "number": b.get("number"),
         "repos": [f"{owner['login']}/{rn}" for rn in b.get("repos", [])],
         "release": "tags" if any(release.get(rn) == "tags" for rn in b.get("repos", [])) else "none",
         "hierarchy": b.get("hierarchy", []), "outside_hierarchy": b.get("outside_hierarchy", [])}
    e.update({k: b[k] for k in EXTRA_BOARD_KEYS if k in b})
    return e


def generate(person, hubs, shipped=None):
    """boards.json from the person layer, its hubs and the shipped defaults."""
    boards = {}
    for h in hubs:
        for b in h["owner"].get("boards", []):
            e = board_entry(h["owner"], b)
            if e["number"] is None:
                raise ProvisionError(f"{h['path']}: board {b['name']} has no \"number\": run ./provision.py to find it "
                                     "on GitHub, then add it there")
            boards[b["name"]] = e
    return {"defaults": merged_defaults(person, shipped), "boards": boards}


def config_diff(want, have):
    """What differs between two board configs, as readable lines; empty when equal in content."""
    if not isinstance(have, dict) or not isinstance(have.get("defaults", {}), dict) \
            or not isinstance(have.get("boards", {}), dict) \
            or not all(isinstance(b, dict) for b in have.get("boards", {}).values()):
        return ["not a board config: it needs an object whose \"defaults\" and \"boards\" are objects, "
                "with an object per board"]
    out = []
    wd, hd = want.get("defaults", {}), have.get("defaults", {}) if isinstance(have, dict) else {}
    for k in sorted(set(wd) | set(hd)):
        if wd.get(k, None) != hd.get(k, None) or (k in wd) != (k in hd):
            out.append(f"defaults.{k}: " + ("missing" if k not in hd else "not generated" if k not in wd else "differs"))
    wb, hb = want.get("boards", {}), have.get("boards", {}) if isinstance(have, dict) else {}
    for name in sorted(set(wb) | set(hb)):
        if name not in hb:
            out.append(f"board {name}: missing")
        elif name not in wb:
            out.append(f"board {name}: not in any hub")
        else:
            keys = sorted(k for k in set(wb[name]) | set(hb[name])
                          if (k in wb[name]) != (k in hb[name]) or wb[name].get(k) != hb[name].get(k))
            if keys:
                out.append(f"board {name}: {', '.join(keys)}")
    extra = sorted(k for k in (have if isinstance(have, dict) else {}) if k not in ("defaults", "boards"))
    out += [f"{k}: not generated" for k in extra]
    return out


def config_main(args, out=print, err=None):
    """`provision.py config [--out PATH] [--check]`."""
    err = err or (lambda m: print(m, file=sys.stderr))
    check, path, rest = "--check" in args, CONFIG_PATH, [a for a in args if a != "--check"]
    if rest[:1] == ["--out"] and len(rest) >= 2:
        path, rest = os.path.expanduser(rest[1]), rest[2:]
    if rest:
        err(f"provision config: unexpected {' '.join(rest)}; see --help")
        return 1
    try:
        person = load_person()
        hubs = load_hubs(person)
        want = generate(person, hubs)
    except ProvisionError as e:
        err(f"provision: {e}")
        return 1
    if check:
        try:
            have = read_json(path)
        except OSError:
            out(f"{path}: no board config there; run ./provision.py config")
            return 1
        except ValueError as e:
            out(f"{path}: not valid JSON ({e})")
            return 1
        diff = config_diff(want, have)
        if diff:
            out(f"{path} differs from the hubs' config:")
            for line in diff:
                out(f"  {line}")
            return 1
        out(f"{path} matches the hubs' config ({len(want['boards'])} boards).")
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        f.write(json.dumps(want, indent=2) + "\n")
    out(f"Wrote {path}: {len(want['boards'])} boards ({', '.join(want['boards']) or 'none'}) from {len(hubs)} hub(s).")
    return 0


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
                          "- Commit prefixes: `analysis:`, `plan:`, `impl:`, `status:`, plus `feat:` / `fix:` / `docs:` / `chore:`.\n\n"
                          "## Working with other agents\n\n"
                          "Agents from any harness share this repo's work through the board, issues, pull requests and STATUS.md.\n\n"
                          "- Set `BOARD_AGENT` to your agent name (an option of the board's Agent field), with `BOARD_MODEL` and "
                          "`BOARD_SESSION`; `board` signs your comments with them.\n"
                          "- Run `board inbox` at the start of each session and between tasks, and deal with what's waiting first.\n"
                          "- Claim with `board claim . <owner/repo#n> --status-md STATUS.md`; it sets Agent to you.\n"
                          "- Ask with `board ask . <item> <agent> review|question <text>`; answer with "
                          "`board answer . <item> [--verdict approve|changes] <text>`; hand over with "
                          "`board handoff . <item> <agent> <text> --status-md STATUS.md`; mark a reply read with `board ack . <item>`.\n"
                          "- A pull request merges after another agent's approve verdict or the operator's approval.\n"
                          "- Write agent names in bold; an @-mention notifies the GitHub user of that name.\n")
    files["STATUS.md"] = (f"# STATUS — {name}\n\n## What just happened\n\n- Repo created with task-mgmt's repo layout.\n\n"
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
        self.person, self.hubs, self.shas = cfg.get("person"), cfg.get("hubs") or [], {}
        self.hub_of = {h["owner"]["login"]: h for h in self.hubs}
        if self.person is not None:  # from hubs: the generated defaults, as `config` writes them
            self.defaults = merged_defaults(self.person)
        else:
            try:
                self.defaults = read_json(config_path).get("defaults", {})
            except (OSError, ValueError):
                self.defaults = {}
        self.fixture_label = (self.defaults.get("fixture") or {}).get("label") or FIXTURE_LABEL[0]

    def say(self, mark, text):
        self.out(f"  {mark} {text}")

    def pending(self, text, verb=("creating", "would create")):
        self.todo.append(text)
        self.say("+" if self.live else "·", f"{verb[0] if self.live else verb[1]} {text}")

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
            # a hub repo's folder already holds its own config, which is committed with the layout
            if os.path.exists(path) and (not os.path.isdir(path) or set(os.listdir(path)) - {".task-mgmt"}):
                raise ProvisionError(f"{path} exists and holds more than a .task-mgmt/ folder; set \"path\" for {name}")
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
            g(["commit", "-q", "-m", "chore: repo layout from task-mgmt"], path)
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
        organization level, and should pin the board command with the BOARD_REF variable. The token
        is the owner's to add, so it is reported, never set. From hubs, provision sets the two
        variables (variables()); from a github.json it only checks they exist.
        A repo marked "automation": false is skipped."""
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
                         "it has a token (BOARD_APP_ID and BOARD_APP_KEY, or BOARD_TOKEN), BOARD_CONFIG and BOARD_REF")
            return
        missing = []
        if not ({"var:BOARD_APP_ID", "secret:BOARD_APP_KEY"} <= have or "secret:BOARD_TOKEN" in have):
            missing.append("a token: variable BOARD_APP_ID and secret BOARD_APP_KEY (a GitHub App, for an organization "
                           "board) or secret BOARD_TOKEN (a personal access token with repo and project)")
        if self.person is not None:
            if missing:
                self.by_hand(f"{name}: add {missing[0]} in Settings > Secrets and variables > Actions; "
                             "until then the board workflow skips")
            self.variables(name, typ == "organization")
            return
        if "var:BOARD_CONFIG" not in have:
            missing.append("variable BOARD_CONFIG (the board config JSON)")
        if missing:
            self.by_hand(f"{name}: add {'; and '.join(missing)} in Settings > Secrets and variables > Actions; "
                         "until then the board workflow skips")
        if "var:BOARD_REF" not in have:
            self.by_hand(f"{name}: set variable BOARD_REF to the full task-mgmt commit SHA to run the board command from; "
                         "without it the board workflow runs task-mgmt's main and warns")

    def variables(self, name, org=False):
        """From hubs: set the repo's BOARD_CONFIG and BOARD_REF to what they should be. A rehearsal
        compares the current values (BOARD_CONFIG as parsed JSON, BOARD_REF exactly); --live sets them."""
        want = {}
        boards, numberless = {}, []
        for h in self.hubs:
            for b in h["owner"].get("boards", []):
                e = board_entry(h["owner"], b)
                if name in e["repos"]:
                    boards[b["name"]] = e
                    if e["number"] is None:
                        numberless.append(b["name"])
        if not boards:
            self.by_hand(f"{name}: no hub board lists it, so it has no BOARD_CONFIG to set")
        elif numberless:
            self.say("·", f"{name}: BOARD_CONFIG waits for the number of board {', '.join(numberless)} in its hub config")
        else:
            want["BOARD_CONFIG"] = {"defaults": self.defaults, "boards": boards}
        owner = name.split("/")[0]
        sha = self.release_sha((self.hub_of.get(owner) or {}).get("version"))
        if sha:
            want["BOARD_REF"] = sha
        try:
            current = {var: self.gh.rest(f"repos/{name}/actions/variables/{var}") for var in want}
            shared = self.org_variables(name) if org and None in current.values() else {}
        except ProvisionError:
            self.by_hand(f"{name}: couldn't read its Actions variables with this token; check by hand that BOARD_CONFIG "
                         "and BOARD_REF hold what the hubs give")
            return
        for var, value in want.items():
            cur, level = current[var], "repo"
            if cur is None and var in shared:
                cur, level = shared[var], "organization"
            if cur is not None:
                if var == "BOARD_CONFIG":
                    try:
                        same = json.loads(cur.get("value") or "") == value
                    except ValueError:
                        same = False
                else:
                    same = cur.get("value") == value
                if same:
                    self.say("✓", f"{name}: variable {var}" + (" (organization level)" if level == "organization" else ""))
                    continue
                if level == "organization":
                    self.by_hand(f"{name}: the organization variable {var} it sees differs from what the hubs give: "
                                 "update it at the organization, or set a repo-level one")
                    continue
            shown = f"boards {', '.join(value['boards'])}" if var == "BOARD_CONFIG" else value
            self.pending(f"variable {var} on {name} to {shown} ({'missing' if cur is None else 'differs'})",
                         verb=("setting", "would set"))
            if self.live:
                body = json.dumps(value, indent=2) if var == "BOARD_CONFIG" else value
                self.gh.run(["variable", "set", var, "--repo", name, "--body", body])

    def org_variables(self, name):
        """The organization variables a repo's Actions see, by name, with their values."""
        out, page = {}, 1
        while True:  # 100 is GitHub's page limit
            d = self.gh.rest(f"repos/{name}/actions/organization-variables?per_page=100&page={page}") or {}
            items = d.get("variables", [])
            out.update({x["name"]: x for x in items})
            if len(items) < 100:
                return out
            page += 1

    def release_sha(self, version):
        """The commit SHA BOARD_REF pins: the hub's version tag in the product repo, peeled to its
        commit, or else the sha= of the release this script runs from. Missing ones are reported once."""
        key = version or ""
        if key in self.shas:
            return self.shas[key]
        sha = None
        if not version:
            try:
                with open(RELEASE_FILE) as f:
                    for line in f:
                        k, _, v = line.strip().partition("=")
                        if k == "sha" and v:
                            sha = v
            except OSError:
                pass
            if not sha:
                self.by_hand(f"a hub has no \"version\" and there's no {os.path.basename(RELEASE_FILE)} beside "
                             "provision.py, so its repos' BOARD_REF isn't checked: set \"version\" in the hub config")
        else:
            tag = f"refs/tags/{version}"
            plain = peeled = None
            for line in self.gh.ls_remote(f"https://github.com/{PRODUCT_REPO}", tag, tag + "^{}").splitlines():
                found, _, ref = line.strip().partition("\t")
                if ref == tag + "^{}":
                    peeled = found
                elif ref == tag:
                    plain = found
            sha = peeled or plain  # an annotated tag lists the tag object first, then (^{}) its commit
            if not sha:
                self.by_hand(f"release {version} is not a tag of {PRODUCT_REPO}: fix \"version\" in the hub config")
        self.shas[key] = sha
        return sha

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
        hub = self.hub_of.get(owner)
        if not p and b.get("number") is not None:
            self.by_hand(f"{(hub or {}).get('path', 'the config')} gives board {b['name']} #{b['number']}, but {owner} has "
                         f"no open board titled \"{b['title']}\": fix its title or number")
            return
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
        if b.get("number") is not None and b["number"] != d["number"]:
            self.by_hand(f"{(hub or {}).get('path', 'the config')} gives board {b['name']} #{b['number']}, but GitHub has "
                         f"\"{b['title']}\" as #{d['number']}: fix its number")
        elif hub and b.get("number") is None:
            self.by_hand(f"add \"number\": {d['number']} to board {b['name']} in {hub['path']}")
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
        if not b.get("read_only"):
            self.agent_fields(d, p["id"], fields)
        off = [w["name"] for w in d["workflows"]["nodes"] if w["name"] in WORKFLOWS and not w["enabled"]]
        have = {w["name"] for w in d["workflows"]["nodes"]}
        off += [w for w in WORKFLOWS if w not in have]
        if off and not b.get("read_only"):
            self.by_hand(f"turn on in {d['url']}/workflows: {', '.join(off)}")
        levels = [o["name"] for o in (fields.get("Category") or {}).get("options", [])]
        repos = [f"{owner}/{rn}" for rn in b.get("repos", [])]
        tags = any((release or {}).get(rn) == "tags" for rn in b.get("repos", []))
        self.entries[b["name"]] = {"owner": owner, "owner_type": typ, "number": d["number"], "repos": repos,
                                   "release": "tags" if tags else "none", "hierarchy": levels, "outside_hierarchy": [],
                                   **({"read_only": True} if b.get("read_only") else {})}

    def agent_fields(self, d, project_id, fields):
        """The Agent and Responder fields, with the board config's agents and operator as options."""
        agents = list(self.defaults.get("agents") or [])
        op = self.defaults.get("operator")
        op_name = (op if isinstance(op, str) else (op or {}).get("name") or (op or {}).get("login")) if op else None
        if not agents:
            self.say("·", f"board #{d['number']}: no \"agents\" in the board config's defaults, so no Agent and Responder fields")
            return
        want = agents + ([op_name] if op_name else [])
        bad = [n for n in want if not re.match(r"^[\w.-]+$", n or "")]
        if bad:
            raise ProvisionError(f"agent and operator names must be one word: {', '.join(map(repr, bad))}")
        for key, default in (("agent_field", "Agent"), ("responder_field", "Responder")):
            name = self.defaults.get(key) or default
            f = fields.get(name)
            if f is None:
                self.pending(f"field {name} on board #{d['number']} with {', '.join(want)}")
                if self.live:
                    self.gh.graphql(FIELD_M, p=project_id, n=name,
                                    o=[{"name": x, "color": "GRAY", "description": ""} for x in want])
                continue
            have = {o["name"].lower() for o in f.get("options", [])}
            add = [x for x in want if x.lower() not in have]
            if add:
                self.pending(f"{', '.join(add)} in {name} on board #{d['number']}")
                if self.live:
                    keep = [{k: o[k] for k in ("id", "name", "color", "description")} for o in f["options"]]
                    self.gh.graphql(OPTIONS_M, f=f["id"], o=keep + [{"name": x, "color": "GRAY", "description": ""} for x in add])

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
        if self.person is not None:  # from hubs, `provision.py config` writes the board config
            for h in self.hubs:
                for b in h["owner"].get("boards", []):
                    found = self.entries.get(b["name"])
                    if not found:
                        continue
                    e = board_entry(h["owner"], b)
                    same = {"repos": lambda a, c: sorted(a) == sorted(c)}  # repo order doesn't matter; level order does
                    drift = [x for x in ("hierarchy", "repos", "release")
                             if not same.get(x, lambda a, c: a == c)(e[x], found[x])]
                    if drift:
                        self.by_hand(f"hub board {b['name']} differs from GitHub in {', '.join(drift)}: set "
                                     + "; ".join(f"{x} = {json.dumps(found[x])}" for x in drift) + f" in {h['path']}")
            try:
                want = generate(self.person, self.hubs)
            except ProvisionError:
                self.say("·", "board config: waits for every hub board's number")
                return
            try:
                diff = config_diff(want, read_json(self.config_path))
            except OSError:
                diff = ["no file"]
            except ValueError as e:
                diff = [f"not valid JSON ({e})"]
            if diff:
                self.by_hand(f"board config {self.config_path} differs from the hubs ({'; '.join(diff)}): "
                             "run ./provision.py config")
            else:
                self.say("✓", f"board config {self.config_path}")
            return
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
    if argv[:1] == ["config"]:
        return config_main(argv[1:])
    live = "--live" in argv
    args = [a for a in argv if a != "--live"]
    bad = [a for a in args if a.startswith("-")]
    if bad or len(args) > 1:
        print(f"provision: unexpected {' '.join(bad or args[1:])}; see --help", file=sys.stderr)
        return 1
    try:
        if args:
            path, cfg = args[0], load(args[0])
        elif os.path.exists(person_path()):
            cfg = from_person()
            path = ", ".join(h["path"] for h in cfg["hubs"])
        else:
            path = os.path.join(HERE, "github.json")
            if not os.path.exists(path):
                raise ProvisionError(f"no config at {path}: copy github.example.json to github.json and edit it, "
                                     f"or copy person.example.json to {person_path()} to read your hubs")
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
