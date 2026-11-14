# STATUS

Handoff note for agents and maintainers. Read first, update before leaving.

## What just happened

- The product is named task-mgmt, at https://github.com/armodis-ai/task-mgmt.
- Repo scaffold added: AGENTS.md, STATUS.md, docs/decisions/.
- claude-restore and claude-provider ship under `template/claude-restore/` (MIT).
- README documents installing a pinned release.
- Hub configs (`<hub>/.task-mgmt/config.json`) and a person layer (`person.json`): `provision.py config` generates the `board` config from them, and `provision.py` reads the hubs, checks their boards against GitHub, and sets each repo's `BOARD_CONFIG` and `BOARD_REF` variables and reads them back. Read-only boards get no workflow findings.
- Release v0.2.0 ([#22](https://github.com/armodis-ai/task-mgmt/issues/22)).

## What's in progress

(none)

## What's next

- The roadmap issues on the [task-mgmt roadmap](https://github.com/orgs/armodis-ai/projects/11).

## Where to find things

- Conventions: [AGENTS.md](AGENTS.md)
- Product overview and install: [README.md](README.md)
- Decisions: [docs/decisions/](docs/decisions/)
- Tests: `tests/<suite>/`
