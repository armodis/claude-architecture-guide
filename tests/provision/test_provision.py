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
        self.vars = {}                            # "owner/name:VAR" -> value, the repo's Actions variables
        self.tags = {}                            # tag -> `git ls-remote` output for it

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
            fields += [{"id": f"F_{n}", "name": n, "options": [{"id": f"{n}{i}", "name": o, "color": "GRAY", "description": ""} for i, o in enumerate(opts)]}
                       for n, opts in b.get("agent_fields", {}).items()]
            return {"node": {"number": b["number"], "url": f"https://x/{b['number']}",
                             "repositories": {"nodes": [{"nameWithOwner": r} for r in b["repos"]]},
                             "workflows": {"nodes": self.workflows}, "fields": {"nodes": fields}}}
        if "linkProjectV2ToRepository" in q:
            self.writes.append(("link", v["p"], v["r"]))
            self.board_by_id(v["p"])["repos"].append(v["r"][2:])
            return {}
        if "createProjectV2Field" in q:
            self.writes.append(("field", v["n"], [o["name"] for o in v["o"]]))
            self.board_by_id(v["p"]).setdefault("agent_fields", {})[v["n"]] = [o["name"] for o in v["o"]]
            return {}
        if "updateProjectV2Field" in q:
            self.writes.append(("options", v["f"], v["o"]))
            for bs in self.boards.values():
                for b in bs:
                    if v["f"] == "F_theme":
                        b["themes"] = [o["name"] for o in v["o"]]
                    elif v["f"][2:] in b.get("agent_fields", {}):
                        b["agent_fields"][v["f"][2:]] = [o["name"] for o in v["o"]]
            return {}
        raise AssertionError(f"unexpected query: {q[:60]}")

    def board_by_id(self, pid):
        return next(b for bs in self.boards.values() for b in bs if b["id"] == pid)

    def rest(self, path):
        parts = path.split("/")
        if len(parts) == 3:  # repos/<owner>/<name>; GitHub answers 404 for a missing repo
            full = f"{parts[1]}/{parts[2]}"
            return {"node_id": f"R_{full}", "size": 1, "pushed_at": "2026-01-01"} if full in self.repos else None
        if parts[3] == "contents":  # the board workflow file
            return None if "workflow" in getattr(self, "absent", set()) else {}
        if parts[3] == "actions" and len(parts) == 6:  # one repo variable: repos/<owner>/<name>/actions/variables/<NAME>
            if getattr(self, "vars_forbidden", False):
                raise pv.ProvisionError(f"gh api {path}: HTTP 403")
            value = self.vars.get(f"{parts[1]}/{parts[2]}:{parts[5]}")
            return None if value is None else {"name": parts[5], "value": value}
        if parts[3] == "actions":  # secret and variable lists, repo and organization level
            if getattr(self, "actions_forbidden", False):
                raise pv.ProvisionError(f"gh api {path}: HTTP 403")
            kind = parts[4].split("?")[0]
            have = getattr(self, "actions", {"actions/secrets": ["BOARD_TOKEN"], "actions/variables": ["BOARD_CONFIG", "BOARD_REF"]})
            key = "secrets" if kind.endswith("secrets") else "variables"
            if kind == "organization-variables" and getattr(self, "org_vars", None):  # with values, as GitHub lists them
                return {key: [{"name": k, "value": v} for k, v in self.org_vars.items()]}
            return {key: [{"name": x} for x in have.get("actions/" + kind, [])]}
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
        if args[:2] == ["variable", "set"]:
            self.vars[f"{args[args.index('--repo') + 1]}:{args[2]}"] = args[args.index("--body") + 1]

    def ls_remote(self, url, *refs):
        self.lookups = getattr(self, "lookups", []) + [(url, refs)]  # a read: not in writes
        tag = refs[0].rsplit("/", 1)[1]
        return self.tags.get(tag, "")

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

    def test_agent_fields_are_created_from_the_board_configs_agents_and_operator(self):
        with open(self.cfgpath, "w") as f:
            json.dump({"defaults": {"agents": ["alpha", "beta"], "operator": {"name": "Pat", "login": "pat-example"}},
                       "boards": {}}, f)
        board = {"id": "P_w", "number": 3, "title": "Widget", "repos": ["acme-co/widget"], "levels": [], "themes": ["Data", "App"],
                 "agent_fields": {"Agent": ["alpha"]}}
        gh = FakeGH({"acme-co": "Organization"}, repos={"acme-co/ops", "acme-co/widget"}, boards={"acme-co": [board]},
                    labels={"acme-co/ops:test-fixture", "acme-co/widget:test-fixture"})
        code, log = run(gh, {"owners": [ORG]}, True, self.cfgpath)
        self.assertEqual(code, 0, log)
        self.assertIn(("field", "Responder", ["alpha", "beta", "Pat"]), gh.writes)
        added = next(w[2] for w in gh.writes if w[0] == "options" and w[1] == "F_Agent")
        self.assertEqual([o["name"] for o in added], ["alpha", "beta", "Pat"])
        self.assertEqual(added[0]["id"], "Agent0")
        self.assertEqual(board["agent_fields"], {"Agent": ["alpha", "beta", "Pat"], "Responder": ["alpha", "beta", "Pat"]})

    def test_agent_and_operator_names_must_be_one_word(self):
        with open(self.cfgpath, "w") as f:
            json.dump({"defaults": {"agents": ["alpha"], "operator": {"name": "Pat Doe", "login": "pat"}}, "boards": {}}, f)
        board = {"id": "P_w", "number": 3, "title": "Widget", "repos": ["acme-co/widget"], "levels": [], "themes": ["Data", "App"]}
        gh = FakeGH({"acme-co": "Organization"}, repos={"acme-co/ops", "acme-co/widget"}, boards={"acme-co": [board]},
                    labels={"acme-co/ops:test-fixture", "acme-co/widget:test-fixture"})
        with self.assertRaisesRegex(pv.ProvisionError, "one word.*'Pat Doe'"):
            run(gh, {"owners": [ORG]}, True, self.cfgpath)
        self.assertFalse(any(w[0] == "field" for w in gh.writes))

    def test_without_agents_in_the_config_no_agent_fields_are_made(self):
        board = {"id": "P_w", "number": 3, "title": "Widget", "repos": ["acme-co/widget"], "levels": [], "themes": ["Data", "App"]}
        gh = FakeGH({"acme-co": "Organization"}, repos={"acme-co/ops", "acme-co/widget"}, boards={"acme-co": [board]},
                    labels={"acme-co/ops:test-fixture", "acme-co/widget:test-fixture"})
        code, log = run(gh, {"owners": [ORG]}, True, self.cfgpath)
        self.assertFalse(any(w[0] == "field" for w in gh.writes))
        self.assertIn("no Agent and Responder fields", log)

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

    def automation_run(self, **attrs):
        board = {"id": "P_w", "number": 3, "title": "Widget", "repos": ["acme-co/widget"], "levels": [], "themes": ["Data", "App"]}
        gh = FakeGH({"acme-co": "Organization"}, repos={"acme-co/ops", "acme-co/widget"}, boards={"acme-co": [board]},
                    labels={"acme-co/ops:test-fixture", "acme-co/widget:test-fixture"})
        for k, v in attrs.pop("gh", {}).items():
            setattr(gh, k, v)
        org = attrs.pop("org", ORG)
        code, log = run(gh, {"owners": [org]}, True, self.cfgpath)
        return code, log, gh

    def test_missing_token_or_config_is_a_step_by_hand(self):
        code, log, gh = self.automation_run(gh={"actions": {"actions/variables": ["BOARD_CONFIG", "BOARD_REF"]}})
        self.assertEqual(code, 2)
        self.assertIn("acme-co/ops: add a token", log)
        self.assertNotIn("variable BOARD_CONFIG (the board", log)
        self.assertEqual([w for w in gh.writes if w[0] != "options"], [], "nothing is set: the token is the owner's")

    def test_organization_level_and_app_tokens_count(self):
        code, log, _ = self.automation_run(gh={"actions": {"actions/organization-variables": ["BOARD_CONFIG", "BOARD_APP_ID", "BOARD_REF"],
                                                           "actions/organization-secrets": ["BOARD_APP_KEY"]}})
        self.assertEqual(code, 0, log)

    def test_an_unpinned_board_command_is_a_step_by_hand(self):
        code, log, _ = self.automation_run(gh={"actions": {"actions/secrets": ["BOARD_TOKEN"], "actions/variables": ["BOARD_CONFIG"]}})
        self.assertEqual(code, 2)
        self.assertIn("acme-co/ops: set variable BOARD_REF", log)
        self.assertNotIn("add a token", log)

    def test_unreadable_secrets_are_reported_not_fatal(self):
        code, log, _ = self.automation_run(gh={"actions_forbidden": True})
        self.assertEqual(code, 2)
        self.assertIn("couldn't read its Actions secrets", log)

    def test_user_repos_skip_the_organization_lookup(self):
        class UserGH(FakeGH):
            def rest(self, path):
                if "organization-" in path:
                    raise pv.ProvisionError(f"gh api {path}: HTTP 422 Validation Failed")
                return super().rest(path)
        board = {"id": "P_t", "number": 1, "title": "Tasks", "repos": ["jdoe/tasks"], "levels": [], "themes": ["Home"]}
        gh = UserGH({"jdoe": "User"}, repos={"jdoe/tasks"}, boards={"jdoe": [board]}, labels={"jdoe/tasks:test-fixture"})
        me = {"login": "jdoe", "type": "user", "repos": [{"name": "tasks"}],
              "boards": [{"name": "tasks", "title": "Tasks", "repos": ["tasks"], "template": {"owner": "tpl", "number": 7}}]}
        code, log = run(gh, {"owners": [me]}, True, self.cfgpath)
        self.assertNotIn("couldn't read", log)
        self.assertEqual(code, 0, log)

    def test_missing_workflow_and_opting_out(self):
        code, log, _ = self.automation_run(gh={"absent": {"workflow"}})
        self.assertIn("copy template/repo/.github/workflows/board.yml", log)
        org = dict(ORG, repos=[dict(r, automation=False) for r in ORG["repos"]])
        code, log, _ = self.automation_run(gh={"absent": {"workflow"}}, org=org)
        self.assertEqual(code, 0, log)

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
