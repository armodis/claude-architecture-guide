"""Offline tests for agent coordination: the Agent and Responder fields, ask, answer, handoff, ack,
inbox, and the agent side of claim, finish, select and setup-agents. GitHub is a fake hub."""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "template", "board", ".local", "bin", "board")
loader = importlib.machinery.SourceFileLoader("board_agents_under_test", SRC)
spec = importlib.util.spec_from_loader("board_agents_under_test", loader)
board = importlib.util.module_from_spec(spec)
loader.exec_module(board)

from test_board import OPTS, item, snap  # noqa: E402

BOARDS = board.load_config(os.path.join(HERE, "boards.test.json"))
WORK = BOARDS["company"]
ME = {"BOARD_AGENT": "claude", "BOARD_MODEL": "Opus", "BOARD_SESSION": "s-1"}
AGENT_FIELDS = {"Agent": {"id": "FA", "type": "SINGLE_SELECT", "options": OPTS("claude", "codex", "Pat")},
                "Responder": {"id": "FR", "type": "SINGLE_SELECT", "options": OPTS("claude", "codex", "Pat")}}


def agent_snap(*items, with_fields=True):
    s = snap(*items)
    if with_fields:
        s["fields"].update(json.loads(json.dumps(AGENT_FIELDS)))
    return s


def pr_item(ref, closes=(), title="a pull request"):
    return {"item_id": "PVTI_" + ref, "kind": "PULL_REQUEST", "archived": False, "title": title, "fields": {},
            "pr_ref": ref, "pr_id": "PR_" + ref, "state": "OPEN", "merged": False, "draft": False,
            "url": "https://github.com/" + ref.replace("#", "/pull/"), "closes": list(closes)}


def open_pr(ref):
    return {"ref": ref, "state": "OPEN", "merged": False, "url": "https://github.com/" + ref.replace("#", "/pull/"),
            "merge_oid": None}


def marker(what, frm, to, at, cid="c", **kv):
    extra = "".join(f" {k}={v}" for k, v in kv.items())
    return {"id": cid, "url": "https://example.test/" + cid, "at": at,
            "body": f"<!-- board:{what} from={frm} to={to}{extra} -->\n**{to}**: text from {frm}.\n\n— {frm}"}


class FakeHub:
    """Stands in for GitHub. Records every write; reads come from the snapshot and the maps given."""

    def __init__(self, s, prs=None, items_by_query=None, notifications=(), readback=None, fail_boards=(), thread=()):
        self.s, self.prs, self._thread = s, prs or {}, list(thread)
        self.items_by_query, self.notes = items_by_query or {}, list(notifications)
        self.readback, self.fail_boards = readback, set(fail_boards)
        self.writes, self.values = [], {}
        for e in s["items"]:
            for f in ("Agent", "Responder"):
                if e["fields"].get(f) is not None:
                    self.values[(e["item_id"], f)] = e["fields"][f]

    def fields(self, b):
        if b["name"] in self.fail_boards:
            raise board.BoardError(f"can't read {b['name']}")
        return {"project_id": self.s["project_id"], "title": "t", "fields": self.s["fields"]}

    def snapshot(self, b):
        return self.s

    def set_field(self, meta, item_id, name, value):
        self.writes.append(("set", item_id, name, value))
        self.values[(item_id, name)] = value

    def clear_field(self, meta, item_id, name):
        self.writes.append(("clear", item_id, name))
        self.values.pop((item_id, name), None)

    def read_field(self, item_id, name):
        if self.readback is not None:
            return self.readback
        return self.values.get((item_id, name))

    def comment(self, subject_id, body):
        self.writes.append(("comment", subject_id, body))
        return f"https://example.test/comment/{len(self.writes)}"

    def review(self, pr_id, body):
        self.writes.append(("review", pr_id, body))
        return f"https://example.test/review/{len(self.writes)}"

    def request_review(self, pr_id, login):
        self.writes.append(("request_review", pr_id, login))

    def pr(self, ref):
        if ref not in self.prs:
            raise board.BoardError(f"no pull request {ref}")
        return self.prs[ref]

    def thread(self, subject_id):
        return self._thread

    def items(self, b, query):
        if b["name"] in self.fail_boards:
            raise board.BoardError(f"can't read {b['name']}")
        return self.items_by_query.get((b["name"], query), [])

    def notifications(self, since):
        return self.notes

    def create_field(self, project_id, name, options):
        self.writes.append(("create_field", name, tuple(options)))
        self.s["fields"][name] = {"id": "new-" + name, "type": "SINGLE_SELECT", "options": OPTS(*options)}

    def set_options(self, field, options):
        self.writes.append(("set_options", field["id"], tuple(o["name"] for o in options)))
        field["options"] = OPTS(*(o["name"] for o in options))

    def kinds(self):
        return [w[0] for w in self.writes]

    def comments(self):
        return [w[2] for w in self.writes if w[0] == "comment"]


def run(fn, *a, env=ME, **kw):
    saved = dict(os.environ)
    for k in ("BOARD_AGENT", "BOARD_MODEL", "BOARD_SESSION"):
        os.environ.pop(k, None)
    os.environ.update(env or {})
    logs = []
    try:
        rc = fn(*a, log=logs.append, **kw)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return rc, logs


ISSUE = "acme-co/ops#4"


class Ask(unittest.TestCase):
    def test_sets_responder_and_posts_a_marked_signed_comment(self):
        hub = FakeHub(agent_snap(item(ISSUE)))
        rc, logs = run(board.ask, WORK, ISSUE, "codex", "question", "Which field order?", hub=hub)
        self.assertEqual(rc, board.APPLIED)
        self.assertIn(("set", "PVTI_" + ISSUE, "Responder", "codex"), hub.writes)
        body = hub.comments()[0]
        self.assertIn("<!-- board:ask from=claude to=codex kind=question session=s-1 -->", body)
        self.assertIn("Which field order?", body)
        self.assertIn("— claude · Opus · session s-1", body)
        self.assertTrue(any("read back" in l and "ok" in l for l in logs))

    def test_agent_names_match_options_ignoring_case_and_are_never_mentioned(self):
        hub = FakeHub(agent_snap(item(ISSUE)))
        run(board.ask, WORK, ISSUE, "CODEX", "question", "x", hub=hub)
        self.assertIn(("set", "PVTI_" + ISSUE, "Responder", "codex"), hub.writes)
        self.assertNotIn("@codex", hub.comments()[0])

    def test_an_item_already_waiting_on_another_agent_is_refused_unless_forced(self):
        s = agent_snap(item(ISSUE, Responder="Pat"))
        with self.assertRaisesRegex(board.BoardError, "already waiting on Pat"):
            run(board.ask, WORK, ISSUE, "codex", "review", "x", hub=FakeHub(s))
        hub = FakeHub(s)
        run(board.ask, WORK, ISSUE, "codex", "question", "x", hub=hub, force=True)
        self.assertIn(("set", "PVTI_" + ISSUE, "Responder", "codex"), hub.writes)

    def test_needs_an_agent_name_that_is_an_option(self):
        with self.assertRaisesRegex(board.BoardError, "BOARD_AGENT"):
            run(board.ask, WORK, ISSUE, "codex", "question", "x", hub=FakeHub(agent_snap(item(ISSUE))), env={})
        with self.assertRaisesRegex(board.BoardError, "not an option.*claude, codex, Pat"):
            run(board.ask, WORK, ISSUE, "gemini", "question", "x", hub=FakeHub(agent_snap(item(ISSUE))))

    def test_kind_is_review_or_question(self):
        with self.assertRaisesRegex(board.BoardError, "review or question"):
            run(board.ask, WORK, ISSUE, "codex", "chat", "x", hub=FakeHub(agent_snap(item(ISSUE))))

    def test_a_board_without_the_field_names_board_setup(self):
        with self.assertRaisesRegex(board.BoardError, "Responder.*setup-agents"):
            run(board.ask, WORK, ISSUE, "codex", "question", "x", hub=FakeHub(agent_snap(item(ISSUE), with_fields=False)))

    def test_read_only_boards_refuse(self):
        with self.assertRaisesRegex(board.BoardError, "read-only"):
            run(board.ask, BOARDS["globex"], ISSUE, "codex", "question", "x", hub=FakeHub(agent_snap(item(ISSUE))))

    def test_text_that_mentions_another_owners_issue_is_refused(self):
        with self.assertRaisesRegex(board.BoardError, "globex/app#3"):
            run(board.ask, WORK, ISSUE, "codex", "question", "see globex/app#3", hub=FakeHub(agent_snap(item(ISSUE))))

    def test_a_review_ask_on_an_issue_names_its_open_pull_request(self):
        hub = FakeHub(agent_snap(item(ISSUE, prs=[open_pr("acme-co/ops#40")])))
        run(board.ask, WORK, ISSUE, "codex", "review", "please", hub=hub)
        self.assertIn("https://github.com/acme-co/ops/pull/40", hub.comments()[0])

    def test_a_pull_request_on_the_board_is_asked_about_on_itself(self):
        hub = FakeHub(agent_snap(pr_item("acme-co/ops#41")))
        run(board.ask, WORK, "acme-co/ops#41", "codex", "review", "please", hub=hub)
        self.assertIn(("set", "PVTI_acme-co/ops#41", "Responder", "codex"), hub.writes)
        self.assertEqual([w[1] for w in hub.writes if w[0] == "comment"], ["PR_acme-co/ops#41"])

    def test_a_pull_request_off_the_board_resolves_to_the_issue_it_closes(self):
        hub = FakeHub(agent_snap(item(ISSUE, prs=[open_pr("acme-co/ops#40")])),
                      prs={"acme-co/ops#40": {"id": "PR_40", "url": "u40", "state": "OPEN",
                                              "closes": [{"ref": ISSUE}]}})
        run(board.ask, WORK, "acme-co/ops#40", "codex", "review", "please", hub=hub)
        self.assertIn(("set", "PVTI_" + ISSUE, "Responder", "codex"), hub.writes)

    def test_asking_the_operator_for_a_review_uses_githubs_review_request(self):
        hub = FakeHub(agent_snap(item(ISSUE, prs=[open_pr("acme-co/ops#40")])),
                      prs={"acme-co/ops#40": {"id": "PR_40", "url": "u40", "state": "OPEN", "closes": [{"ref": ISSUE}]}})
        run(board.ask, WORK, ISSUE, "pat", "review", "please", hub=hub)
        self.assertIn(("request_review", "PR_40", "pat-example"), hub.writes)
        self.assertIn(("set", "PVTI_" + ISSUE, "Responder", "Pat"), hub.writes)

    def test_asking_the_operator_a_question_mentions_their_login(self):
        hub = FakeHub(agent_snap(item(ISSUE)))
        run(board.ask, WORK, ISSUE, "Pat", "question", "ok to drop it?", hub=hub)
        self.assertIn("@pat-example", hub.comments()[0])

    def test_a_write_that_does_not_read_back_fails(self):
        rc, _ = run(board.ask, WORK, ISSUE, "codex", "question", "x", hub=FakeHub(agent_snap(item(ISSUE)), readback="claude"))
        self.assertEqual(rc, board.FAILED)


class Answer(unittest.TestCase):
    def asked(self, **kw):
        return agent_snap(item(ISSUE, Responder="claude", Agent="codex", **kw))

    def test_clears_responder_and_answers_the_asker(self):
        hub = FakeHub(self.asked(), thread=[marker("ask", "codex", "claude", "2026-11-12T01:00:00Z", kind="question")])
        rc, _ = run(board.answer, WORK, ISSUE, "Yes, drop it.", hub=hub)
        self.assertEqual(rc, board.APPLIED)
        self.assertIn(("clear", "PVTI_" + ISSUE, "Responder"), hub.writes)
        body = hub.comments()[0]
        self.assertIn("<!-- board:answer from=claude to=codex session=s-1 -->", body)
        self.assertIn("Yes, drop it.", body)

    def test_with_no_ask_marker_the_answer_goes_to_the_items_agent(self):
        hub = FakeHub(self.asked())
        run(board.answer, WORK, ISSUE, "done", hub=hub)
        self.assertIn("to=codex", hub.comments()[0])

    def test_only_the_responder_answers_unless_forced(self):
        s = agent_snap(item(ISSUE, Responder="codex", Agent="claude"))
        with self.assertRaisesRegex(board.BoardError, "waiting on codex"):
            run(board.answer, WORK, ISSUE, "x", hub=FakeHub(s))
        hub = FakeHub(s)
        run(board.answer, WORK, ISSUE, "x", hub=hub, force=True)
        self.assertIn(("clear", "PVTI_" + ISSUE, "Responder"), hub.writes)

    def test_a_verdict_posts_a_comment_review_with_the_verdict_first(self):
        hub = FakeHub(self.asked(prs=[open_pr("acme-co/ops#40")]),
                      prs={"acme-co/ops#40": {"id": "PR_40", "url": "u40", "state": "OPEN", "closes": [{"ref": ISSUE}]}},
                      thread=[marker("ask", "codex", "claude", "2026-11-12T01:00:00Z", kind="review")])
        run(board.answer, WORK, ISSUE, "Looks right.", hub=hub, verdict="approve")
        review = [w for w in hub.writes if w[0] == "review"][0]
        self.assertEqual(review[1], "PR_40")
        self.assertTrue(review[2].startswith("<!-- board:verdict from=claude to=codex verdict=approve session=s-1 -->\n**Verdict: approve**"))
        self.assertIn("https://example.test/review/", hub.comments()[0])
        self.assertIn("verdict=approve", hub.comments()[0])

    def test_verdict_values(self):
        with self.assertRaisesRegex(board.BoardError, "approve or changes"):
            run(board.answer, WORK, ISSUE, "x", hub=FakeHub(self.asked()), verdict="lgtm")

    def test_a_verdict_needs_exactly_one_open_pull_request(self):
        with self.assertRaisesRegex(board.BoardError, "no open pull request"):
            run(board.answer, WORK, ISSUE, "x", hub=FakeHub(self.asked()), verdict="approve")
        two = self.asked(prs=[open_pr("acme-co/ops#40"), open_pr("acme-co/ops#41")])
        with self.assertRaisesRegex(board.BoardError, "acme-co/ops#40, acme-co/ops#41"):
            run(board.answer, WORK, ISSUE, "x", hub=FakeHub(two), verdict="approve")


class Handoff(unittest.TestCase):
    def test_sets_agent_and_posts_a_marked_comment(self):
        hub = FakeHub(agent_snap(item(ISSUE, status="In Progress", Agent="claude")))
        rc, _ = run(board.handoff, WORK, ISSUE, "codex", "Tests are in; the build is yours.", hub=hub)
        self.assertEqual(rc, board.APPLIED)
        self.assertIn(("set", "PVTI_" + ISSUE, "Agent", "codex"), hub.writes)
        self.assertIn("<!-- board:handoff from=claude to=codex session=s-1 -->", hub.comments()[0])

    def test_rewrites_the_status_md_line_for_the_new_agent(self):
        e = item(ISSUE, title="Build it", status="In Progress", Agent="claude")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "STATUS.md")
            with open(p, "w") as f:
                f.write(f"# Status\n\n## What's in progress\n\n- [{ISSUE}]({e['url']}) Build it — claimed 2026-11-12 by claude\n\n## Next\n")
            run(board.handoff, WORK, ISSUE, "codex", "yours", hub=FakeHub(agent_snap(e)), status_md=p)
            text = open(p).read()
        self.assertIn("by codex", text)
        self.assertNotIn("by claude", text)
        self.assertEqual(text.count(ISSUE), 1)


class Ack(unittest.TestCase):
    def test_posts_an_ack_marker(self):
        hub = FakeHub(agent_snap(item(ISSUE, Agent="claude")))
        run(board.ack, WORK, ISSUE, "Read, thanks.", hub=hub)
        self.assertIn("<!-- board:ack from=claude to=claude session=s-1 -->", hub.comments()[0])
        self.assertEqual(hub.kinds(), ["comment"])


def inbox_item(ref, comments, title="t"):
    return {"ref": ref, "title": title, "url": "https://github.com/" + ref.replace("#", "/issues/"), "comments": comments}


class Inbox(unittest.TestCase):
    def hub(self, responder=(), agent=(), notifications=(), fail=(), s=None):
        q = {("company", 'Responder:"claude" is:open'): list(responder), ("company", 'Agent:"claude" is:open'): list(agent)}
        return FakeHub(s or agent_snap(item(ISSUE)), items_by_query=q, notifications=notifications, fail_boards=fail)

    def inbox(self, hub, env=ME, **kw):
        return run(board.inbox, {"company": WORK}, hub=hub, env=env, **kw)

    def test_lists_asks_waiting_on_me_with_who_asked(self):
        ask = marker("ask", "codex", "claude", "2026-11-12T01:00:00Z", cid="c1", kind="review")
        rc, logs = self.inbox(self.hub(responder=[inbox_item(ISSUE, [ask])]))
        self.assertEqual(rc, 0)
        self.assertTrue(any(ISSUE in l and "review from codex" in l for l in logs))

    def test_lists_a_reply_on_my_item_newer_than_my_last_signed_comment(self):
        mine = marker("ask", "claude", "codex", "2026-11-12T01:00:00Z", cid="c1", kind="review")
        reply = marker("answer", "codex", "claude", "2026-11-12T02:00:00Z", cid="c2")
        _, logs = self.inbox(self.hub(agent=[inbox_item(ISSUE, [mine, reply])]))
        self.assertTrue(any(ISSUE in l and "answer from codex" in l for l in logs))

    def test_a_reply_i_have_since_acknowledged_is_not_listed(self):
        reply = marker("answer", "codex", "claude", "2026-11-12T02:00:00Z", cid="c2")
        ack = marker("ack", "claude", "claude", "2026-11-12T03:00:00Z", cid="c3")
        _, logs = self.inbox(self.hub(agent=[inbox_item(ISSUE, [reply, ack])]))
        self.assertTrue(any("0 item(s)" in l for l in logs))

    def test_a_handoff_to_me_is_listed(self):
        h = marker("handoff", "codex", "claude", "2026-11-12T02:00:00Z", cid="c4")
        _, logs = self.inbox(self.hub(agent=[inbox_item(ISSUE, [h])]))
        self.assertTrue(any("handoff from codex" in l for l in logs))

    def test_an_item_on_both_lists_shows_once(self):
        ask = marker("ask", "codex", "claude", "2026-11-12T01:00:00Z", cid="c1", kind="question")
        _, logs = self.inbox(self.hub(responder=[inbox_item(ISSUE, [ask])], agent=[inbox_item(ISSUE, [ask])]))
        self.assertTrue(any("1 item(s)" in l for l in logs))

    def test_the_agent_flag_overrides_the_environment(self):
        q = {("company", 'Responder:"codex" is:open'): [inbox_item(ISSUE, [marker("ask", "claude", "codex", "2026-11-12T01:00:00Z", kind="review")])]}
        _, logs = run(board.inbox, {"company": WORK}, hub=FakeHub(agent_snap(item(ISSUE)), items_by_query=q), env={}, agent="codex")
        self.assertTrue(any("review from claude" in l for l in logs))

    def test_json_entries_are_keyed_by_the_marker_comment(self):
        ask = marker("ask", "codex", "claude", "2026-11-12T01:00:00Z", cid="c9", kind="review")
        _, logs = self.inbox(self.hub(responder=[inbox_item(ISSUE, [ask])]), as_json=True)
        out = json.loads("".join(logs))
        self.assertEqual(out["agent"], "claude")
        self.assertEqual(out["items"][0]["id"], "c9")
        self.assertEqual(out["items"][0]["kind"], "ask")
        self.assertEqual(out["items"][0]["from"], "codex")

    def test_a_board_without_the_fields_is_skipped_and_an_unreadable_one_does_not_stop_the_rest(self):
        boards = {"company": WORK, "personal": BOARDS["personal"]}
        ask = marker("ask", "codex", "claude", "2026-11-12T01:00:00Z", kind="review")
        hub = FakeHub(agent_snap(item(ISSUE)), items_by_query={("company", 'Responder:"claude" is:open'): [inbox_item(ISSUE, [ask])]},
                      fail_boards=["personal"])
        rc, logs = run(board.inbox, boards, hub=hub)
        self.assertEqual(rc, 1)
        self.assertTrue(any("personal" in l and "can't read" in l for l in logs))
        self.assertTrue(any("1 item(s)" in l for l in logs))
        _, logs = run(board.inbox, {"company": WORK}, hub=FakeHub(agent_snap(item(ISSUE), with_fields=False)))
        self.assertTrue(any("no Responder field" in l for l in logs))

    def test_notifications_on_my_items_or_on_no_board_are_shown_others_are_not(self):
        s = agent_snap(item(ISSUE, Agent="claude"), item("acme-co/ops#5", Agent="codex"))
        notes = [{"id": "n1", "reason": "comment", "title": "mine", "ref": ISSUE, "url": "u1", "at": "2026-11-12T01:00:00Z"},
                 {"id": "n2", "reason": "comment", "title": "theirs", "ref": "acme-co/ops#5", "url": "u2", "at": "2026-11-12T01:00:00Z"},
                 {"id": "n3", "reason": "mention", "title": "loose", "ref": "acme-co/ops#77", "url": "u3", "at": "2026-11-12T01:00:00Z"}]
        q = {("company", 'Agent:"claude" is:open'): [inbox_item(ISSUE, [])]}
        _, logs = run(board.inbox, {"company": WORK}, hub=FakeHub(s, items_by_query=q, notifications=notes))
        text = "\n".join(logs)
        self.assertIn("mine", text)
        self.assertIn("loose", text)
        self.assertNotIn("theirs", text)


def claim_run(e, env=ME, finish=False, status_md=None, with_fields=True):
    """Run claim or finish with the board stubbed. Returns (plans applied, assignee writes, logs)."""
    s = agent_snap(e, with_fields=with_fields)
    plans, assigned, logs = [], [], []
    saved = board.snapshot, board.apply_plan, board.gql, board.GitHub
    board.snapshot = lambda b, write=True: s

    def apply(b, boards, plan, **kw):
        plans.append(plan)
        return board.APPLIED
    board.apply_plan = apply

    class GH:
        def viewer(self):
            return {"id": "U1", "login": "agents-bot"}

        def issue(self, ref, fresh=False):
            return {"assignees": ["agents-bot"]}
    board.GitHub = GH
    board.gql = lambda q, **v: assigned.append(v) or {}
    old_env = dict(os.environ)
    for k in ("BOARD_AGENT", "BOARD_MODEL", "BOARD_SESSION"):
        os.environ.pop(k, None)
    os.environ.update(env or {})
    try:
        rc = board.claim(WORK, {"company": WORK}, e["ref"], status_md=status_md, finish=finish, log=logs.append)
    finally:
        board.snapshot, board.apply_plan, board.gql, board.GitHub = saved
        os.environ.clear()
        os.environ.update(old_env)
    return rc, [op for p in plans for op in p], logs


class ClaimAndFinish(unittest.TestCase):
    def test_claim_sets_agent_and_names_it_in_status_md(self):
        e = item(ISSUE, title="Build it")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "STATUS.md")
            with open(p, "w") as f:
                f.write("# Status\n\n## What's in progress\n\n- Nothing in flight.\n")
            rc, ops, _ = claim_run(e, status_md=p)
            text = open(p).read()
        self.assertEqual(rc, board.APPLIED)
        self.assertIn({"op": "set_field", "item": ISSUE, "field": "Agent", "value": "claude", "cross_owner": False}, ops)
        self.assertRegex(text, r"claimed \d{4}-\d\d-\d\d by claude \(session s-1\)")

    def test_claim_refuses_an_item_another_agent_holds(self):
        with self.assertRaisesRegex(board.BoardError, "held by codex"):
            claim_run(item(ISSUE, Agent="codex"))

    def test_claim_without_the_field_works_as_before(self):
        rc, ops, _ = claim_run(item(ISSUE), with_fields=False)
        self.assertEqual(rc, board.APPLIED)
        self.assertEqual([o["field"] for o in ops], ["Status"])

    def test_claim_without_an_agent_name_skips_the_field_and_says_so(self):
        rc, ops, logs = claim_run(item(ISSUE), env={})
        self.assertEqual([o["field"] for o in ops], ["Status"])
        self.assertTrue(any("BOARD_AGENT" in l for l in logs))

    def test_finish_clears_responder_and_keeps_agent(self):
        rc, ops, _ = claim_run(item(ISSUE, status="In Progress", Agent="claude", Responder="codex"), finish=True)
        self.assertIn({"op": "clear_field", "item": ISSUE, "field": "Responder", "cross_owner": False}, ops)
        self.assertFalse(any(o.get("field") == "Agent" for o in ops))

    def test_select_skips_an_item_another_agent_holds(self):
        s = agent_snap(item(ISSUE, Priority="P1", Effort=1, Agent="codex"))
        picks, skipped = board.select(WORK, s, count=5, claimed=lambda r: set())
        self.assertEqual(picks, [])
        self.assertIn((ISSUE, "held by codex"), skipped)

    def test_the_fixture_reset_clears_both_fields(self):
        fx = item(ISSUE, title="[Test fixture] t", labels=["test-fixture"], status="Backlog", Agent="claude", Responder="codex")
        plan = board.reset_fixture_plan(WORK, agent_snap(fx))
        self.assertEqual(sorted(o["field"] for o in plan if o["op"] == "clear_field"), ["Agent", "Responder"])


class SetupAgents(unittest.TestCase):
    def test_creates_both_fields_with_the_agents_and_the_operator(self):
        hub = FakeHub(agent_snap(with_fields=False))
        rc, _ = run(board.setup_agents, WORK, hub=hub)
        self.assertEqual(rc, board.APPLIED)
        self.assertEqual([w for w in hub.writes if w[0] == "create_field"],
                         [("create_field", "Agent", ("claude", "codex", "Pat")), ("create_field", "Responder", ("claude", "codex", "Pat"))])

    def test_adds_missing_options_and_keeps_the_rest_with_their_ids(self):
        s = agent_snap()
        s["fields"]["Agent"]["options"] = OPTS("claude", "old-agent")
        hub = FakeHub(s)
        run(board.setup_agents, WORK, hub=hub)
        self.assertIn(("set_options", "FA", ("claude", "old-agent", "codex", "Pat")), hub.writes)

    def test_nothing_to_do_writes_nothing(self):
        hub = FakeHub(agent_snap())
        rc, logs = run(board.setup_agents, WORK, hub=hub)
        self.assertEqual(hub.writes, [])
        self.assertTrue(any("already" in l for l in logs))

    def test_dry_run_writes_nothing(self):
        hub = FakeHub(agent_snap(with_fields=False))
        run(board.setup_agents, WORK, hub=hub, dry_run=True)
        self.assertEqual(hub.writes, [])

    def test_needs_agents_in_the_config_and_a_writable_board(self):
        with self.assertRaisesRegex(board.BoardError, "read-only"):
            run(board.setup_agents, BOARDS["globex"], hub=FakeHub(agent_snap(with_fields=False)))
        bare = dict(WORK, agents=[])
        with self.assertRaisesRegex(board.BoardError, '"agents"'):
            run(board.setup_agents, bare, hub=FakeHub(agent_snap(with_fields=False)))


class Config(unittest.TestCase):
    def test_operator_may_be_a_name_and_login_or_a_login(self):
        self.assertEqual(board.operator_of(WORK), ("Pat", "pat-example"))
        self.assertEqual(board.operator_of(dict(WORK, operator="pat-example")), ("pat-example", "pat-example"))
        self.assertEqual(board.operator_of(dict(WORK, operator=None)), (None, None))


if __name__ == "__main__":
    unittest.main()
