"""Offline tests for the rules and commands beyond plain field edits: required fields, readiness,
hierarchy direction, mentions, relationships, pull requests, releases, freshness and notes."""
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "template", "board", ".local", "bin", "board")
loader = importlib.machinery.SourceFileLoader("board_features_under_test", SRC)
spec = importlib.util.spec_from_loader("board_features_under_test", loader)
board = importlib.util.module_from_spec(spec)
loader.exec_module(board)

from test_board import FULL, item, no_lookup, snap  # noqa: E402  (same fixtures as the plan tests)

BOARDS = board.load_config(os.path.join(HERE, "boards.test.json"))
WORK = BOARDS["company"]


def tree_snap(*extra):
    return snap(item("acme-co/ops#1", Category="Epic", Priority="P1"),
                item("acme-co/ops#2", Category="User Story", parent="acme-co/ops#1", Priority="P1", Effort=2),
                item("acme-co/ops#3", parent="acme-co/ops#2", Priority="P1", Effort=1),
                *extra)


def check(plan, s=None, lookup=no_lookup, **kw):
    return board.check_plan(WORK, s or tree_snap(), plan, lookup, **kw)


class RequiredFields(unittest.TestCase):
    def test_create_without_required_fields_is_refused_with_the_list(self):
        with self.assertRaisesRegex(board.BoardError, "needs Status, Priority, Theme, Complexity, Type$"):
            check([{"op": "create", "repo": "acme-co/ops", "title": "t", "parent": "acme-co/ops#2",
                    "fields": {}, "type": None}])

    def test_effort_only_on_stories_and_tasks(self):
        epic = {"op": "create", "repo": "acme-co/ops", "title": "e", "type": "Feature", "parent": None,
                "fields": {"Status": "Backlog", "Priority": "P2", "Theme": "Placeholder", "Complexity": "Low",
                           "Category": "Epic"}}
        with self.assertRaisesRegex(board.BoardError, "parent link"):
            check([epic])  # an Epic sits under a Milestone on this board
        check([dict(epic, parent="acme-co/ops#9")], s=tree_snap(item("acme-co/ops#9", Category="Milestone", Priority="P1")))

    def test_parent_type_needs_a_category(self):
        with self.assertRaisesRegex(board.BoardError, "Category"):
            check([dict(FULL, op="create", repo="acme-co/ops", title="t", type="Feature")])

    def test_todo_at_create_needs_a_done_when_line(self):
        todo = dict(FULL, op="create", repo="acme-co/ops", title="t", fields=dict(FULL["fields"], Status="Todo"))
        with self.assertRaisesRegex(board.BoardError, "done-when"):
            check([todo])
        check([dict(todo, body="Context.\n\n**Done when:** the report runs.")])

    def test_move_to_todo_checks_fields_and_body(self):
        s = tree_snap(item("acme-co/ops#4", status="Backlog", parent="acme-co/ops#2", Priority="P1"))  # no Effort
        move = [{"op": "set_field", "item": "acme-co/ops#4", "field": "Status", "value": "Todo"}]
        with self.assertRaisesRegex(board.BoardError, "can't move to Todo: no Effort"):
            check(move, s=s, body_of=lambda r: "Done when: x")
        fixed = [{"op": "set_field", "item": "acme-co/ops#4", "field": "Effort", "value": 2}] + move
        with self.assertRaisesRegex(board.BoardError, "done-when"):
            check(fixed, s=s, body_of=lambda r: "no marker here")
        check(fixed, s=s, body_of=lambda r: "## Done when\nIt works.")

    def test_parent_and_type_set_earlier_in_the_plan_count_for_todo(self):
        s = tree_snap(item("acme-co/ops#4", status="Backlog", typ=None, Priority="P1", Effort=1))  # no parent, no type
        check([{"op": "set_type", "item": "acme-co/ops#4", "type": "Task"},
               {"op": "attach", "parent": "acme-co/ops#2", "child": "acme-co/ops#4"},
               {"op": "set_field", "item": "acme-co/ops#4", "field": "Status", "value": "Todo"}],
              s=s, body_of=lambda r: "Done when: it works")

    def test_what_done_looks_like_heading_counts(self):
        self.assertTrue(board.has_done_marker(WORK, "## What done looks like\nThe export runs."))
        self.assertTrue(board.has_done_marker(WORK, "**Done when:** x"))
        self.assertFalse(board.has_done_marker(WORK, "We are done with this when it works"))

    def test_parent_optional_levels_need_no_parent(self):
        standalone = dict(WORK, parent_optional=["Task"])
        task = dict(FULL, op="create", repo="acme-co/ops", title="t", parent=None)
        with self.assertRaisesRegex(board.BoardError, "parent link .*parent_optional"):
            check([task])
        board.check_plan(standalone, tree_snap(), [task], no_lookup)
        s = tree_snap(item("acme-co/ops#4", Priority="P1", Effort=1, assignees=()))
        self.assertIn(("orphan", "acme-co/ops#4", "Task with no parent"), set(board.hygiene(WORK, s)))
        self.assertNotIn(("orphan", "acme-co/ops#4", "Task with no parent"), set(board.hygiene(standalone, s)))

    def test_fixture_creates_are_exempt(self):
        check([{"op": "create", "repo": "acme-co/ops", "title": "[Test fixture] t", "labels": ["test-fixture"]}])


class Hierarchy(unittest.TestCase):
    def test_upside_down_attach_is_refused(self):
        with self.assertRaisesRegex(board.BoardError, "puts a level under the same or a lower one"):
            check([{"op": "attach", "parent": "acme-co/ops#3", "child": "acme-co/ops#2"}])
        with self.assertRaisesRegex(board.BoardError, "same or a lower"):
            check([{"op": "attach", "parent": "acme-co/ops#2",
                    "child": "acme-co/ops#5"}], s=tree_snap(item("acme-co/ops#5", Category="User Story", Priority="P1", Effort=1)))

    def test_skipped_level_is_allowed(self):
        _, reasons = check([{"op": "attach", "parent": "acme-co/ops#1", "child": "acme-co/ops#3"}])
        self.assertIn("op 1: attach", reasons)

    def test_a_level_changed_earlier_in_the_plan_counts(self):
        s = tree_snap(item("acme-co/ops#5", Category="User Story", parent="acme-co/ops#1", Priority="P1", Effort=1))
        check([{"op": "clear_field", "item": "acme-co/ops#5", "field": "Category"},
               {"op": "attach", "parent": "acme-co/ops#2", "child": "acme-co/ops#5"}], s=s)
        with self.assertRaisesRegex(board.BoardError, "same or a lower"):
            check([{"op": "set_field", "item": "acme-co/ops#3", "field": "Category", "value": "Epic"},
                   {"op": "attach", "parent": "acme-co/ops#2", "child": "acme-co/ops#3"}])

    def test_upside_down_create_is_refused(self):
        with self.assertRaisesRegex(board.BoardError, "same or a lower"):
            check([dict(FULL, op="create", repo="acme-co/ops", title="t", parent="acme-co/ops#3")])

    def test_promotion_sets_the_parent_type_and_demotion_the_leaf_type(self):
        promote = [{"op": "set_field", "item": "acme-co/ops#3", "field": "Category", "value": "User Story"},
                   {"op": "attach", "parent": "acme-co/ops#1", "child": "acme-co/ops#3"}]
        steps, _ = check(promote)
        self.assertEqual([(op["op"], op.get("type")) for _, op, _ in steps],
                         [("set_field", None), ("set_type", "Feature"), ("attach", None)])
        with self.assertRaisesRegex(board.BoardError, "same or a lower"):
            check(promote[:1])  # a User Story left under a User Story
        steps, _ = check([{"op": "clear_field", "item": "acme-co/ops#2", "field": "Category"}])
        self.assertEqual([op.get("type") for _, op, _ in steps], [None, "Task"])
        steps, _ = check([{"op": "set_field", "item": "acme-co/ops#3", "field": "Category", "value": "User Story"},
                          {"op": "set_type", "item": "acme-co/ops#3", "type": "Bug"},
                          {"op": "attach", "parent": "acme-co/ops#1", "child": "acme-co/ops#3"}])
        self.assertEqual(len(steps), 3, "a plan that sets the type itself gets no implied op")


class MentionsAndLinks(unittest.TestCase):
    def test_another_owners_issue_in_text_is_refused(self):
        for text in ("see globex/web#4", "see https://github.com/globex/web/issues/4", "and globex/web#12."):
            with self.subTest(text=text), self.assertRaisesRegex(board.BoardError, "mentions .* from another owner"):
                check([dict(FULL, op="create", repo="acme-co/ops", title="t", body=text)])

    def test_own_owner_mentions_and_plain_numbers_pass(self):
        check([dict(FULL, op="create", repo="acme-co/ops", title="t",
                    body="Follows acme-co/ops#1 and #3; see https://github.com/acme-co/ops/issues/2")])

    def test_relationships_take_any_owner_and_need_the_issue_to_exist(self):
        lookup = lambda r: dict(owner=r.split("/")[0], title="t", labels=[], parent=None)
        steps, reasons = check([{"op": "relate", "item": "acme-co/ops#3", "other": "jdoe/tasks#1"},
                                {"op": "block", "item": "acme-co/ops#3", "by": "globex/web#2"}], lookup=lookup)
        self.assertEqual(len(steps), 2)
        self.assertEqual(reasons, [], "relationships apply without review")

        def missing(r):
            raise board.BoardError(f"no issue {r}")
        with self.assertRaisesRegex(board.BoardError, "no issue jdoe/tasks#99"):
            check([{"op": "relate", "item": "acme-co/ops#3", "other": "jdoe/tasks#99"}], lookup=missing)
        with self.assertRaisesRegex(board.BoardError, "itself"):
            check([{"op": "block", "item": "acme-co/ops#3", "by": "acme-co/ops#3"}])

    def test_duplicate_of_another_owner_needs_the_flag(self):
        lookup = lambda r: dict(owner=r.split("/")[0], title="[Test fixture] t", labels=["test-fixture"], parent=None)
        with self.assertRaisesRegex(board.BoardError, "crosses owners"):
            check([{"op": "close", "item": "acme-co/ops#3", "duplicate_of": "jdoe/tasks#1"}], lookup=lookup)

    def test_add_pr_checks_the_owner(self):
        pr = lambda r: dict(owner=r.split("/")[0], closes=[])
        steps, _ = check([{"op": "add_pr", "pr": "acme-co/ops#40"}], pr_info=pr)
        self.assertEqual(steps[0][1]["pr"], "acme-co/ops#40")
        with self.assertRaisesRegex(board.BoardError, "crosses owners"):
            check([{"op": "add_pr", "pr": "globex/web#4"}], pr_info=pr)


def pr_item(ref, state="OPEN", status="In Review", merged=False):
    return {"item_id": "PVTI_" + ref, "kind": "PULL_REQUEST", "archived": False, "title": "pr", "fields": {"Status": status},
            "pr_ref": ref, "pr_id": "PR_" + ref, "state": state, "merged": merged, "url": "u", "draft": False, "closes": []}


class PullRequestHygiene(unittest.TestCase):
    def kinds(self, s, b=WORK, **kw):
        return {(k, r, m) for k, r, m in board.hygiene(b, s, **kw) if k == "pull request" or k == "status"}

    def test_open_pull_request_needs_in_review(self):
        s = tree_snap(item("acme-co/ops#4", status="In Progress", parent="acme-co/ops#2", Priority="P1", Effort=1,
                           assignees=["me"], prs=[{"ref": "acme-co/ops#40", "state": "OPEN", "merged": False}]))
        self.assertIn(("pull request", "acme-co/ops#4", "acme-co/ops#40 is open but Status is 'In Progress', not 'In Review'"),
                      self.kinds(s))

    def test_in_review_without_a_pull_request(self):
        s = tree_snap(item("acme-co/ops#4", status="In Review", parent="acme-co/ops#2", Priority="P1", Effort=1, assignees=["me"]))
        self.assertIn(("pull request", "acme-co/ops#4", "In Review with no open pull request"), self.kinds(s))

    def test_closed_with_an_open_pull_request(self):
        s = tree_snap(item("acme-co/ops#4", status="Done", state="CLOSED", parent="acme-co/ops#2",
                           prs=[{"ref": "acme-co/ops#41", "state": "OPEN", "merged": False}]))
        self.assertIn(("pull request", "acme-co/ops#4", "closed while acme-co/ops#41 is still open, but Status is 'Done', not 'In Review'"),
                      self.kinds(s))
        ok = tree_snap(item("acme-co/ops#4", status="In Review", state="CLOSED", parent="acme-co/ops#2",
                            prs=[{"ref": "acme-co/ops#41", "state": "OPEN", "merged": False}]))
        self.assertEqual({x for x in self.kinds(ok) if x[1] == "acme-co/ops#4"}, set(), "closed at In Review is expected")

    def test_pending_release_rules_follow_the_release_setting(self):
        s = tree_snap(item("acme-co/ops#4", status="Pending Release", state="CLOSED", parent="acme-co/ops#2"))
        self.assertIn(("status", "acme-co/ops#4", "Pending Release on a board with no release process (release: none)"),
                      self.kinds(s))
        tags = dict(WORK, release="tags")
        self.assertEqual({x for x in self.kinds(s, b=tags) if x[1] == "acme-co/ops#4"}, set())

    def test_pull_requests_on_the_board_and_unlinked_ones(self):
        s = tree_snap(pr_item("acme-co/ops#50", status="Todo"), pr_item("acme-co/ops#51", state="MERGED", status="In Review",
                                                                         merged=True))
        got = self.kinds(dict(s), b=dict(WORK, repos=["acme-co/ops"]), open_prs=lambda repo, pid: ["acme-co/ops#60"])
        self.assertIn(("pull request", "acme-co/ops#50", "open pull request on the board at 'Todo', not 'In Review'"), got)
        self.assertIn(("pull request", "acme-co/ops#51", "merged pull request at 'In Review'"), got)
        self.assertIn(("pull request", "acme-co/ops#60", "open, closes no issue, and isn't on the company board"), got)


class Release(unittest.TestCase):
    def setUp(self):
        self.saved = board.pull, board.apply_plan
        self.plans = []
        board.apply_plan = lambda b, boards, plan, **kw: self.plans.append(plan) or board.APPLIED

    def tearDown(self):
        board.pull, board.apply_plan = self.saved

    def test_items_move_to_done_only_when_every_merged_pr_is_in_the_tag(self):
        merged = lambda oid: {"ref": "acme-co/ops#90", "state": "MERGED", "merged": True, "merge_oid": oid}
        s = tree_snap(item("acme-co/ops#4", status="Pending Release", state="CLOSED", prs=[merged("a1")]),
                      item("acme-co/ops#5", status="Pending Release", state="CLOSED", prs=[merged("a1"), merged("b2")]),
                      item("acme-co/web#6", status="Pending Release", state="CLOSED", prs=[merged("a1")]))
        board.pull = lambda b, write=True: s
        rc = board.release(dict(WORK, release="tags"), BOARDS, "acme-co/ops", "v1", included=lambda repo, oid, tag: oid == "a1",
                           log=lambda *_: None)
        self.assertEqual(rc, board.APPLIED)
        self.assertEqual(self.plans, [[{"op": "set_field", "item": "acme-co/ops#4", "field": "Status", "value": "Done"}]])


class Guard(unittest.TestCase):
    def run_guard(self, issue_status, open_prs, board_cfg=None, later_prs=None, later_status=None, on_board=True,
                  logs=None, state="CLOSED", returns=None, slept=None):
        """open_prs on arrival; later_prs / later_status: what the recheck sees (another merge, the
        board's own "Item closed" landing late, or a release moving the item). returns: what each
        apply_plan call reports, in order. Returns (Status values written, guard's exit code)."""
        plans, status, calls = [], {"v": issue_status}, {"pr": 0}
        returns = list(returns or [])

        class GH:
            def pr(self, ref):
                calls["pr"] += 1
                prs = open_prs if calls["pr"] == 1 or later_prs is None else later_prs
                return dict(id="PR", owner="acme-co", state="MERGED", merged=True, url="u",
                            closes=[dict(id="I4", ref="acme-co/ops#4", state=state, open_prs=prs)])

        def sleep(s):
            if slept is not None:
                slept.append(s)
            if later_status is not None:
                status["v"] = later_status
        b = board_cfg or WORK
        saved = board.gql, board.pull, board.apply_plan
        board.gql = lambda q, **v: (_ for _ in ()).throw(AssertionError("no direct GitHub writes"))
        board.pull = lambda bb, write=True: tree_snap(*([item("acme-co/ops#4", status=status["v"], state="CLOSED")]
                                                        if on_board else []))

        def apply(bb, boards, plan, **kw):
            plans.append(plan)
            status["v"] = plan[0]["value"]
            return returns.pop(0) if returns else board.APPLIED
        board.apply_plan = apply
        try:
            rc = board.guard({"company": b}, "acme-co/ops#40", gh=GH(), sleep=sleep,
                             log=(logs.append if logs is not None else lambda *_: None))
        finally:
            board.gql, board.pull, board.apply_plan = saved
        return [op["value"] for p in plans for op in p], rc

    def written(self, *a, **kw):
        return self.run_guard(*a, **kw)[0]

    def test_another_open_pr_keeps_the_issue_in_review_without_reopening(self):
        self.assertEqual(self.written("Done", ["acme-co/ops#41"]), ["In Review"])

    def test_the_last_merge_sets_done_or_pending_release(self):
        self.assertEqual(self.written("In Review", []), ["Done"])
        self.assertEqual(self.written("In Review", [], dict(WORK, release="tags")), ["Pending Release"])

    def test_nothing_to_do_when_status_is_already_right(self):
        self.assertEqual(self.written("Done", []), [])

    def test_recheck_restores_in_review_when_item_closed_lands_after_the_first_read(self):
        self.assertEqual(self.written("In Review", ["acme-co/ops#41"], later_status="Done"), ["In Review"])

    def test_recheck_sets_done_when_the_other_pr_merged_meanwhile(self):
        self.assertEqual(self.written("Done", ["acme-co/ops#41"], later_prs=[]), ["In Review", "Done"])

    def test_recheck_keeps_a_release_moving_the_item_to_done(self):
        self.assertEqual(self.written("In Review", [], dict(WORK, release="tags"), later_status="Done"),
                         ["Pending Release"])

    def test_a_reopened_issue_is_left_alone(self):
        logs = []
        self.assertEqual(self.written("In Progress", [], state="OPEN", logs=logs), [])
        self.assertTrue(any("open again" in m for m in logs), logs)

    def test_a_recheck_that_fixes_the_board_clears_the_first_passes_failure(self):
        out, rc = self.run_guard("In Review", ["acme-co/ops#41"], later_status="Done", returns=[board.APPLIED])
        self.assertEqual(rc, board.APPLIED)
        out, rc = self.run_guard("Done", ["acme-co/ops#41"], later_status="Done", returns=[board.FAILED, board.APPLIED])
        self.assertEqual((out, rc), (["In Review", "In Review"], board.APPLIED))

    def test_a_recheck_that_finds_the_board_right_clears_the_first_passes_failure(self):
        self.assertEqual(self.run_guard("Done", ["acme-co/ops#41"], returns=[board.FAILED]), (["In Review"], board.APPLIED))
        self.assertEqual(self.run_guard("In Review", [], returns=[board.FAILED]), (["Done"], board.APPLIED))

    def test_recheck_off_at_zero_and_skipped_when_nothing_is_on_a_board(self):
        slept = []
        self.written("Done", ["acme-co/ops#41"], dict(WORK, guard_recheck_seconds=0), later_status="Done", slept=slept)
        self.written("Done", [], on_board=False, slept=slept)
        self.assertEqual(slept, [])

    def test_an_issue_on_no_board_is_reported(self):
        logs = []
        self.assertEqual(self.written("Done", [], on_board=False, logs=logs), [])
        self.assertTrue(any("not on company" in m for m in logs), logs)


class StateFolder(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.saved = board.STATE, board.CACHE, board.snapshot
        board.STATE = board.CACHE = self.dir

    def tearDown(self):
        board.STATE, board.CACHE, board.snapshot = self.saved
        shutil.rmtree(self.dir)

    def write(self, s):
        board.write_snapshot_file(WORK, s)

    def test_stale_snapshot_is_pulled_again(self):
        old = tree_snap()
        old["taken"] = (board.now() - dt.timedelta(hours=25)).isoformat()
        self.write(old)
        pulled = []
        board.snapshot = lambda b, write=True: pulled.append(b["name"]) or tree_snap()
        board.load_snapshot(WORK)
        self.assertEqual(pulled, ["company"])
        fresh = tree_snap()
        fresh["taken"] = board.now().isoformat()
        self.write(fresh)
        board.load_snapshot(WORK)
        self.assertEqual(pulled, ["company"], "a fresh snapshot is used as it is")

    def test_notes_are_appended_marked_stale_and_kept_across_a_refresh(self):
        s = tree_snap()
        s["taken"] = board.now().isoformat()
        self.write(s)
        board.add_note(WORK, "acme-co/ops#3", "duplicate candidate", "acme-co/ops#2", "agent-a", snap_loader=lambda b: None)
        board.add_note(WORK, "acme-co/ops#3", "readiness", "ready", "agent-b", snap_loader=lambda b: None)
        got = board.notes(board.read_snapshot_file(WORK), "acme-co/ops#3")
        self.assertEqual([(x["kind"], x["value"], x["by"], x["stale"]) for x in got],
                         [("duplicate candidate", "acme-co/ops#2", "agent-a", False), ("readiness", "ready", "agent-b", False)])
        self.assertEqual(got[0]["basis_updated"], "2026-01-01T00:00:00Z")

    def test_refresh_keeps_analysis_by_ref(self):
        s = tree_snap()
        s["items"][2]["analysis"] = [{"kind": "k", "value": "v", "by": "a", "at": "t", "basis_updated": "2026-01-01T00:00:00Z"}]
        self.write(s)
        node = {"id": "PVTI_acme-co/ops#3", "type": "ISSUE", "isArchived": False, "updatedAt": "2026-12-01T00:00:00Z",
                "fieldValues": {"nodes": []},
                "content": {"id": "I3", "number": 3, "title": "x", "state": "OPEN", "stateReason": None,
                            "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-12-01T00:00:00Z", "url": "u",
                            "repository": {"nameWithOwner": "acme-co/ops"}, "issueType": {"name": "Task"},
                            "labels": {"nodes": []}, "assignees": {"nodes": []}, "parent": None,
                            "subIssues": {"nodes": []}, "blockedBy": {"nodes": []},
                            "closedByPullRequestsReferences": {"nodes": []}}}
        saved_fields, saved_gql = board.fields, board.gql
        board.fields = lambda b: {"project_id": "PVT_x", "title": "t", "fields": s["fields"]}
        board.gql = lambda q, **v: {"organization": {"projectV2": {"items": {"pageInfo": {"hasNextPage": False},
                                                                              "nodes": [node]}}}}
        try:
            board.snapshot = self.saved[2]
            board.snapshot(WORK)
        finally:
            board.fields, board.gql = saved_fields, saved_gql
        got = board.notes(board.read_snapshot_file(WORK), "acme-co/ops#3")
        self.assertEqual([(x["kind"], x["stale"]) for x in got], [("k", True)])


class ConfigAndRepos(unittest.TestCase):
    def test_defaults_merge_deeply(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"boards": {"x": {"owner": "o", "owner_type": "organization", "number": 1, "hierarchy": ["Epic"],
                                    "statuses": {"done": "Shipped"}, "repos": ["o/a"]}}}, tmp)
        tmp.close()
        try:
            b = board.load_config(tmp.name)["x"]
        finally:
            os.unlink(tmp.name)
        self.assertEqual((b["statuses"]["done"], b["statuses"]["select"], b["fixture"]["label"]), ("Shipped", "Todo", "test-fixture"))
        self.assertEqual(board.board_for_repo({"x": b}, "o/a")["name"], "x")
        with self.assertRaisesRegex(board.BoardError, "no board"):
            board.board_for_repo({"x": b}, "o/zzz")

    def test_finish_removes_only_the_claim_line(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        url = "https://github.com/o/r/issues/5"
        tmp.write(f"# S\n\n## What's in progress\n\n- [o/r#5]({url}) five — claimed 2026-01-01\n"
                  f"- [o/r#6](https://github.com/o/r/issues/6) six, blocked on [o/r#5]({url})\n\n## What's next\n")
        tmp.close()
        try:
            self.assertEqual(board.status_md_finish(tmp.name, url), 1)
            text = open(tmp.name).read()
        finally:
            os.unlink(tmp.name)
        self.assertIn("o/r#6", text)


if __name__ == "__main__":
    unittest.main()
