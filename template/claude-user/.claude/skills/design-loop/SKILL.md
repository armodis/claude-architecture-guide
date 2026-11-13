---
name: design-loop
description: Run the design loop on complex work in any repo — frame it with the operator, build a thin end-to-end slice, settle facts with checks, bring only judgment calls to the operator at a direction gate and a contract gate, then build to tests and verify with evidence. Keeps one folder per run at design/<YYYY-MM-DD-slug>/ in the repo. Use when the user says "design loop", "/design-loop", "run this through the loop", or asks to design and scope multi-part work that is easy to mis-frame.
---

# Design loop

Agents settle facts; the operator makes the judgment calls. Every question the operator sees should be one that evidence cannot answer. Facts are reported with their evidence, never asked.

**Inputs:** the operator's request, and the repo the session runs in. **Outputs:** a run folder in that repo, the work itself on a feature branch, and tests that become the regression suite.

## The run folder

`design/<YYYY-MM-DD-slug>/` at the repo root, created from [templates/](templates/):

| File | Holds |
|---|---|
| `framing.md` | Goal, requirements, done-when, out of scope, assumptions, effort estimate, known judgment calls, corrections at confirmation |
| `facts.md` | Fact log: one entry per settled question, with evidence |
| `decisions.md` | Decision ledger: each judgment call, its neutral options, the operator's ruling in their words |
| `contract.md` | Goal, scope, decisions, and the acceptance tests with the command that runs them |
| `cost.md` + `cost-log.tsv` | Effort estimate, and token spend by step from the transcripts |
| `evidence/` | Probe output worth keeping |
| `scratch/` | Working files; gitignored. Subagents write here |

On the first run in a repo, add `design/*/scratch/` to its `.gitignore`. Use the date from `date +%F`.

**Cost:** at the start of each step, run `python3 <this skill's folder>/scripts/cost.py mark <run-dir> <step>` (`~/.claude/skills/design-loop/` when installed at user level) (steps `0-frame`, `1-thin-rail`, `2-direction-gate`, `3-probes-tests`, `4-contract-gate`, `5-build`, `6-verify`). Marking a step also links the session to the run, which the compaction hook relies on: when continuing a run in a new session, mark the current step again first. Run `… report <run-dir>` at each gate and at the end; it rewrites the report block in `cost.md`, and it refuses to run on a machine without the sessions' transcripts.

## Steps

### 0. Frame (operator, briefly)

Create the run folder from the templates first, then mark `0-frame`, so the framing's spend is counted and the session is linked to the run.

Find where the request is genuinely underspecified and settle what you can by reading first. Then restate **GOAL / REQUIREMENTS / DONE WHEN / OUT OF SCOPE / ASSUMPTIONS**, plus an effort estimate (complexity rating and its drivers) and the judgment calls you can already see. Ask about the endpoint: how far the run goes. Flag the assumption most likely to be wrong. Wait for explicit confirmation; write `framing.md` with the corrections the operator made and their wording. An issue's own scope is not proof the framing is right — check it against what the operator says now.

### 1. Thin rail and probes (agents)

On a feature branch, build the thinnest end-to-end slice that touches the real system, so probes hit what will actually run. Then run the **triage gate**:

- Spawn two `design-triage` reviewers **in one message** so they run concurrently and blind: one with `model: "fable"`, one with `model: "opus"`. If Fable is unavailable, use Opus and Sonnet, and record that in `facts.md`. Give each the run folder, the gate name and the absolute output path `<run-dir>/scratch/triage-<gate>-<model>.md`. Run them in the background; they write with Bash, under the session's permission mode.
- Merge the two outputs. A question either reviewer could settle by a check is a fact. Settle the open facts yourself or with Sonnet/Haiku subagents (plain scripts where no judgment is needed), including checks that need writes, keeping writes inside the run's scratch or a disposable test target. Record each in `facts.md` with its evidence. Copy probe output worth keeping to `evidence/`.
- Where the reviewers disagree on whether something is a fact, try the check; if it settles, it was a fact.
- Write the remaining judgment calls to `decisions.md`, keeping options neutral and the recommendation separate. Tier each one: **full** if it changes scope or the done-when, is hard to reverse, or affects other people or shared systems; **default** otherwise. When the reviewers tier a call differently, use full.
- Collect each reviewer's **Fences crossed** section into `facts.md`, so the operator sees what was read outside the run's scope and why.

### 2. Direction gate (operator)

Show the operator `decisions.md` and a short summary of `facts.md` (what was settled, and any fences crossed; nothing asked). **Full** calls come first, each with the question, the options with the same structure and length, the evidence, then the recommendation in its own line. **Default** calls follow as one line each — the question and the recommended option — under "going with the recommendation unless you object"; any the operator does not object to are recorded as ruled on the recommendation. Record each ruling in the operator's words. A ruling is not revisited unless new evidence contradicts it; then bring the evidence, not a re-argument.

### 3. More probes and tests (agents)

Turn each decision into a test where possible. Run the triage gate again on the updated run if open questions remain. Tests are observed by running them, never claimed.

### 4. Contract gate (operator)

Write `contract.md`: goal, scope, the decisions (linked to the ledger), and the acceptance tests — each with its path, the command that runs it, and its current result. Keep the prose thin; the tests are the substance. The operator approves the contract.

### 5. Build to contract (agents)

Run the [`preflight`](../preflight/SKILL.md) skill first, with `--pull` and the paths of every repo the build works in, and stop on a non-zero exit: report what blocks and its fix. Then build against the tests. A mid-flight decision that is **reversible** goes in `decisions.md`, marked "decided during build, reversible", and the build continues. One that is **irreversible or outward-facing** (deletion, force-push, external messages, other people's work, shared settings) comes to the operator before acting.

### 6. Verify (verifier)

Spawn `design-verifier` on the run folder in its own context, with the output path `<run-dir>/scratch/verify.md`. It runs every acceptance test and reports met / not met / unverifiable per contract item with evidence. Report its result plainly; a not-met item is fixed and re-verified, not re-worded.

### Closing the run

- Lasting decisions become ADRs in `docs/decisions/` or stay as tests; reader-facing material moves to `docs/`.
- Run `cost.py mark <run-dir> closed`, then the cost report; write estimate against actual at the top of `cost.md`.
- Set `framing.md`'s **Status:** to Closed, as the line's first word (the compaction hook skips closed runs). The folder stays as the record.
- Update the repo's STATUS.md.

## After compaction

A `SessionStart` hook ([design-framing.sh](../../hooks/design-framing.sh)) prints the active run's `framing.md` after a compaction. Re-read it and `decisions.md` before continuing.
