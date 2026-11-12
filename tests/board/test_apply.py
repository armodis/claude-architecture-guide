"""Offline tests of apply_plan with GitHub faked: the auto-add race, plans that stop part-way,
and side effects reported as exit 3.  Run:  python3 -m unittest discover -s tests/board"""
import copy
import importlib.machinery
import importlib.util
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "template", "board", ".local", "bin", "board")
CONFIG = os.path.join(HERE, "boards.test.json")
loader = importlib.machinery.SourceFileLoader("board_apply_under_test", SRC)
board = importlib.util.module_from_spec(importlib.util.spec_from_loader("board_apply_under_test", loader))
loader.exec_module(board)

ALL = board.load_config(CONFIG)
BOARDS = {k: ALL[k] for k in ("company", "personal")}
OPTS = lambda *n: [{"id": f"id-{x}", "name": x, "color": "GRAY", "description": ""} for x in n]
FIELDS = {"Status": {"id": "F1", "type": "SINGLE_SELECT", "options": OPTS("Todo", "Backlog", "In Progress", "Done")},
          "Priority": {"id": "F2", "type": "SINGLE_SELECT", "options": OPTS("P1", "P2", "P3")}}


def it(ref, parent=None, state="OPEN", **f):
    return {"item_id": "PVTI_" + ref, "kind": "ISSUE", "archived": False, "title": "[Test fixture] " + ref, "fields": dict(f),
            "ref": ref, "issue_id": "I_" + ref, "state": state, "state_reason": None, "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z", "url": "u", "issue_type": "Task", "labels": ["test-fixture"], "parent": parent,
            "children": []}


def sn(name, items):
    return {"board": name, "taken": "2026-11-11T00:00:00+00:00", "project_id": "PVT_" + name, "fields": copy.deepcopy(FIELDS),
            "items": items}


BASE = [it("acme-co/ops#4"), it("acme-co/ops#5", parent="acme-co/ops#4")]
CREATE = {"op": "create", "repo": "acme-co/ops", "title": "[Test fixture] tmp", "type": "Task", "parent": "acme-co/ops#5",
          "labels": ["test-fixture"], "fields": {"Priority": "P3"}, "as": "tmp"}
AFTER = BASE + [it("acme-co/ops#9", parent="acme-co/ops#5")]


def run(plan, fail_on=None, after=None, after_personal=(), race=False, trim=False):
    """Apply a plan against faked boards: the first snapshots return BASE, later ones `after`."""
    count = {"n": 0}

    def fake_snapshot(b, write=True):
        count["n"] += 1
        late = count["n"] > 1 + len(BOARDS)
        if b["name"] == "company":
            return sn(b["name"], copy.deepcopy(after if late and after is not None else BASE))
        return sn(b["name"], copy.deepcopy(list(after_personal) if late else []))

    class GH:
        def issue(self, ref, fresh=False):
            parent = "acme-co/ops#5" if ref == "acme-co/ops#9" else None
            return dict(id="I_" + ref, owner=ref.split("/")[0], title="[Test fixture] x", state="OPEN", reason=None,
                        type="Task", labels=["test-fixture"], parent=parent)

        def repo(self, n):
            return {"id": "R", "types": {"Task": "T"}, "labels": {"test-fixture": "L"}}

    names = {}

    def fake_gql(q, **v):
        if fail_on and fail_on in q:
            raise board.BoardError("GitHub: Content already exists in this project" if race else "GitHub: simulated failure")
        if "createIssue" in q:
            return {"createIssue": {"issue": {"id": "I_acme-co/ops#9", "number": 9, "url": "u9",
                                              "repository": {"nameWithOwner": "acme-co/ops"}}}}
        if "addProjectV2ItemById" in q:
            return {"addProjectV2ItemById": {"item": {"id": "PVTI_new"}}}
        if "updateProjectV2Field(" in q:
            opts = [{"id": o.get("id") or "new-" + o["name"], "name": o["name"].strip() if trim else o["name"]} for o in v["o"]]
            names.update({o["id"]: o["name"] for o in opts})
            return {"updateProjectV2Field": {"projectV2Field": {"options": opts}}}
        if "updateProjectV2ItemFieldValue" in q:
            names["last"] = names.get(v["v"].get("singleSelectOptionId"))
            return {"x": {}}
        if "fieldValueByName" in q:
            return {"node": {"isArchived": False, "fieldValueByName": {"name": names.get("last") or "P3"}}}
        if "isArchived" in q:
            return {"node": {"isArchived": False}}
        return {"x": {}}

    saved = board.snapshot, board.GitHub, board.gql
    board.snapshot, board.GitHub, board.gql = fake_snapshot, GH, fake_gql
    log = []
    try:
        try:
            rc = board.apply_plan(BOARDS["company"], BOARDS, plan, approved=True, log=log.append)
        except board.BoardError as e:
            rc = str(e)
    finally:
        board.snapshot, board.GitHub, board.gql = saved
    return rc, log


class Apply(unittest.TestCase):
    def test_add_that_loses_the_auto_add_race_takes_the_existing_item(self):
        rc, log = run([CREATE], fail_on="addProjectV2ItemById", after=AFTER, race=True)
        self.assertEqual(rc, board.APPLIED, log)
        self.assertIn("     acme-co/ops#9 was already on company (auto-added)", log)

    def test_stopped_plan_reads_back_before_reporting(self):
        rc, log = run([CREATE, {"op": "close", "item": "$tmp", "reason": "not_planned"}], fail_on="addProjectV2ItemById", after=AFTER)
        self.assertIn("plan stopped part-way", rc)
        self.assertIn("  board company: acme-co/ops#9 appeared", log)

    def test_failed_create_with_a_later_alias_still_reports(self):
        rc, log = run([CREATE, {"op": "close", "item": "$tmp", "reason": "not_planned"}], fail_on="createIssue")
        self.assertIn("plan stopped part-way (GitHub: simulated failure)", rc)
        self.assertTrue(any("reading back every board" in l for l in log))

    def test_auto_add_onto_another_board_is_a_side_effect(self):
        rc, log = run([CREATE], after=AFTER, after_personal=[it("acme-co/ops#9", parent="acme-co/ops#5")])
        self.assertEqual(rc, board.SIDE_EFFECTS, log)
        self.assertIn("  board personal: acme-co/ops#9 appeared", log)

    PLAN_P0 = [{"op": "add_options", "field": "Priority", "options": ["P0"]},
               {"op": "set_field", "item": "acme-co/ops#4", "field": "Priority", "value": "P0"}]

    def test_options_added_earlier_in_the_plan_can_be_set(self):
        after = [it("acme-co/ops#4", Priority="P0"), it("acme-co/ops#5", parent="acme-co/ops#4")]
        rc, log = run(self.PLAN_P0, after=after)
        self.assertEqual(rc, board.APPLIED, log)

    def test_an_unplanned_change_in_an_edited_option_field_fails(self):
        after = [it("acme-co/ops#4", Priority="P0"), it("acme-co/ops#5", parent="acme-co/ops#4", Priority="P0")]
        rc, log = run(self.PLAN_P0, after=after)
        self.assertEqual(rc, board.FAILED, log)

    def test_option_names_github_changes_stop_the_plan_and_read_back(self):
        plan = [{"op": "add_options", "field": "Priority", "options": ["P0 "]}]
        rc, log = run(plan, after=BASE, trim=True)
        self.assertIn("plan stopped part-way", rc)
        self.assertTrue(any("reading back every board" in l for l in log), log)

    def test_shared_fields_are_not_changed_by_a_run(self):
        before = copy.deepcopy(FIELDS)
        run(self.PLAN_P0, after=BASE)
        self.assertEqual(FIELDS, before)

    def test_clean_create_applies(self):
        rc, log = run([CREATE], after=AFTER)
        self.assertEqual(rc, board.APPLIED, log)


if __name__ == "__main__":
    unittest.main()
