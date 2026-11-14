# task-mgmt — agent conventions

Conventions for agents working on this repo. The product is described in [README.md](README.md).

## Working here

- Read [STATUS.md](STATUS.md) first; update it before leaving.
- Work on a feature branch and land it by pull request that references the issue (`Refs #N` or `closes #N`).
- Commit prefixes: `analysis:`, `plan:`, `impl:`, `status:`, plus `feat:` / `fix:` / `docs:` / `chore:`.
- Tests, one suite per area: `python3 -m unittest discover -s tests/board`, and the same for `tests/provision`, `tests/design_loop` and `tests/preflight`. Run the suite for the area you changed.
- Decision records go in [docs/decisions/](docs/decisions/).

## Neutrality

This repo is public and adopter-neutral: it carries no employer, client or personal names, paths or emails. Before each commit, grep the staged diff for private names and remove every hit. Build records are kept privately by the maintainers, so this repo has no `design/` folder.
