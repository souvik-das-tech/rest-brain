# Contributing to Rest Brain

Thanks for your interest! Bug reports, ideas and pull requests are all welcome.

## Ground rules

- Be kind. This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Security problems go through [SECURITY.md](SECURITY.md), not public issues.
- For a bigger change, open an issue or a discussion first so we can agree on the approach.

## Set up

You need Python 3.12 or newer. The tests use a fake AGY, so you do **not** need the real AGY CLI.

```bash
git clone https://github.com/souvik-das-tech/rest-brain.git
cd rest-brain
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt        # Windows: .venv\Scripts\python ...
.venv/bin/python -m pytest
```

To try the real API, install and sign in to the AGY CLI, copy `.env.example` to `.env`, and run
`python -m brain`. The interactive docs are at `http://127.0.0.1:8787/docs`.

## Project layout

| Path | What it is |
|---|---|
| `brain/__main__.py` | Command line, `.env` loading, logging, starts uvicorn |
| `brain/server.py` | FastAPI app: routes, auth, error handlers, `/health` check |
| `brain/schemas.py` | Pydantic request and response models (they drive the OpenAPI docs) |
| `brain/sessions.py` | `SessionManager`, `Session`, JSON extraction |
| `brain/agy.py` | AGY CLI adapter: warm stream-json session, one-shot, process handling |
| `brain/paths.py` | Data and log directories |
| `tests/test_api.py` | API tests against a fake AGY |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together.

## Making a change

1. Fork the repository and create a branch from `main`.
2. Keep the change focused. Match the style of the surrounding code (type hints, short docstrings,
   lines up to about 120 characters).
3. Add or update tests in `tests/` for new behaviour. Extend the fake AGY in `tests/test_api.py`
   when you need a new CLI behaviour.
4. Run `python -m pytest` and make sure it passes on your OS.
5. Update `README.md` when you change endpoints, options or defaults, and add a line under
   `[Unreleased]` in `CHANGELOG.md`.
6. Open a pull request and fill in the template.

## Reporting bugs

Use the **Bug report** issue template. The output of `GET /health` (with paths or user names
removed if you prefer) and the relevant lines of `brain.log` help a lot. Never paste your `.env`
or your password.
