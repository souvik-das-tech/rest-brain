# Architecture

Rest Brain is a small FastAPI app that drives the AGY CLI as child processes. This page explains
the moving parts. All names below are in the `brain/` package.

## Overview

```
HTTP request
   │
   ▼
server.py   create_app()
   │  require_auth (HTTP Basic, secrets.compare_digest)     /health, /docs, /openapi.json stay open
   │  CORSMiddleware (when BRAIN_CORS is set)
   │  exception handlers → {"error": {"code", "message"}}
   ▼
sessions.py SessionManager ─── ask_once() ──▶ agy.py AgyOneShot          (POST /ask)
   │            │
   │            └─ _reap(): every 60 s closes sessions idle longer than idle_timeout
   ▼
   Session  (id, model, instructions, transcript, asyncio.Lock)
   │
   ▼
agy.py AgyProvider
   ├─ AgySession   warm process:  agy -p= --input-format stream-json --output-format stream-json
   └─ AgyOneShot   fallback:      agy -p <prompt> --output-format json [--json-schema <file>]
```

## Processes and protocols

**Warm session (`AgySession`).** One long-running process per chat session. Each turn writes one
line to stdin:

```json
{"event": "user", "message": {"role": "user", "content": "..."}}
```

and reads NDJSON events from stdout until an `{"event": "result", ...}` event arrives. The
session's instructions are sent as the first turn. Starting a process costs about 10 s; later turns
take about 3 s. Turns are serialized with a lock. After 40 turns (`max_turns`) the process is
replaced in the background.

**One-shot (`AgyOneShot`).** A new process per request with `--output-format json`. When a schema is
given, it is written to a uniquely named file in the workspace and passed with `--json-schema`, so
AGY enforces it. The file is deleted afterwards.

**Failure handling (`AgyProvider.ask`).**

- A crashed process (`AIProcessError`) is retried once with a fresh process. If that fails as well,
  the session switches to one-shot mode.
- A time-out kills the process and returns `504`; the next message starts a new one.
- Whenever a process (re)starts, `Session.history_note()` puts the last 8000 characters of the
  transcript in front of the next message, so the conversation continues.
- Sign-in problems are detected from known markers in AGY's output (`not authenticated`,
  `sign in`, ...) and reported as `503 agy_not_signed_in`.

**Process cleanup (`kill_tree`).** On Windows, `taskkill /T /F` ends AGY and its helpers, and child
processes start with `CREATE_NO_WINDOW`. On POSIX, each AGY process starts in its own session and
the whole process group gets `SIGKILL`.

## Isolation

AGY runs with its working directory set to an empty, app-owned `agy_workspace/` folder in the data
directory (`paths.data_dir()`). Rest Brain never passes `--dangerously-skip-permissions`, so in
headless mode every tool that needs approval is denied. AGY can think, answer and use its own web
search, but cannot read or change files. Denied tool attempts are logged.

## JSON replies

`sessions.extract_json()` returns the first JSON object or array in a reply, looking inside
Markdown `json` code fences first. In a session, `json` and `schema` requests add an instruction to
reply with JSON only (with the schema, when given). If parsing fails, the session asks once more; if
that also fails, the API returns `422 invalid`.

## Health check

`server.check_agy()` runs `agy --version` and `agy models` at the same time. `agy models` needs a
signed-in account, so it doubles as the sign-in check. The result is cached for 60 s
(`AGY_CHECK_TTL`) and cleared whenever a request fails with "not installed" or "not signed in".

## Configuration and startup

`__main__.main()` loads `.env` from the project folder (real environment variables win), parses the
command-line options, sets up console and rotating file logging, warns when listening on a
non-loopback address without auth, and starts uvicorn with `create_app()`. `main.py` is the same
entry point for process managers such as pm2.

## State

All sessions live in memory in `SessionManager.sessions`. There is no database. Restarting the API
closes every AGY process and clears all sessions.

## Tests

`tests/test_api.py` writes a fake AGY script that implements `--version`, `models`, `-p` (with
`--json-schema`) and the stream-json loop, and points `SessionManager(command=[python, script])` at
it. The tests drive the app through `httpx.ASGITransport` with the real lifespan. They cover auth,
CORS, sessions, crash recovery with transcript replay, one-shot schemas, errors and the OpenAPI spec.
