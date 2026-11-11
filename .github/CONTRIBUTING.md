# Contributing to MineScope

MineScope is owned by **TheYAZBAL** and developed under **DevStudio**. Thank you for helping!

## Team structure (organizational roles)

Engineering (Python, protocols, architecture, CLI, database), Quality Assurance
(automated, protocol, regression and performance testing) and Documentation
(technical, API, installation and developer guides). These are roles, not claims
that separate people already work on the project.

## Workflow

1. **Fork** <https://github.com/TheYAZBAL/MineScope> and clone your fork.
2. **Branch** from `main`: `feature/<name>`, `fix/<name>`, `refactor/<module>`,
   `docs/<name>`, `test/<name>`.
3. **Set up**: see [docs/development/setup.md](docs/development/setup.md).
4. **Commit** using conventional prefixes: `feat:`, `fix:`, `refactor:`, `docs:`,
   `test:`, `perf:`, `chore:`.
5. **Test**: run `python -m unittest discover -s tests -t .` (or `pytest`). New behaviour
   needs tests; tests must work offline (fake sockets / loopback), never against public servers.
6. **Open a pull request** using the template. Keep it focused and describe what you ran.
7. **Review**: a maintainer reviews; address feedback by pushing more commits.
8. **Release** (maintainers): update `CHANGELOG.md` and the version in `minescope/core/constants.py`
   and `pyproject.toml`, tag `vX.Y.Z`, and publish release notes from `.github/RELEASE_TEMPLATE.md`.

## Standards

PEP 8 / 257 / 484, type hints on public APIs, explicit error handling, parameterized SQL only,
no features that attack or degrade servers. Do not fabricate server or player data.
