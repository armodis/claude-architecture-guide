"""Offline tests for provision.py: a fake `gh` stands in for GitHub."""
import importlib.machinery, importlib.util, json, os, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "provision.py")
loader = importlib.machinery.SourceFileLoader("provision_under_test", SRC)
spec = importlib.util.spec_from_loader("provision_under_test", loader)
pv = importlib.util.module_from_spec(spec)
loader.exec_module(pv)

WF_ON = [{"name": w, "enabled": True} for w in pv.WORKFLOWS]


class FakeGH:
    """Answers the queries provision.py sends; records every write."""

    def __init__(self, owners, repos=(), boards=None, labels=(), workflows=None):
        self.owners = owners                      # login -> "Organization" | "User"
        self.repos = set(repos)                   # "owner/name"
        self.boards = boards or {}                # login -> [{"id","number","title","repos":[..],"levels":[..],"themes":[..]}]
        self.labels = set(labels)                 # "owner/name:label"
        self.workflows = workflows if workflows is not None else WF_ON
        self.writes = []

    def graphql(self, q, **v):
        if "repositoryOwner" in q and "projectsV2" in q:
            # GitHub's query matches loosely; provision.py keeps exact titles only
            nodes = [{"id": b["id"], "number": b["number"], "title": b["title"], "url": f"https://x/{b['number']}", "closed": False}
                     for b in self.boards.get(v["l"], []) if v["t"].split()[0].lower() in b["title"].lower()]
            return {"repositoryOwner": {"projectsV2": {"pageInfo": {"hasNextPage": False}, "nodes": nodes}}}
        if "repositoryOwner" in q:
            t = self.owners.get(v["l"])
            if not t:
                return {"repositoryOwner": None}
            return {"repositoryOwner": {"__typename": t, "id": f"O_{v['l']}", "login": v["l"]}}
        if "projectV2(number" in q:
            return {"organization": {"projectV2": {"id": "T_1", "title": "[TEMPLATE] x", "template": True}}}
        if "copyProjectV2" in q:
            self.writes.append(("copy", v["t"]))
            login = v["o"][2:]
            b = {"id": f"P_{v['t']}", "number": 50 + len(self.writes), "title": v["t"], "repos": [],
                 "levels": ["Milestone", "Epic", "User Story"], "themes": ["Old"]}
            self.boards.setdefault(login, []).append(b)
            return {"copyProjectV2": {"projectV2": {"id": b["id"], "number": b["number"], "url": "u"}}}
        if "node(id" in q:
            b = next(b for bs in self.boards.values() for b in bs if b["id"] == v["p"])
            fields = [{"id": "F_cat", "name": "Category", "options": [{"id": f"c{i}", "name": n, "color": "GRAY", "description": ""} for i, n in enumerate(b["levels"])]},
                      {"id": "F_theme", "name": "Theme", "options": [{"id": f"t{i}", "name": n, "color": "GRAY", "description": ""} for i, n in enumerate(b["themes"])]}]
            return {"node": {"number": b["number"], "url": f"https://x/{b['number']}",
                             "repositories": {"nodes": [{"nameWithOwner": r} for r in b["repos"]]},
                             "workflows": {"nodes": self.workflows}, "fields": {"nodes": fields}}}
        if "linkProjectV2ToRepository" in q:
            self.writes.append(("link", v["p"], v["r"]))
            self.board_by_id(v["p"])["repos"].append(v["r"][2:])
            return {}
        if "updateProjectV2Field" in q:
            self.writes.append(("options", v["f"], v["o"]))
            for bs in self.boards.values():
                for b in bs:
                    if v["f"] == "F_theme":
                        b["themes"] = [o["name"] for o in v["o"]]
            return {}
        raise AssertionError(f"unexpected query: {q[:60]}")

    def board_by_id(self, pid):
        return next(b for bs in self.boards.values() for b in bs if b["id"] == pid)

    def rest(self, path):
        parts = path.split("/")
        if len(parts) == 3:  # repos/<owner>/<name>; GitHub answers 404 for a missing repo
            full = f"{parts[1]}/{parts[2]}"
            return {"node_id": f"R_{full}", "size": 1, "pushed_at": "2026-01-01"} if full in self.repos else None
        _, owner, name, _, label = parts
        return {} if f"{owner}/{name}:{label}" in self.labels else None

    def git_identity(self):
        return "dev@example.com"

    def is_empty(self, name):
        return name in getattr(self, "empty", set())

    def scopes(self):
        return {"repo", "project", "read:org", "workflow"}

    def run(self, args, input=None, cwd=None, check=True):
        self.writes.append(("gh", args[0], args[1]))
        if args[:2] == ["repo", "create"]:
            self.repos.add(args[2])
        if args[:2] == ["label", "create"]:
            self.labels.add(f"{args[args.index('--repo') + 1]}:{args[2]}")

    def git(self, args, cwd):
        self.writes.append(("git", args[0]))


ORG = {"login": "acme-co", "type": "organization",
       "repos": [{"name": "ops"}, {"name": "widget", "kind": "product"}],
       "boards": [{"name": "widget", "title": "Widget", "repos": ["widget"], "template": {"owner": "tpl", "number": 9},
                   "themes": ["Data", "App"]}]}


def run(gh, cfg, live, config_path):
    lines = []
    code = pv.Run(gh, cfg, live, config_path=config_path, out=lines.append).go()
    return code, "\n".join(lines)


class Config(unittest.TestCase):
    def write(self, obj):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(obj, f); f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_board_must_link_listed_repos(self):
        bad = {"owners": [dict(ORG, boards=[dict(ORG["boards"][0], repos=["nope"])])]}
        with self.assertRaisesRegex(pv.ProvisionError, "not listed"):
            pv.load(self.write(bad))

    def test_owner_type_checked(self):
        with self.assertRaisesRegex(pv.ProvisionError, "type must be"):
            pv.load(self.write({"owners": [{"login": "x", "type": "team"}]}))

    def test_missing_file_says_what_to_copy(self):
        with self.assertRaisesRegex(pv.ProvisionError, "github.example.json"):
            pv.load("/nonexistent/github.json")

    def test_example_config_loads(self):
        pv.load(os.path.join(HERE, "..", "..", "github.example.json"))


class Scaffold(unittest.TestCase):
    def test_product_layout(self):
        files = pv.scaffold("acme-co", {"name": "widget", "kind": "product"})
        for f in ("README.md", "AGENTS.md", "STATUS.md", ".gitignore", "design/.gitkeep", "docs/decisions/.gitkeep",
                  "backend/.gitkeep", "frontend/.gitkeep", "scripts/.gitkeep", ".env.example"):
            self.assertIn(f, files)
        self.assertIn("design/*/scratch/", files[".gitignore"])
        self.assertIn(".env", files[".gitignore"].split("\n"))

    def test_plain_layout_has_no_app_folders(self):
        files = pv.scaffold("acme-co", {"name": "ops"})
        self.assertNotIn("backend/.gitkeep", files)
        self.assertIn("design/.gitkeep", files)


class Runs(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        self.cfgpath = os.path.join(d, "boards.json")
        self.home = d

    def test_rehearsal_writes_nothing(self):
        gh = FakeGH({"acme-co": "Organization"})
        code, log = run(gh, {"owners": [ORG]}, False, self.cfgpath)
        self.assertEqual(code, 2)
        self.assertEqual(gh.writes, [])
        self.assertIn("would create repo acme-co/widget", log)
        self.assertIn("would create board \"Widget\"", log)
        self.assertFalse(os.path.exists(self.cfgpath))

    def test_missing_org_is_a_manual_step(self):
        code, log = run(FakeGH({}), {"owners": [ORG]}, True, self.cfgpath)
        self.assertEqual(code, 2)
        self.assertIn("organizations/new", log)

    def test_live_creates_repos_board_links_themes_and_config(self):
        gh = FakeGH({"acme-co": "Organization"})
        org = dict(ORG, repos=[dict(r, path=os.path.join(self.home, r["name"])) for r in ORG["repos"]])
        code, log = run(gh, {"owners": [org]}, True, self.cfgpath)
        self.assertEqual(code, 0, log)
        self.assertIn(("gh", "repo", "create"), gh.writes)
        self.assertTrue(os.path.exists(os.path.join(self.home, "widget", "backend", ".gitkeep")))
        self.assertIn(("copy", "Widget"), gh.writes)
        self.assertTrue(any(w[0] == "link" and w[2] == "R_acme-co/widget" for w in gh.writes))
        opts = next(w[2] for w in gh.writes if w[0] == "options")
        self.assertEqual([o["name"] for o in opts], ["Old", "Data", "App"])
        self.assertEqual(opts[0]["id"], "t0", "existing options keep their ids")
        cfg = pv.read_json(self.cfgpath)
        self.assertEqual(cfg["boards"]["widget"]["hierarchy"], ["Milestone", "Epic", "User Story"])
        self.assertEqual(cfg["boards"]["widget"]["owner_type"], "organization")
        self.assertIn("statuses", cfg["defaults"])

    def test_rerun_on_a_complete_setup_changes_nothing(self):
        board = {"id": "P_w", "number": 3, "title": "Widget", "repos": ["acme-co/widget"],
                 "levels": ["Epic"], "themes": ["Data", "App"]}
        gh = FakeGH({"acme-co": "Organization"}, repos={"acme-co/ops", "acme-co/widget"}, boards={"acme-co": [board]},
                    labels={"acme-co/ops:test-fixture", "acme-co/widget:test-fixture"})
        with open(self.cfgpath, "w") as f:
            json.dump({"defaults": {}, "boards": {"widget": {"owner": "acme-co", "number": 3, "repos": ["acme-co/widget"]}}}, f)
        code, log = run(gh, {"owners": [ORG]}, True, self.cfgpath)
        self.assertEqual((code, gh.writes), (0, []), log)
        self.assertIn("Everything is in place", log)
        self.assertEqual(pv.read_json(self.cfgpath)["boards"]["widget"], {"owner": "acme-co", "number": 3, "repos": ["acme-co/widget"]},
                         "existing config entries are kept as they are")

    def test_disabled_workflows_are_reported_with_the_page(self):
        board = {"id": "P_w", "number": 3, "title": "Widget", "repos": ["acme-co/widget"], "levels": [], "themes": ["Data", "App"]}
        wf = [dict(w, enabled=w["name"] != "Auto-add to project") for w in WF_ON]
        gh = FakeGH({"acme-co": "Organization"}, repos={"acme-co/ops", "acme-co/widget"}, boards={"acme-co": [board]},
                    labels={"acme-co/ops:test-fixture", "acme-co/widget:test-fixture"}, workflows=wf)
        code, log = run(gh, {"owners": [ORG]}, True, self.cfgpath)
        self.assertEqual(code, 2)
        self.assertIn("https://x/3/workflows: Auto-add to project", log)


class ReviewCases(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.home))
        self.cfgpath = os.path.join(self.home, "boards.json")

    def write(self, obj):
        path = os.path.join(self.home, "github.json")
        with open(path, "w") as f:
            json.dump(obj, f)
        return path

    def test_duplicate_board_names_and_bad_templates_are_refused(self):
        twice = {"owners": [ORG, dict(ORG, login="other-co")]}
        with self.assertRaisesRegex(pv.ProvisionError, "two boards are named"):
            pv.load(self.write(twice))
        bad = {"owners": [dict(ORG, boards=[dict(ORG["boards"][0], template={"owner": "tpl"})])]}
        with self.assertRaisesRegex(pv.ProvisionError, "template needs"):
            pv.load(self.write(bad))
        with self.assertRaisesRegex(pv.ProvisionError, "non-empty"):
            pv.load(self.write([1]))

    def test_placeholder_theme_is_dropped_when_real_themes_arrive(self):
        board = {"id": "P_w", "number": 3, "title": "Widget", "repos": ["acme-co/widget"], "levels": [], "themes": ["Placeholder"]}
        gh = FakeGH({"acme-co": "Organization"}, repos={"acme-co/ops", "acme-co/widget"}, boards={"acme-co": [board]},
                    labels={"acme-co/ops:test-fixture", "acme-co/widget:test-fixture"})
        code, log = run(gh, {"owners": [ORG]}, True, self.cfgpath)
        self.assertEqual(code, 0, log)
        opts = next(w[2] for w in gh.writes if w[0] == "options")
        self.assertEqual([o["name"] for o in opts], ["Data", "App"])

    def test_a_config_entry_for_another_project_is_reported(self):
        board = {"id": "P_w", "number": 3, "title": "Widget", "repos": ["acme-co/widget"], "levels": [], "themes": ["Data", "App"]}
        gh = FakeGH({"acme-co": "Organization"}, repos={"acme-co/ops", "acme-co/widget"}, boards={"acme-co": [board]},
                    labels={"acme-co/ops:test-fixture", "acme-co/widget:test-fixture"})
        with open(self.cfgpath, "w") as f:
            json.dump({"boards": {"widget": {"owner": "your-org", "owner_type": "organization", "number": 2}}}, f)
        code, log = run(gh, {"owners": [ORG]}, True, self.cfgpath)
        self.assertEqual(code, 2)
        self.assertIn("points at your-org #2, not acme-co #3", log)

    def test_empty_repo_and_config_drift_are_reported(self):
        board = {"id": "P_w", "number": 3, "title": "Widget", "repos": ["acme-co/widget"], "levels": ["Epic"], "themes": ["Data", "App"]}
        gh = FakeGH({"acme-co": "Organization"}, repos={"acme-co/ops", "acme-co/widget"}, boards={"acme-co": [board]},
                    labels={"acme-co/ops:test-fixture", "acme-co/widget:test-fixture"})
        gh.empty = {"acme-co/ops"}
        with open(self.cfgpath, "w") as f:
            json.dump({"boards": {"widget": {"owner": "acme-co", "number": 3, "repos": [], "hierarchy": ["Epic"]}}}, f)
        code, log = run(gh, {"owners": [ORG]}, True, self.cfgpath)
        self.assertEqual(code, 2)
        self.assertIn("repo acme-co/ops exists but is empty", log)
        self.assertIn("differs from GitHub in repos", log)

    def test_missing_workflow_scope_stops_before_creating(self):
        gh = FakeGH({"acme-co": "Organization"})
        gh.scopes = lambda: {"repo", "project", "read:org"}
        org = dict(ORG, repos=[dict(r, path=os.path.join(self.home, r["name"])) for r in ORG["repos"]])
        with self.assertRaisesRegex(pv.ProvisionError, "workflow scope"):
            run(gh, {"owners": [org]}, False, self.cfgpath)
        self.assertEqual(gh.writes, [])

    def test_new_repo_layout_includes_the_board_workflow(self):
        self.assertIn(".github/workflows/board.yml", pv.scaffold("acme-co", {"name": "ops"}))

    def test_config_entry_carries_repos_and_release(self):
        gh = FakeGH({"acme-co": "Organization"})
        org = dict(ORG, repos=[dict(r, path=os.path.join(self.home, r["name"]), release="tags" if r["name"] == "widget" else "none")
                               for r in ORG["repos"]])
        code, log = run(gh, {"owners": [org]}, True, self.cfgpath)
        self.assertEqual(code, 0, log)
        e = pv.read_json(self.cfgpath)["boards"]["widget"]
        self.assertEqual((e["repos"], e["release"]), (["acme-co/widget"], "tags"))


if __name__ == "__main__":
    unittest.main()
