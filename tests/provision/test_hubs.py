"""Offline tests for provision.py's hub config, person layer, generated boards.json and the
workflow variables it manages. Uses test_provision's fake `gh`."""
import contextlib, io, json, os, shutil, tempfile, unittest
from unittest import mock

from test_provision import FakeGH, pv, run

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
ORG_HUB = os.path.join(HERE, "hubs", "org-hub")
USER_HUB = os.path.join(HERE, "hubs", "user-hub")
EXPECTED = os.path.join(HERE, "expected-boards.json")
PERSON = {"operator": {"name": "Pat", "login": "example-user"}, "agents": ["alpha", "beta"],
          "hubs": [ORG_HUB, USER_HUB], "defaults": {"freshness_hours": 12}}
TAG_OBJECT, TAG_COMMIT = "a" * 40, "c" * 40
ANNOTATED = f"{TAG_OBJECT}\trefs/tags/v9.9.9\n{TAG_COMMIT}\trefs/tags/v9.9.9^{{}}\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.out = os.path.join(self.tmp, "boards.json")

    def person(self, **changes):
        path = os.path.join(self.tmp, "person.json")
        with open(path, "w") as f:
            json.dump(dict(PERSON, **changes), f)
        env = mock.patch.dict(os.environ, {"TASK_MGMT_PERSON": path})
        env.start()
        self.addCleanup(env.stop)
        return path

    def hub(self, cfg, name="hub"):
        folder = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(folder, ".task-mgmt"), exist_ok=True)
        with open(os.path.join(folder, ".task-mgmt", "config.json"), "w") as f:
            f.write(cfg if isinstance(cfg, str) else json.dumps(cfg))
        return folder

    def config(self, *args):
        lines = []
        code = pv.config_main(list(args), out=lines.append, err=lines.append)
        return code, "\n".join(lines)


class Generate(Base):
    def test_generated_config_matches_the_hand_kept_one(self):
        self.person()
        code, log = self.config("--out", self.out)
        self.assertEqual(code, 0, log)
        self.assertEqual(pv.read_json(self.out), pv.read_json(EXPECTED))
        self.assertIn("4 boards (company, widget, archive, personal) from 2 hub(s)", log)

    def test_check_passes_on_equal_content_and_fails_on_a_difference(self):
        self.person()
        cfg = pv.read_json(EXPECTED)
        with open(self.out, "w") as f:  # same content, other key order and layout
            json.dump(cfg, f, sort_keys=True)
        self.assertEqual(self.config("--check", "--out", self.out)[0], 0)
        cfg["boards"]["widget"]["number"] = 3
        cfg["boards"]["stray"] = {"owner": "example-org"}
        cfg["defaults"]["stale_days"] = 1
        with open(self.out, "w") as f:
            json.dump(cfg, f)
        code, log = self.config("--check", "--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("board widget: number", log)
        self.assertIn("board stray: not in any hub", log)
        self.assertIn("defaults.stale_days: differs", log)
        self.assertEqual(pv.read_json(self.out), cfg, "--check writes nothing")
        code, log = self.config("--check", "--out", os.path.join(self.tmp, "none.json"))
        self.assertEqual(code, 1)
        self.assertIn("no board config there", log)

    def test_person_defaults_override_key_by_key_and_agents_come_last(self):
        self.person(defaults={"stale_days": 3, "statuses": {"done": "Shipped"}, "agents": ["ignored"]})
        self.assertEqual(self.config("--out", self.out)[0], 0)
        d = pv.read_json(self.out)["defaults"]
        self.assertEqual(d["stale_days"], 3)
        self.assertEqual(d["statuses"], {"done": "Shipped"}, "a key is replaced whole")
        self.assertEqual(d["leaf_type"], "Task", "shipped defaults stay")
        self.assertEqual(d["agents"], ["alpha", "beta"])

    def test_a_board_without_a_number_is_an_error(self):
        h = pv.read_json(os.path.join(USER_HUB, ".task-mgmt", "config.json"))
        del h["owner"]["boards"][0]["number"]
        self.person(hubs=[ORG_HUB, self.hub(h)])
        code, log = self.config("--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("board personal has no \"number\": run ./provision.py", log)
        self.assertFalse(os.path.exists(self.out))


class Validation(Base):
    def test_person_layer_errors(self):
        with mock.patch.dict(os.environ, {"TASK_MGMT_PERSON": os.path.join(self.tmp, "absent.json")}):
            with self.assertRaisesRegex(pv.ProvisionError, "person.example.json"):
                pv.load_person()
        for bad, msg in ((dict(hubs=[]), "non-empty list"), (dict(agents="alpha"), "list of names"),
                         (dict(operator={}), "operator"), (dict(defaults=[]), "defaults")):
            self.person(**bad)
            with self.assertRaisesRegex(pv.ProvisionError, msg):
                pv.load_person()

    def test_hub_errors(self):
        org = pv.read_json(os.path.join(ORG_HUB, ".task-mgmt", "config.json"))
        cases = [("{", "not valid JSON"), ({"version": "v1"}, "\"owner\" entry"), (dict(org, version=""), "release tag"),
                 (dict(org, blocks={}), "blocks"),
                 (dict(org, owner=dict(org["owner"], boards=[dict(org["owner"]["boards"][0], number="1")])), "number must be a number"),
                 (dict(org, owner=dict(org["owner"], boards=[dict(org["owner"]["boards"][0], read_only="yes")])), "read_only must be true"),
                 (dict(org, owner=dict(org["owner"], type="team")), "type must be")]
        for i, (cfg, msg) in enumerate(cases):
            with self.assertRaisesRegex(pv.ProvisionError, msg):
                pv.load_hub(self.hub(cfg, f"h{i}"), set())
        with self.assertRaisesRegex(pv.ProvisionError, "hub.example.json"):
            pv.load_hub(os.path.join(self.tmp, "nohub"), set())
        self.person(hubs=[ORG_HUB, ORG_HUB])
        with self.assertRaisesRegex(pv.ProvisionError, "two boards are named"):
            pv.from_person()

    def test_examples_load(self):
        pv.load_person(os.path.join(ROOT, "person.example.json"))
        shutil.copy(os.path.join(ROOT, "hub.example.json"), os.path.join(self.hub({}, "ex"), ".task-mgmt", "config.json"))
        pv.load_hub(os.path.join(self.tmp, "ex"), set())

    def test_without_a_file_argument_the_hubs_are_the_owners(self):
        self.person()
        cfg = pv.from_person()
        self.assertEqual([o["login"] for o in cfg["owners"]], ["example-org", "example-user"])
        with mock.patch.dict(os.environ, {"TASK_MGMT_PERSON": os.path.join(self.tmp, "absent.json")}):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(pv.main([]), 1)
        self.assertIn("no person layer", err.getvalue())


def org_gh(numbers=(1, 2, 4), workflows=None):
    boards = [{"id": f"P_{t}", "number": n, "title": t, "repos": [f"example-org/{r}"], "levels": [], "themes": []}
              for t, r, n in zip(("Company", "Widget", "Archive"), ("ops", "widget", "archive"), numbers)]
    repos = {"example-org/ops", "example-org/widget", "example-org/archive"}
    gh = FakeGH({"example-org": "Organization"}, repos=repos, boards={"example-org": boards},
                labels={f"{r}:test-fixture" for r in repos}, workflows=workflows)
    gh.tags = {"v9.9.9": ANNOTATED}
    return gh


class Variables(Base):
    def setUp(self):
        super().setUp()
        self.person(hubs=[ORG_HUB])
        self.cfg = pv.from_person()
        self.want = pv.generate(self.cfg["person"], self.cfg["hubs"])
        with open(self.out, "w") as f:
            json.dump(self.want, f)

    def board_config(self, *names):
        return {"defaults": self.want["defaults"], "boards": {n: self.want["boards"][n] for n in names}}

    def test_missing_variables_are_pending_and_nothing_is_written(self):
        gh = org_gh()
        code, log = run(gh, self.cfg, False, self.out)
        self.assertEqual(code, 2, log)
        self.assertEqual(gh.writes, [])
        self.assertIn("would set variable BOARD_CONFIG on example-org/widget to boards widget (missing)", log)
        self.assertIn(f"would set variable BOARD_REF on example-org/ops to {TAG_COMMIT} (missing)", log)
        self.assertNotIn(TAG_OBJECT, log, "an annotated tag pins its commit, not the tag object")
        self.assertEqual(gh.lookups, [("https://github.com/armodis-ai/task-mgmt", ("refs/tags/v9.9.9", "refs/tags/v9.9.9^{}"))],
                         "the tag is resolved once per run")

    def test_differing_and_content_equal_values(self):
        gh = org_gh()
        widget = self.board_config("widget")
        reordered = json.dumps({"boards": widget["boards"], "defaults": dict(reversed(list(widget["defaults"].items())))})
        gh.vars = {"example-org/widget:BOARD_CONFIG": reordered, "example-org/widget:BOARD_REF": TAG_COMMIT,
                   "example-org/ops:BOARD_CONFIG": json.dumps(self.board_config("widget")),
                   "example-org/ops:BOARD_REF": TAG_OBJECT}
        code, log = run(gh, self.cfg, False, self.out)
        self.assertIn("✓ example-org/widget: variable BOARD_CONFIG", log)
        self.assertIn("✓ example-org/widget: variable BOARD_REF", log)
        self.assertIn("would set variable BOARD_CONFIG on example-org/ops to boards company (differs)", log)
        self.assertIn(f"would set variable BOARD_REF on example-org/ops to {TAG_COMMIT} (differs)", log)

    def test_live_sets_them_and_reads_them_back(self):
        gh = org_gh()
        code, log = run(gh, self.cfg, True, self.out)
        self.assertEqual(code, 0, log)
        self.assertEqual(json.loads(gh.vars["example-org/ops:BOARD_CONFIG"]), self.board_config("company"))
        self.assertEqual(json.loads(gh.vars["example-org/archive:BOARD_CONFIG"]), self.board_config("archive"))
        self.assertEqual(gh.vars["example-org/widget:BOARD_REF"], TAG_COMMIT)
        self.assertEqual(sum(1 for w in gh.writes if w[:2] == ("gh", "variable")), 6)
        self.assertIn("Reading back what landed", log)
        self.assertIn("✓ example-org/ops: variable BOARD_CONFIG", log.split("Reading back")[1])

    def test_a_lightweight_tag_and_the_release_file(self):
        gh = org_gh()
        gh.tags = {"v9.9.9": f"{TAG_COMMIT}\trefs/tags/v9.9.9\n"}
        code, log = run(gh, self.cfg, False, self.out)
        self.assertIn(f"BOARD_REF on example-org/ops to {TAG_COMMIT}", log)
        hub = pv.read_json(os.path.join(ORG_HUB, ".task-mgmt", "config.json"))
        del hub["version"]
        self.person(hubs=[self.hub(hub)])
        cfg = pv.from_person()
        release = os.path.join(self.tmp, ".task-mgmt-release")
        with mock.patch.object(pv, "RELEASE_FILE", release):
            code, log = run(org_gh(), cfg, False, self.out)
            self.assertIn("so its repos' BOARD_REF isn't checked", log)
            with open(release, "w") as f:
                f.write("tag=v9.9.8\nsha=" + "b" * 40 + "\n")
            code, log = run(org_gh(), cfg, False, self.out)
            self.assertIn("BOARD_REF on example-org/ops to " + "b" * 40, log)

    def test_an_unknown_tag_is_a_step_by_hand(self):
        gh = org_gh()
        gh.tags = {}
        code, log = run(gh, self.cfg, False, self.out)
        self.assertIn("release v9.9.9 is not a tag of armodis-ai/task-mgmt", log)
        self.assertNotIn("variable BOARD_REF on", log)

    def test_read_only_boards_get_no_workflow_finding(self):
        off = [{"name": w, "enabled": False} for w in pv.WORKFLOWS]
        code, log = run(org_gh(workflows=off), self.cfg, False, self.out)
        self.assertIn("turn on in https://x/1/workflows", log)
        self.assertNotIn("https://x/4/workflows", log)

    def test_a_hub_number_github_disagrees_with_is_reported(self):
        code, log = run(org_gh(numbers=(1, 5, 4)), self.cfg, False, self.out)
        self.assertEqual(code, 2)
        self.assertIn("gives board widget #2, but GitHub has \"Widget\" as #5", log)

    def test_a_board_config_that_differs_from_the_hubs_is_reported(self):
        with open(self.out, "w") as f:
            json.dump(dict(self.want, boards={}), f)
        code, log = run(org_gh(), self.cfg, False, self.out)
        self.assertIn("differs from the hubs (board archive: missing; board company: missing; board widget: missing): "
                      "run ./provision.py config", log)

    def test_github_json_input_keeps_presence_only_checks(self):
        org = pv.read_json(os.path.join(ORG_HUB, ".task-mgmt", "config.json"))["owner"]
        gh = org_gh()
        code, log = run(gh, {"owners": [org]}, False, os.path.join(self.tmp, "other.json"))
        self.assertNotIn("variable BOARD_CONFIG on", log)
        self.assertFalse(hasattr(gh, "lookups"))


if __name__ == "__main__":
    unittest.main()
