# Rest Brain

**Turn the AGY (Google Antigravity) CLI on your machine into a small, self-hosted REST API, so any app can use it over HTTP.**

[![CI](https://github.com/souvik-das-tech/rest-brain/actions/workflows/ci.yml/badge.svg)](https://github.com/souvik-das-tech/rest-brain/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)](#quick-start)
[![FastAPI](https://img.shields.io/badge/built%20with-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)

## Why it exists

The AGY CLI is a capable AI agent, but it is a command-line tool. Each project that wants to use it
has to start processes, speak its stream-json protocol, handle restarts, time-outs and sign-in errors,
and parse the replies. Rest Brain does that once. It runs next to the signed-in CLI and gives
web apps, Node or Python services and mobile backends a plain JSON-over-HTTP API.

## Features

- **Warm chat sessions.** Each session keeps one AGY process running, so after the first turn
  (about 10-20 s while AGY starts) replies take about 3-5 s.
- **Survives crashes.** If the AGY process crashes, times out or reaches its turn limit, it restarts
  and the earlier transcript is replayed, so the conversation goes on. After repeated crashes a
  session falls back to one-shot mode.
- **One-shot `/ask`.** A stateless request with native JSON Schema enforcement from AGY.
- **JSON replies.** Send `"json": true` or a JSON Schema and get the parsed result in a `json` field.
- **Clear health check.** `GET /health` tells you whether AGY is installed and signed in, and what to
  do when it is not.
- **Live model list.** `GET /models` comes straight from `agy models`, so new models need no code change.
- **HTTP Basic auth and CORS.** Constant-time credential checks; `/health` and the docs stay open.
- **Swagger UI and ReDoc.** Interactive docs at `/docs` with an **Authorize** button.
- **Sandboxed by design.** AGY runs in an empty folder and its tools are auto-denied in headless mode,
  so it can only answer and plan. Your app does the actual work.
- **Windows and Linux, under pm2.** One `ecosystem.config.js` for both.

## Quick start

Requirements: Python 3.12+, the [AGY CLI](https://antigravity.google/) signed in as the same OS user
that runs the API, and optionally [pm2](https://pm2.keymetrics.io/) (`npm i -g pm2`).

**Windows**

```
irm https://antigravity.google/install.ps1 | iex     (or: winget install Google.AntigravityCLI)
agy                                                   (once, to sign in)
git clone https://github.com/souvik-das-tech/rest-brain.git
cd rest-brain
setup.cmd                                             (creates .venv and .env)
run.cmd
```

**Linux (Ubuntu)**

```bash
sudo apt install python3.12-venv      # if venv is missing
# install the AGY CLI, then run `agy` once and sign in
git clone https://github.com/souvik-das-tech/rest-brain.git && cd rest-brain
chmod +x setup.sh run.sh && ./setup.sh
./run.sh
```

Then set `BRAIN_USERNAME` and `BRAIN_PASSWORD` in `.env` (see [.env.example](.env.example)) and open
`http://127.0.0.1:8787/docs`.

### Run with pm2 (Windows and Linux)

[ecosystem.config.js](ecosystem.config.js) picks the right `.venv` Python on each OS.

```
pm2 start ecosystem.config.js
pm2 logs rest-brain
pm2 restart rest-brain        (after changing .env)
pm2 save                      (remember the process list)
```

Start on boot: on Linux run `pm2 startup` and follow what it prints, then `pm2 save`. On Windows pm2
has no built-in startup; use `pm2-installer` or a Task Scheduler task that runs `pm2 resurrect` at logon.

Without pm2: `run.cmd` (Windows), `./run.sh` (Linux) or `python main.py`.

pm2 keeps the environment it was started with. If `agy` is not on its PATH, set `BRAIN_AGY` in `.env`
to the full path. `GET /health` tells you whether the API can find it.

## Usage

### Endpoints

| Method | Path | Body | What it does |
|---|---|---|---|
| GET | `/health` | | API status, OS info, and whether AGY is installed and signed in (no auth) |
| GET | `/models` | | Models this AGY account can use (live from `agy models`) |
| POST | `/ask` | `{prompt, instructions?, model?, json?, schema?}` | Stateless one-shot request (~10-15 s, new process each time) |
| POST | `/sessions` | `{instructions?, model?, wait?}` | Starts a chat session (warm AGY process) and returns its `id` |
| GET | `/sessions` | | Lists open sessions |
| GET | `/sessions/{id}` | | Session info and full transcript |
| POST | `/sessions/{id}/messages` | `{message, json?, schema?}` | Sends one chat turn (~3-5 s once warm) |
| POST | `/sessions/{id}/reset` | | Starts a fresh conversation, keeps the instructions and model |
| DELETE | `/sessions/{id}` | | Closes the session and stops its AGY process |

Reply: `{"reply": "<text>", "json": <parsed JSON or null>, "mode": "session" | "oneshot"}`
(session messages also include `"session": "<id>"`).

- `instructions` is the system prompt (role and rules). In a session it is sent once, at the start.
- `json: true` parses the reply as JSON into `json`. In a session, if the first reply is not JSON, the
  AI is asked once more.
- `schema` (a JSON Schema): `/ask` uses AGY's own `--json-schema` enforcement. In a session the schema
  goes into the prompt and the reply is parsed.
- Prefer sessions. Pass `"wait": true` to `POST /sessions` to wait for the warm-up there, so the first
  message is fast too.

### curl

```bash
curl -u admin:secret -X POST http://127.0.0.1:8787/sessions -H "Content-Type: application/json" \
     -d '{"instructions": "You are a helpful assistant. Be brief."}'
# -> {"id": "acb39d...", ...}

curl -u admin:secret -X POST http://127.0.0.1:8787/sessions/acb39d.../messages \
     -H "Content-Type: application/json" -d '{"message": "What is the command to restart nginx?"}'
# -> {"reply": "Use `sudo systemctl restart nginx`.", "json": null, "mode": "session", "session": "acb39d..."}
```

### JavaScript

```js
const BRAIN = "http://127.0.0.1:8787";
const AUTH = "Basic " + btoa("admin:secret");   // Node: Buffer.from("admin:secret").toString("base64")
const post = (path, body) => fetch(BRAIN + path, {
  method: "POST",
  headers: { "Content-Type": "application/json", "Authorization": AUTH },
  body: JSON.stringify(body),
}).then(r => r.json());

const { id } = await post("/sessions", { instructions: "You plan Linux commands. Reply JSON only." });
const { json } = await post(`/sessions/${id}/messages`, {
  message: "disk usage check command",
  schema: { type: "object", properties: { command: { type: "string" } }, required: ["command"] },
});
console.log(json.command);
```

### Python

```python
import requests

B, AUTH = "http://127.0.0.1:8787", ("admin", "secret")
sid = requests.post(f"{B}/sessions", json={"instructions": "Be brief."}, auth=AUTH).json()["id"]
print(requests.post(f"{B}/sessions/{sid}/messages", json={"message": "hello"}, auth=AUTH).json()["reply"])
```

### Health check

`/health` always returns 200 while the API is up:

```json
{"status": "degraded", "api": {"running": true, "version": "2.0.0", "uptime_seconds": 12.3, "...": "..."},
 "system": {"os": "Linux", "os_release": "6.8.0-45-generic", "arch": "x86_64", "python": "3.12.3"},
 "run_as_user": "ubuntu",
 "agy": {"installed": true, "signed_in": false, "path": "/home/ubuntu/.local/bin/agy", "version": "1.4.12",
         "error": "AGY is installed but not signed in.",
         "action": "Sign in: open a terminal on this machine as user 'ubuntu', run `agy` and complete the login, then call /health?refresh=true."},
 "default_model": "gemini-3.8-flash-medium", "sessions": 0, "auth_enabled": true}
```

| `status` | `agy.installed` | `agy.signed_in` | Meaning |
|---|---|---|---|
| `ok` | true | true | Ready |
| `degraded` | true | false | Installed, not signed in: sign in as `run_as_user` |
| `degraded` | false | null | AGY is not installed |
| `degraded` | true | null | The check failed for another reason: see `agy.error` |

The sign-in check runs `agy models` and takes a few seconds, so it is cached for 60 seconds. Call
`/health?refresh=true` right after signing in.

### Errors

Every error is `{"error": {"code": "...", "message": "..."}}`:

| Status | Codes |
|---|---|
| 401 | `unauthorized` |
| 404 | `not_found` |
| 422 | `invalid` (bad input, or the reply was not JSON when JSON was asked for) |
| 429 | `too_many_sessions` |
| 502 | `model_error`, `agy_process_error`, `agy_error` |
| 503 | `agy_not_installed`, `agy_not_signed_in` |
| 504 | `timeout` |

## How it works

```
 your app ──HTTP/JSON──▶ ┌──────────── Rest Brain (FastAPI + uvicorn) ────────────┐
                         │  Basic auth · CORS · validation · {"error": ...} shape  │
                         │                                                         │
                         │  POST /ask ─────────▶ AgyOneShot ──▶ agy -p ... --json   │
                         │                                     (new process)       │
                         │  /sessions/* ──▶ SessionManager                          │
                         │                   └─ Session (id, transcript, lock)     │
                         │                       └─ AgyProvider                    │
                         │                           ├─ AgySession ──▶ agy -p=      │
                         │                           │   (warm, stream-json stdin/  │
                         │                           │    stdout, restart+replay)   │
                         │                           └─ AgyOneShot (fallback)      │
                         └──────────────────────────┬──────────────────────────────┘
                                                    ▼
                                 empty agy_workspace/ folder, tools auto-denied
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the details.

## Configuration

Set options in `.env`, as environment variables or on the command line (`run.cmd --port 9000`).
Real environment variables override `.env`.

| Option | Env | Default |
|---|---|---|
| `--host` | `BRAIN_HOST` | `127.0.0.1` (this machine only; `0.0.0.0` for the network) |
| `--port` | `BRAIN_PORT` | `8787` |
| `--model` | `BRAIN_MODEL` | `gemini-3.8-flash-medium` |
| `--username` | `BRAIN_USERNAME` | none. Basic auth username |
| `--password` | `BRAIN_PASSWORD` | none. Basic auth password |
| `--cors` | `BRAIN_CORS` | none. Allowed browser origins, comma separated, e.g. `http://localhost:3000`, or `*` |
| `--max-sessions` | `BRAIN_MAX_SESSIONS` | `10` (each session is one AGY process) |
| `--idle-timeout` | `BRAIN_IDLE_TIMEOUT` | `1800` seconds before an unused session closes |
| `--turn-timeout` | `BRAIN_TURN_TIMEOUT` | `150` seconds per turn |
| | `BRAIN_AGY` | Full path to the AGY CLI if it is not on PATH |
| | `BRAIN_DATA_DIR` | Data directory (see below) |

Basic auth is on when both `BRAIN_USERNAME` and `BRAIN_PASSWORD` are set (setting only one is an
error). Every endpoint needs it except `/health`, `/docs`, `/redoc` and `/openapi.json`. Basic auth
sends the password with every request, so put the API behind HTTPS (for example nginx) when it is
reachable over the internet.

## Data and privacy

- **Every request runs on the AGY account signed in on the machine.** Anyone who can call the API
  uses that account. Set a username and password before listening on anything other than `127.0.0.1`.
- **Sessions live in memory only.** Restarting the API clears them. An unused session closes after
  the idle timeout (30 minutes by default).
- **Logs** go to `logs/brain.log` (rotating, 3 x 2 MB) in the data directory: Windows
  `%LOCALAPPDATA%\Rest-Brain`, Linux `~/.local/share/rest-brain`. They record session ids, models,
  turn timings and token counts, tools AGY tried that were denied, error details, and the first 300
  characters of a reply that was not valid JSON when JSON was asked for. They do not record prompts
  or normal replies. pm2 also keeps its own logs.
- **AGY never sees your project files.** It runs in an empty `agy_workspace/` folder in the data
  directory, and Rest Brain never passes `--dangerously-skip-permissions`, so its tools are denied.
  AGY's own web search still works.
- Prompts and replies go to Google's service through the AGY CLI, under that service's terms.

## Development and tests

```
.venv\Scripts\python -m pip install -r requirements-dev.txt      (Linux: .venv/bin/python ...)
.venv\Scripts\python -m pytest
```

The tests start a fake AGY (a small Python script that speaks the same stream-json and `-p` JSON
protocols), so they need no real install or sign-in. CI runs them on Ubuntu and Windows with
Python 3.12 and 3.13.

## Roadmap

Ideas, not promises:

- Streaming replies (Server-Sent Events) for long answers
- Optional API-key or bearer-token auth next to Basic auth
- Persisting sessions across restarts
- A Dockerfile for Linux deployments

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md). To report a security problem, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Souvik Das.

Rest Brain is an independent project. It is not affiliated with or endorsed by Google. "Antigravity"
and "Gemini" are trademarks of their owners. Rest Brain does not include the AGY CLI; you install it
yourself under its own terms.
