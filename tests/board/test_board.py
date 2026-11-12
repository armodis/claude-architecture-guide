"""Unit tests for the board library: plan checks, selection, hygiene, STATUS.md claims.
Offline; nothing here calls GitHub.  Run:  python3 -m unittest discover -s tests/board"""
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "template", "board", ".local", "bin", "board")
CONFIG = os.path.join(HERE, "boards.test.json")
loader = importlib.machinery.SourceFileLoader("board", SRC)
spec = importlib.util.spec_from_loader("board", loader)
board = importlib.util.module_from_spec(spec)
loader.exec_module(board)

BOARDS = board.load_config(CONFIG)
WORK = BOARDS["company"]
OPTS = lambda *names: [{"id": f"id-{n}", "name": n, "color": "GRAY", "description": ""} for n in names]


UNSET = object()


def item(ref, title="x", status="Todo", state="OPEN", typ=UNSET, parent=None, children=(), labels=(),
         created="2026-01-01T00:00:00Z", updated=None, assignees=(), blocked_by=(), prs=(), **fields):
    """A snapshot item. Theme and Complexity default to set, and the type to Feature for an item with
    a Category and Task otherwise, so tests name only the fields they are about."""
    f = {"Status": status} if status else {}
    f.update({"Theme": "Placeholder", "Complexity": "Low"})
    f.update({k.replace("_", " "): v for k, v in fields.items()})
    f = {k: v for k, v in f.items() if v is not None}
    if typ is UNSET:
        typ = "Feature" if f.get("Category") else "Task"
    return {"item_id": "PVTI_" + ref, "kind": "ISSUE", "archived": False, "title": title, "fields": f,
            "ref": ref, "issue_id": "I_" + ref, "state": state, "state_reason": None, "created": created,
            "updated": updated or created, "url": "https://github.com/" + ref.replace("#", "/issues/"),
            "issue_type": typ, "labels": list(labels), "parent": parent, "children": list(children),
            "assignees": list(assignees), "blocked_by": list(blocked_by), "prs": list(prs)}


def snap(*items):
    return {"board": "company", "taken": "2026-11-11T00:00:00+00:00", "project_id": "PVT_x",
            "fields": {"Status": {"id": "F1", "type": "SINGLE_SELECT", "options": OPTS("Todo", "Backlog", "In Progress", "Pending Release", "Done")},
                       "Priority": {"id": "F2", "type": "SINGLE_SELECT", "options": OPTS("P0", "P1", "P2", "P3")},
                       "Effort": {"id": "F3", "type": "NUMBER"},
                       "Category": {"id": "F4", "type": "SINGLE_SELECT", "options": OPTS("Epic", "User Story")},
                       "Theme": {"id": "F5", "type": "SINGLE_SELECT", "options": OPTS("Placeholder")},
                       "Complexity": {"id": "F6", "type": "SINGLE_SELECT", "options": OPTS("Trivial", "Low", "Medium", "Medium-High", "High")},
                       "Target Org": {"id": "F7", "type": "SINGLE_SELECT", "options": OPTS("Acme", "globex")}},
            "items": list(items)}


# A create with every required field, as a leaf under the User Story acme-co/ops#2.
FULL = {"type": "Task", "parent": "acme-co/ops#2", "fields": {"Status": "Backlog", "Priority": "P2", "Theme": "Placeholder",
                                                             "Complexity": "Low", "Effort": 1}}


def no_lookup(ref):
    raise AssertionError(f"unexpected lookup of {ref}")


class PlanChecks(unittest.TestCase):
    def setUp(self):
        self.s = snap(item("acme-co/ops#1", title="Real epic", Category="Epic"),
                      item("acme-co/ops#2", title="Real story", Category="User Story"),
                      item("acme-co/ops#4", title="[Test fixture] Epic", labels=["test-fixture"], Category="Epic"),
                      item("acme-co/ops#6", title="[Test fixture] Task 1", labels=["test-fixture"], typ="Task"))

    def check(self, plan, lookup=no_lookup, b=WORK):
        return board.check_plan(b, self.s, plan, lookup)

    def test_small_field_edit_applies_without_review(self):
        _, reasons = self.check([{"op": "set_field", "item": "acme-co/ops#1", "field": "Priority", "value": "P1"}])
        self.assertEqual(reasons, [])

    def test_close_and_reparent_need_review(self):
        _, reasons = self.check([{"op": "close", "item": "acme-co/ops#2", "reason": "duplicate", "duplicate_of": "acme-co/ops#1"},
                                 {"op": "attach", "parent": "acme-co/ops#1", "child": "acme-co/ops#2"}])
        self.assertEqual([r.split(": ")[1] for r in reasons], ["close", "attach"])

    def test_category_change_needs_review(self):
        _, reasons = self.check([{"op": "set_field", "item": "acme-co/ops#2", "field": "Category", "value": "Epic"}])
        self.assertIn("op 1: changes level (Category)", reasons)

    def test_fixture_only_plan_is_exempt(self):
        _, reasons = self.check([{"op": "close", "item": "acme-co/ops#6", "reason": "completed"},
                                 {"op": "attach", "parent": "acme-co/ops#4", "child": "acme-co/ops#6"}])
        self.assertEqual(reasons, [])

    def test_mixed_plan_is_not_exempt(self):
        _, reasons = self.check([{"op": "attach", "parent": "acme-co/ops#1", "child": "acme-co/ops#6"}])
        self.assertTrue(reasons)

    def test_cross_owner_attach_refused_without_flag(self):
        self.s["items"].append(item("jdoe/tasks#9", title="Personal task"))
        lookup = no_lookup
        with self.assertRaisesRegex(board.BoardError, "crosses owners"):
            self.check([{"op": "attach", "parent": "acme-co/ops#2", "child": "jdoe/tasks#9"}], lookup)
        _, reasons = self.check([{"op": "attach", "parent": "acme-co/ops#2", "child": "jdoe/tasks#9", "cross_owner": True}], lookup)
        self.assertIn("op 1: crosses owners", reasons)

    def test_cross_owner_add_and_create_refused_without_flag(self):
        lookup = lambda r: dict(owner="jdoe", title="t", labels=[], parent=None)
        with self.assertRaisesRegex(board.BoardError, "owned outside"):
            self.check([{"op": "add", "item": "jdoe/tasks#9"}], lookup)
        with self.assertRaisesRegex(board.BoardError, "crosses owners"):
            self.check([{"op": "create", "repo": "jdoe/tasks", "title": "t"}])

    def test_bad_option_and_bad_number_rejected(self):
        with self.assertRaisesRegex(board.BoardError, "not an option"):
            self.check([{"op": "set_field", "item": "acme-co/ops#1", "field": "Priority", "value": "P9"}])
        with self.assertRaisesRegex(board.BoardError, "number"):
            self.check([{"op": "set_field", "item": "acme-co/ops#1", "field": "Effort", "value": "big"}])

    def test_alias_must_be_created_first(self):
        with self.assertRaisesRegex(board.BoardError, "not created earlier"):
            self.check([{"op": "attach", "parent": "$story", "child": "acme-co/ops#6"}])
        steps, _ = self.check([{"op": "create", "repo": "acme-co/ops", "title": "[Test fixture] new", "labels": ["test-fixture"],
                                "parent": "acme-co/ops#4", "as": "story", "fields": {"Category": "User Story"}},
                               {"op": "attach", "parent": "$story", "child": "acme-co/ops#6"}])
        self.assertEqual(len(steps), 2)

    def test_field_edit_off_board_needs_add_first(self):
        lookup = lambda r: dict(owner="acme-co", title="t", labels=[], parent=None)
        with self.assertRaisesRegex(board.BoardError, "add it first"):
            self.check([{"op": "set_field", "item": "acme-co/ops#9", "field": "Priority", "value": "P1"}], lookup)
        self.check([{"op": "add", "item": "acme-co/ops#9"},
                    {"op": "set_field", "item": "acme-co/ops#9", "field": "Priority", "value": "P1"}], lookup)

    def test_large_plan_needs_review(self):
        s = snap(*[item(f"acme-co/ops#{n}") for n in range(1, 13)])
        plan = [{"op": "set_field", "item": f"acme-co/ops#{n}", "field": "Priority", "value": "P2"} for n in range(1, 13)]
        _, reasons = board.check_plan(WORK, s, plan, no_lookup)
        self.assertIn("touches 12 items (over 10)", reasons)

    def test_read_only_board_refuses_plans(self):
        with self.assertRaisesRegex(board.BoardError, "read-only"):
            self.check([{"op": "set_field", "item": "acme-co/ops#1", "field": "Priority", "value": "P1"}], b=BOARDS["globex"])

    def test_add_options_always_reviewed(self):
        _, reasons = self.check([{"op": "add_options", "field": "Theme", "options": ["Tax & compliance"]}])
        self.assertIn("op 1: add_options", reasons)

    def test_add_options_needs_a_list_of_distinct_names(self):
        for bad in ("P0", [], ["P0", "P0"], ["P0", ""]):
            with self.assertRaises(board.BoardError, msg=repr(bad)):
                self.check([{"op": "add_options", "field": "Theme", "options": bad}])

    def test_options_added_earlier_can_be_set_and_snapshot_is_untouched(self):
        before = json.dumps(self.s["fields"]["Theme"], sort_keys=True)
        self.check([{"op": "add_options", "field": "Theme", "options": ["Engineering"]},
                    {"op": "set_field", "item": "acme-co/ops#4", "field": "Theme", "value": "Engineering"}])
        with self.assertRaises(board.BoardError):
            self.check([{"op": "set_field", "item": "acme-co/ops#4", "field": "Theme", "value": "Engineering"}])
        self.assertEqual(before, json.dumps(self.s["fields"]["Theme"], sort_keys=True))


    def test_issue_ops_need_the_item_on_the_board(self):
        lookup = lambda r: dict(owner="acme-co", title="t", labels=[], parent=None)
        for op in ({"op": "close", "item": "acme-co/ops#9"}, {"op": "reopen", "item": "acme-co/ops#9"},
                   {"op": "set_type", "item": "acme-co/ops#9", "type": None},
                   {"op": "label", "item": "acme-co/ops#9", "add": ["bug"]},
                   {"op": "remove", "item": "acme-co/ops#9"}):
            with self.assertRaisesRegex(board.BoardError, "not on the company board", msg=op["op"]):
                self.check([op], lookup)

    def test_remove_of_an_item_created_in_the_plan_is_allowed(self):
        steps, _ = self.check([{"op": "create", "repo": "acme-co/ops", "title": "[Test fixture] tmp", "labels": ["test-fixture"],
                                "parent": "acme-co/ops#4", "as": "tmp"},
                               {"op": "detach", "child": "$tmp"}, {"op": "close", "item": "$tmp", "reason": "not_planned"},
                               {"op": "remove", "item": "$tmp"}])
        self.assertEqual(len(steps), 4)

    def test_dry_run_shows_the_close_reason_used(self):
        self.assertEqual(board.describe({"op": "close", "item": "o/r#2", "duplicate_of": "o/r#1"}), "close o/r#2 (duplicate of o/r#1)")

    def test_missing_and_unknown_keys_rejected(self):
        with self.assertRaisesRegex(board.BoardError, "set_type needs type"):
            self.check([{"op": "set_type", "item": "acme-co/ops#6"}])
        with self.assertRaisesRegex(board.BoardError, "does not take dry_run"):
            self.check([{"op": "reopen", "item": "acme-co/ops#6", "dry_run": True}])

    def test_types_and_labels_checked_before_writing(self):
        repo = lambda r: {"types": {"Task": "T"}, "labels": {"test-fixture": "L"}}
        with self.assertRaisesRegex(board.BoardError, "no issue type 'Epic'"):
            board.check_plan(WORK, self.s, [{"op": "set_type", "item": "acme-co/ops#6", "type": "Epic"}], no_lookup, repo)
        with self.assertRaisesRegex(board.BoardError, r"no label \['nope'\]"):
            board.check_plan(WORK, self.s, [dict(FULL, op="create", repo="acme-co/ops", title="t", labels=["nope"])], no_lookup, repo)

    def test_fixture_label_change_is_reviewed(self):
        _, reasons = self.check([{"op": "label", "item": "acme-co/ops#6", "remove": ["test-fixture"]}])
        self.assertIn("op 1: changes the test-fixture label", reasons)

    def test_label_alone_does_not_make_a_fixture(self):
        self.s["items"].append(item("acme-co/ops#8", title="Real story", labels=["test-fixture"]))
        _, reasons = self.check([{"op": "close", "item": "acme-co/ops#8"}])
        self.assertEqual(reasons, ["op 1: close"])

    def test_creates_count_toward_size(self):
        plan = [dict(FULL, op="create", repo="acme-co/ops", title=f"t{n}") for n in range(11)]
        _, reasons = self.check(plan)
        self.assertIn("touches 12 items (over 10)", reasons)  # 11 creates and their parent

    def test_duplicate_close_inputs_must_agree(self):
        for op in ({"op": "close", "item": "acme-co/ops#2", "reason": "completed", "duplicate_of": "acme-co/ops#1"},
                   {"op": "close", "item": "acme-co/ops#2", "reason": "duplicate"},
                   {"op": "close", "item": "acme-co/ops#2", "duplicate_of": "acme-co/ops#2"}):
            with self.assertRaises(board.BoardError):
                self.check([op])
        self.check([{"op": "close", "item": "acme-co/ops#2", "duplicate_of": "acme-co/ops#1"}])

    def test_booleans_are_not_numbers_and_text_needs_a_string(self):
        self.s["fields"]["WBS"] = {"id": "F6", "type": "TEXT"}
        with self.assertRaisesRegex(board.BoardError, "number"):
            self.check([{"op": "set_field", "item": "acme-co/ops#1", "field": "Effort", "value": True}])
        with self.assertRaisesRegex(board.BoardError, "text"):
            self.check([{"op": "set_field", "item": "acme-co/ops#1", "field": "WBS", "value": 3}])


class Selection(unittest.TestCase):
    def test_order_and_skips(self):
        P = "o/r#100"
        s = snap(item("o/r#1", Priority="P2", Effort=1, parent=P, created="2026-01-01T00:00:00Z"),
                 item("o/r#2", Priority="P1", Effort=5, parent=P),
                 item("o/r#3", Priority="P1", Effort=2, parent=P),
                 item("o/r#4", Priority="P1", Effort=2, parent=P, created="2025-12-01T00:00:00Z"),
                 item("o/r#5", Priority="P0", parent=P),                                   # no Effort
                 item("o/r#6", Priority="P0", Effort=1, parent=P, status="Backlog"),
                 item("o/r#7", title="[Test fixture] x", Priority="P0", Effort=1, parent=P, labels=["test-fixture"]),
                 item("o/r#8", Priority="P0", Effort=1, parent=P),                          # claimed
                 item("o/r#9", Priority="P0", Effort=1, parent=P, state="CLOSED"),
                 item("o/r#10", Priority="P0", Effort=1, parent=P, assignees=["someone"]),
                 item("o/r#11", Priority="P0", Effort=1, parent=P, blocked_by=["o/r#12"]),
                 item("o/r#13", Priority="P0", Effort=1, Theme=None, Complexity=None),     # no parent, Theme, Complexity
                 item("x/y#1", Priority="P0", Effort=1, parent=P))
        picks, skipped = board.select(WORK, s, repo="o/r", count=20, claimed=lambda repo: {"o/r#8"})
        self.assertEqual([e["ref"] for e in picks], ["o/r#4", "o/r#3", "o/r#2", "o/r#1"])
        self.assertEqual(dict(skipped), {"o/r#5": "needs grooming: no Effort", "o/r#8": "claimed in STATUS.md",
                                         "o/r#10": "assigned to someone", "o/r#11": "blocked by o/r#12",
                                         "o/r#13": "needs grooming: no Theme, Complexity, parent link"})

    def test_label_filter(self):
        s = snap(item("o/r#1", Priority="P1", Effort=1, parent="o/r#9", labels=["ops:pipeline"]),
                 item("o/r#2", Priority="P0", Effort=1, parent="o/r#9"))
        picks, _ = board.select(WORK, s, label="ops:pipeline", claimed=lambda r: set())
        self.assertEqual([e["ref"] for e in picks], ["o/r#1"])


class Hygiene(unittest.TestCase):
    def test_findings(self):
        today = dt.datetime(2026, 11, 20, tzinfo=dt.timezone.utc)
        s = snap(item("acme-co/ops#1", status="In Progress", Category="Epic", Priority="P1", Effort=3,
                      updated="2026-11-01T00:00:00Z", children=["acme-co/ops#3", "acme-co/ops#9"]),
                 item("acme-co/ops#2", status="In Progress", state="CLOSED", Category="User Story", parent="acme-co/ops#1",
                      Priority="P1", Effort=1, updated="2026-11-19T00:00:00Z"),
                 item("acme-co/ops#3", typ="Task", parent="acme-co/ops#1", Priority="P1", Effort=1),
                 item("acme-co/ops#4", typ="Task", status="Done", Priority="P1", Effort=1),
                 item("acme-co/ops#5", typ="Task", Category="User Story", parent="acme-co/ops#3", Priority="P1", Effort=1),
                 item("jdoe/tasks#1", typ="Task", parent="acme-co/ops#2", Priority="P1", Effort=1),
                 item("acme-co/ops#7", title="[Test fixture] x", state="CLOSED", labels=["test-fixture"]),
                 item("acme-co/ops#8", title="Real, wrongly labelled", Category="Epic", Priority="P1", Effort=1,
                      labels=["test-fixture"]))
        got = {(k, r, m) for k, r, m in board.hygiene(WORK, s, today=today)}
        want = {("stale", "acme-co/ops#1", "In Progress, not updated for 19 days"),
                ("status", "acme-co/ops#2", "closed but Status is 'In Progress'"),
                ("level", "acme-co/ops#3", "Task under Epic acme-co/ops#1 skips User Story"),
                ("status", "acme-co/ops#4", "Status is Done but the issue is open"),
                ("orphan", "acme-co/ops#4", "Task with no parent"),
                ("level", "acme-co/ops#5", "has Category 'User Story' and type 'Task'"),
                ("level", "acme-co/ops#5", "User Story under Task acme-co/ops#3 (not lower)"),
                ("cross-owner", "jdoe/tasks#1", "issue from another owner on the company board"),
                ("missing", "acme-co/ops#9", "sub-issue of acme-co/ops#1 but not on the board"),
                ("missing", "acme-co/ops#1", "no assignee"),
                ("missing", "acme-co/ops#1", "no parent link"),   # an Epic sits under a Milestone on this board
                ("missing", "acme-co/ops#8", "no parent link")}
        self.assertEqual(got, want)

    def test_fixture_included_on_request(self):
        s = snap(item("acme-co/ops#7", title="[Test fixture] x", state="CLOSED", typ="Task", parent="acme-co/ops#6",
                      labels=["test-fixture"]))
        self.assertEqual(board.hygiene(WORK, s), [])
        self.assertEqual([k for k, _, _ in board.hygiene(WORK, s, include_fixture=True)], ["status"])


class TreeAndXrefs(unittest.TestCase):
    def test_tree_counts(self):
        s = snap(item("o/r#1", Category="Epic", children=["o/r#2", "o/r#3"]),
                 item("o/r#2", typ="Task", parent="o/r#1", state="CLOSED", status="Done"),
                 item("o/r#3", typ="Task", parent="o/r#1"))
        out = board.tree(WORK, s, "o/r#1")
        self.assertIn("  o/r#2  [Task] Done  x", out)
        self.assertTrue(out.endswith("counts: Epic 1 open, 0 closed; Task 1 open, 1 closed"))

    def test_xrefs(self):
        s = snap(item("o/r#1", Source_Org="Acme", Target_Org="globex"), item("o/r#2", Source_Org="Acme"))
        self.assertEqual([r for r, *_ in board.xrefs(WORK, s)], ["o/r#1"])


class StatusMd(unittest.TestCase):
    def test_claim_and_finish_round_trip(self):
        text = "# STATUS\n\n## What's in progress\n\n- Nothing in flight.\n\n## What's next\n\n1. x\n"
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
            f.write(text)
        url = "https://github.com/o/r/issues/5"
        board.status_md_claim(f.name, "o/r#5", url, "Do it")
        got = board.read_text(f.name)
        self.assertIn(f"## What's in progress\n\n- [o/r#5]({url}) Do it — claimed ", got)
        self.assertNotIn("Nothing in flight", got)
        self.assertEqual(board.status_md_finish(f.name, url), 1)
        self.assertNotIn(url, board.read_text(f.name))
        os.unlink(f.name)

    def test_finish_removes_only_the_claim_line(self):
        url = "https://github.com/o/r/issues/5"
        text = ("# STATUS\n\n## What just happened\n\n- Landed [o/r#5](" + url + ") last week\n\n"
                "## What's in progress\n\n- [o/r#5](" + url + ") Do it — claimed 2026-11-11\n"
                "- [o/r#50](" + url + "0) Other — claimed 2026-11-11\n\n## What's next\n")
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
            f.write(text)
        self.assertEqual(board.status_md_finish(f.name, url), 1)
        got = board.read_text(f.name)
        self.assertIn("Landed [o/r#5]", got)
        self.assertIn("[o/r#50]", got)
        os.unlink(f.name)

    def test_claim_into_existing_list_and_into_prose(self):
        for body, want in (("- [o/r#1](u1) First — claimed x\n", "## What's in progress\n\n- [o/r#5](u) T — claimed"),
                           ("Some prose.\n", "## What's in progress\n\n- [o/r#5](u) T — claimed")):
            with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
                f.write("## What's in progress\n\n" + body + "\n## What's next\n")
            board.status_md_claim(f.name, "o/r#5", "u", "T")
            got = board.read_text(f.name)
            self.assertTrue(got.startswith(want), got)
            os.unlink(f.name)

    def test_claim_needs_section(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
            f.write("# STATUS\n")
        with self.assertRaisesRegex(board.BoardError, "no \"## What's in progress\""):
            board.status_md_claim(f.name, "o/r#5", "u", "t")
        os.unlink(f.name)


class ResetFixture(unittest.TestCase):
    def test_plan_reopens_and_clears_fixture_only(self):
        s = snap(item("acme-co/ops#6", title="[Test fixture] T1", labels=["test-fixture"], state="CLOSED", status="Done",
                      Priority="P2", Effort=2, Target_Org="globex"),
                 item("acme-co/ops#4", title="[Test fixture] Epic", labels=["test-fixture"], status="Backlog", Category="Epic"),
                 item("acme-co/ops#1", title="Real", status="Todo", Priority="P1"))
        plan = board.reset_fixture_plan(WORK, s)
        self.assertEqual(plan, [{"op": "reopen", "item": "acme-co/ops#6"},
                                {"op": "set_field", "item": "acme-co/ops#6", "field": "Status", "value": "Backlog"},
                                {"op": "clear_field", "item": "acme-co/ops#6", "field": "Priority"},
                                {"op": "clear_field", "item": "acme-co/ops#6", "field": "Effort"},
                                {"op": "clear_field", "item": "acme-co/ops#6", "field": "Target Org"}])
        _, reasons = board.check_plan(WORK, s, plan, no_lookup)
        self.assertEqual(reasons, [])

    def test_personal_rest_is_backlog(self):
        s = snap(item("jdoe/tasks#5", title="[Test fixture] T1", labels=["test-fixture"], status="Todo"))
        s["fields"]["Status"]["options"] = OPTS("Todo", "Backlog", "In Progress", "In Review", "Done")
        plan = board.reset_fixture_plan(BOARDS["personal"], s)
        self.assertEqual(plan, [{"op": "set_field", "item": "jdoe/tasks#5", "field": "Status", "value": "Backlog"}])
        _, reasons = board.check_plan(BOARDS["personal"], s, plan, no_lookup)
        self.assertEqual(reasons, [])

    def test_board_without_a_rest_status_clears_status(self):
        s = snap(item("jdoe/tasks#5", title="[Test fixture] T1", labels=["test-fixture"], status="Todo"))
        b = {k: v for k, v in BOARDS["personal"].items() if k != "fixture_rest"}
        self.assertEqual(board.reset_fixture_plan(b, s),
                         [{"op": "clear_field", "item": "jdoe/tasks#5", "field": "Status"}])


class Cli(unittest.TestCase):
    def test_unknown_flags_and_wrong_counts_rejected(self):
        with self.assertRaisesRegex(board.BoardError, "does not take --dry-run"):
            board.parse(["apply", "company", "plan.json", "--dry-run"])
        with self.assertRaisesRegex(board.BoardError, "takes 2 argument"):
            board.parse(["apply", "company"])
        with self.assertRaisesRegex(board.BoardError, "needs a value"):
            board.parse(["select", "company", "--repo"])
        with self.assertRaisesRegex(board.BoardError, "board names or --all"):
            board.parse(["snapshot"])
        self.assertEqual(board.parse(["apply", "company", "p.json", "--approved"]), ("apply", ["company", "p.json"], {"--approved": True}))


class Config(unittest.TestCase):
    def test_boards_merge_defaults(self):
        self.assertEqual(BOARDS["personal"]["statuses"]["claim"], "In Progress")
        self.assertEqual(BOARDS["company"]["stale_days"], 7)
        self.assertTrue(BOARDS["globex"]["read_only"])
        self.assertEqual(board.levels(BOARDS["personal"]), ["Epic", "User Story", "Task"])


if __name__ == "__main__":
    unittest.main()
