# Development setup

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

| Task | Command |
| --- | --- |
| Tests (stdlib) | `python -m unittest discover -s tests -t .` |
| Tests (pytest) | `python -m pytest` |
| Coverage | `python -m pytest --cov=minescope --cov-report=term-missing` |
| Lint | `ruff check minescope tests` |
| Format check | `ruff format --check minescope tests` |
| Types | `mypy minescope` |
| Build ZIP | `python scripts/build_zip.py` |

Debugging: `minescope --log-level DEBUG scan host` logs why each protocol attempt failed.
Tests never touch public servers: use `tests/fixtures/fakes.py` (fake sockets) and
`tests/fixtures/loopback.py` (real sockets on 127.0.0.1).
