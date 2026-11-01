"""REST API over the AGY CLI (FastAPI). All bodies are JSON; errors are {"error": {"code", "message"}}."""

from __future__ import annotations

import asyncio
import getpass
import logging
import os
import platform
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.exceptions import HTTPException as StarletteHTTPException

from brain import __version__
from brain.agy import (
    AGY_INSTALL_URL, AIAuthError, AIError, AINotInstalled, AIModelError, AIProcessError, AITimeout,
    agy_available, agy_version, list_models,
)
from brain.schemas import (
    AgyStatus, ApiStatus, AskRequest, DeleteResponse, ErrorResponse, HealthResponse, MessageRequest,
    MessageResponse, ModelsResponse, ReplyResponse, SessionCreate, SessionDetail, SessionInfo, SessionList,
    SystemInfo,
)
from brain.sessions import Session, SessionManager, TooManySessions

log = logging.getLogger(__name__)

_STATUS = [  # most specific first
    (AINotInstalled, 503, "agy_not_installed"),
    (AIAuthError, 503, "agy_not_signed_in"),
    (AITimeout, 504, "timeout"),
    (AIModelError, 502, "model_error"),
    (AIProcessError, 502, "agy_process_error"),
    (AIError, 502, "agy_error"),
]
_HTTP_CODES = {401: "unauthorized", 404: "not_found", 405: "method_not_allowed"}
AGY_CHECK_TTL = 60  # seconds the /health AGY check is cached

DESCRIPTION = """
The local **AGY (Antigravity) CLI** as a REST API. Any project (web, Node, Python, mobile backend)
can use the AI brain over HTTP instead of writing its own AGY integration.

### Quick start
1. `GET /health` checks that the API is up and that AGY is installed and signed in on this machine
   (no login needed).
2. Click **Authorize** and enter the username and password (HTTP Basic auth).
3. `POST /sessions` starts a chat and returns its `id`.
4. `POST /sessions/{id}/messages` sends one message and returns the reply.

### Sessions vs. `/ask`
| | Speed | Memory |
|---|---|---|
| **Sessions** (recommended) | first turn ~10-20 s, later turns ~3 s | remembers the conversation |
| **`/ask`** | ~10-15 s every time (new AGY process) | none, but enforces JSON Schema natively |

### JSON replies
Send `"json": true` to get the reply parsed into the `json` field, or send a JSON Schema as
`"schema"` to describe the exact shape you want.

### Errors
Every error has the same shape:
```json
{"error": {"code": "not_found", "message": "Session not found."}}
```
| Status | Codes |
|---|---|
| 401 | `unauthorized` |
| 404 | `not_found` |
| 422 | `invalid` (bad input, or the AI reply was not JSON when JSON was asked for) |
| 429 | `too_many_sessions` |
| 502 | `model_error`, `agy_process_error`, `agy_error` |
| 503 | `agy_not_installed`, `agy_not_signed_in` |
| 504 | `timeout` |

All requests run on the AGY account signed in on the machine that runs this API.
"""

TAGS = [
    {"name": "Health", "description": "Is the API running, and is the AGY CLI installed and signed in? "
                                      "No auth needed."},
    {"name": "Models", "description": "The models the signed-in AGY account can use."},
    {"name": "Ask", "description": "Stateless one-shot requests. Each one starts a new AGY process."},
    {"name": "Sessions", "description": "Chat sessions. Each is a warm AGY process that keeps the "
                                        "conversation, so turns after the first are fast."},
]


def _err(description: str) -> dict[str, Any]:
    return {"model": ErrorResponse, "description": description}


AUTH_ERRORS = {401: _err("Missing or wrong username/password.")}
AI_ERRORS = {
    422: _err("Invalid input, or the AI reply was not JSON when JSON was asked for."),
    502: _err("AGY or the model returned an error."),
    503: _err("AGY is not installed or not signed in on the server."),
    504: _err("AGY did not answer in time."),
}
NOT_FOUND = {404: _err("No session with this id (it may have been closed after being idle).")}


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


# ---- dependencies -----------------------------------------------------------------------------

basic_auth = HTTPBasic(auto_error=False, description="The username and password set in BRAIN_USERNAME and "
                                                     "BRAIN_PASSWORD on the server.")


def require_auth(request: Request,
                 credentials: Annotated[HTTPBasicCredentials | None, Depends(basic_auth)]) -> None:
    username, password = request.app.state.auth
    ok = credentials is not None
    if ok:
        # compare both, always, so the response time does not reveal which one was wrong
        user_ok = secrets.compare_digest(credentials.username.encode(), username.encode())
        pass_ok = secrets.compare_digest(credentials.password.encode(), password.encode())
        ok = user_ok and pass_ok
    if not ok:
        raise HTTPException(401, "Missing or wrong username/password.",
                            headers={"WWW-Authenticate": 'Basic realm="Rest Brain"'})


def get_manager(request: Request) -> SessionManager:
    return request.app.state.manager


Manager = Annotated[SessionManager, Depends(get_manager)]
SessionId = Annotated[str, Path(description="Session id from `POST /sessions`.",
                                examples=["acb39d5e0f7a4c41a5f0f3f0b1e6d2aa"])]


def get_session(session_id: SessionId, manager: Manager) -> Session:
    try:
        return manager.get(session_id)
    except KeyError:
        raise HTTPException(404, "Session not found.")


ChatSession = Annotated[Session, Depends(get_session)]


# ---- routes -----------------------------------------------------------------------------------

public = APIRouter()
api = APIRouter(responses=AUTH_ERRORS)


@public.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse("/docs")


def run_as_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # no login name (e.g. some containers)
        return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


async def check_agy(manager: SessionManager) -> dict[str, Any]:
    """Installed? `agy --version`. Signed in? `agy models`, which fetches the list with the account."""
    user = run_as_user()
    now = datetime.now(timezone.utc)
    path = manager.command[0] if manager.command else agy_available()
    if not path:
        return {"installed": False, "signed_in": None, "path": None, "version": None, "checked_at": now,
                "error": "AGY CLI not found on PATH (set BRAIN_AGY to its full path if it is installed).",
                "action": f"Install the AGY CLI as user '{user}', run `agy` once and sign in, then call "
                          "/health?refresh=true.",
                "install_url": AGY_INSTALL_URL}
    command = manager.command or [path]
    version, models = await asyncio.gather(agy_version(command, timeout=15), list_models(command, timeout=30),
                                           return_exceptions=True)
    status: dict[str, Any] = {"installed": True, "signed_in": True, "path": path, "checked_at": now,
                              "version": None if isinstance(version, BaseException) else version,
                              "error": None, "action": None, "install_url": None}
    if isinstance(models, AIAuthError):
        status.update(signed_in=False, error="AGY is installed but not signed in.",
                      action=f"Sign in: open a terminal on this machine as user '{user}', run `agy` and complete "
                             "the login, then call /health?refresh=true.")
    elif isinstance(models, BaseException):
        status.update(signed_in=None, error=f"Sign-in check (`agy models`) failed: {models}",
                      action=f"Run `agy models` in a terminal on this machine as user '{user}' to see the problem.")
    elif isinstance(version, BaseException):
        status["error"] = f"agy --version failed: {version}"
    return status


@public.get("/health", response_model=HealthResponse, tags=["Health"], summary="API and AGY status")
async def health(
    request: Request, manager: Manager,
    refresh: Annotated[bool, Query(description="Check AGY now instead of using the result cached for 60 s "
                                               "(use it right after signing in).")] = False,
) -> dict[str, Any]:
    """Call this to check that the API is running, whether the AGY CLI is **installed** on the machine it
    runs on, and whether it is **signed in**. It always returns **200** while the API is up.

    | `status` | `agy.installed` | `agy.signed_in` | Meaning |
    |---|---|---|---|
    | `ok` | true | true | Ready |
    | `degraded` | true | false | Installed, not signed in: follow `agy.action` |
    | `degraded` | false | null | AGY is not installed |
    | `degraded` | true | null | The check failed for another reason: see `agy.error` |

    The AGY check takes a few seconds, so its result is cached for 60 seconds."""
    state = request.app.state
    async with state.agy_lock:
        cached = state.agy_check
        if refresh or cached is None or time.time() - cached[0] > AGY_CHECK_TTL:
            state.agy_check = cached = (time.time(), await check_agy(manager))
    agy = cached[1]
    started = state.started
    return {
        "status": "ok" if agy["signed_in"] else "degraded",
        "api": {"running": True, "version": __version__,
                "started_at": datetime.fromtimestamp(started, timezone.utc),
                "uptime_seconds": round(time.time() - started, 1)},
        "system": {"os": platform.system(), "os_release": platform.release(), "arch": platform.machine(),
                   "python": platform.python_version()},
        "run_as_user": run_as_user(),
        "agy": agy,
        "default_model": manager.default_model,
        "sessions": len(manager.sessions),
        "auth_enabled": state.auth is not None,
    }


@api.get("/models", response_model=ModelsResponse, tags=["Models"], summary="List available models",
         responses={k: v for k, v in AI_ERRORS.items() if k != 422})
async def models(manager: Manager) -> dict[str, Any]:
    """Live from `agy models`, so new models show up without a code change. Use an `id` as the
    `model` field of `/ask` or `POST /sessions`."""
    return {"default": manager.default_model, "models": await list_models(manager.command)}


@api.post("/ask", response_model=ReplyResponse, tags=["Ask"], summary="One-shot question",
          responses=AI_ERRORS)
async def ask(
    manager: Manager,
    body: Annotated[AskRequest, Body(openapi_examples={
        "plain": {"summary": "Plain question",
                  "value": {"prompt": "What is the command to restart nginx?",
                            "instructions": "You are a Linux expert. Be brief."}},
        "json": {"summary": "JSON reply",
                 "value": {"prompt": "List 3 Linux commands to check disk usage.", "json": True}},
        "schema": {"summary": "Enforced JSON Schema",
                   "value": {"prompt": "Command to check free memory",
                             "schema": {"type": "object", "properties": {"command": {"type": "string"},
                                                                         "explanation": {"type": "string"}},
                                        "required": ["command"]}}},
    })],
) -> dict[str, Any]:
    """Starts a new AGY process for this one prompt (~10-15 s) and keeps no memory. With `schema`,
    AGY enforces the JSON Schema natively. Use a session instead for a conversation or for speed."""
    return await manager.ask_once(body.prompt, model=body.model or None, instructions=body.instructions,
                                  schema=body.json_schema, want_json=body.want_json)


@api.get("/sessions", response_model=SessionList, tags=["Sessions"], summary="List open sessions")
async def list_sessions(manager: Manager) -> dict[str, Any]:
    return {"sessions": [s.info() for s in manager.sessions.values()]}


@api.post("/sessions", response_model=SessionInfo, status_code=201, tags=["Sessions"],
          summary="Start a chat session",
          responses={429: _err("Too many open sessions; delete one first."), **AI_ERRORS})
async def create_session(
    manager: Manager,
    body: Annotated[SessionCreate, Body(openapi_examples={
        "basic": {"summary": "Assistant with instructions",
                  "value": {"instructions": "You are a helpful assistant. Reply in Banglish."}},
        "warm": {"summary": "Wait until warm",
                 "value": {"instructions": "You plan Linux commands. Reply JSON only.", "wait": True}},
        "empty": {"summary": "Defaults", "value": {}},
    })] = SessionCreate(),
) -> dict[str, Any]:
    """Starts a warm AGY process with these instructions and returns the session. Its first message
    waits for the warm-up (about 10-20 s) unless you pass `"wait": true` here. An unused session
    closes after the idle timeout (30 minutes by default). Sessions live in memory: restarting the
    API clears them."""
    session = manager.create(body.model or None, body.instructions)
    if body.wait:
        await session.ready()
    return session.info()


@api.get("/sessions/{session_id}", response_model=SessionDetail, tags=["Sessions"],
         summary="Session info and transcript", responses=NOT_FOUND)
async def get_session_detail(session: ChatSession) -> dict[str, Any]:
    return session.info(with_transcript=True)


@api.post("/sessions/{session_id}/messages", response_model=MessageResponse, tags=["Sessions"],
          summary="Send a message", responses={**NOT_FOUND, **AI_ERRORS})
async def send_message(
    session: ChatSession,
    body: Annotated[MessageRequest, Body(openapi_examples={
        "plain": {"summary": "Chat message", "value": {"message": "nginx restart er command ki?"}},
        "json": {"summary": "JSON reply", "value": {"message": "Give me 3 tips as a JSON array.", "json": True}},
        "schema": {"summary": "Reply matching a schema",
                   "value": {"message": "disk usage check command",
                             "schema": {"type": "object", "properties": {"command": {"type": "string"}},
                                        "required": ["command"]}}},
    })],
) -> dict[str, Any]:
    """Sends one chat turn (~3-5 s once the session is warm). Messages to the same session are
    answered one at a time. If the AGY process crashes or times out, it restarts and the earlier
    transcript is replayed, so the conversation continues."""
    result = await session.send(body.message, want_json=body.want_json, schema=body.json_schema)
    return {"session": session.id, **result}


@api.post("/sessions/{session_id}/reset", response_model=SessionInfo, tags=["Sessions"],
          summary="Start over", responses=NOT_FOUND)
async def reset_session(session: ChatSession) -> dict[str, Any]:
    """Clears the conversation and keeps the same instructions and model."""
    await session.reset()
    return session.info()


@api.delete("/sessions/{session_id}", response_model=DeleteResponse, tags=["Sessions"],
            summary="Close a session", responses=NOT_FOUND)
async def delete_session(session: ChatSession, manager: Manager) -> dict[str, Any]:
    """Closes the session and stops its AGY process."""
    try:
        await manager.delete(session.id)
    except KeyError:  # closed by the idle reaper in the meantime
        raise HTTPException(404, "Session not found.")
    return {"deleted": session.id}


# ---- app --------------------------------------------------------------------------------------

def create_app(manager: SessionManager, username: str | None = None, password: str | None = None,
               cors: list[str] | None = None) -> FastAPI:
    """Basic auth is on when both `username` and `password` are given; /health and the docs stay open."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager.start()
        yield
        await manager.close()

    app = FastAPI(
        title="Rest Brain", version=__version__, description=DESCRIPTION, openapi_tags=TAGS,
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True,
                               "tryItOutEnabled": True, "filter": True, "docExpansion": "list",
                               "defaultModelsExpandDepth": 1},
    )
    app.state.manager = manager
    app.state.started = time.time()
    app.state.auth = (username, password) if username and password else None
    app.state.agy_check = None  # (time, AgyStatus dict) cached by /health
    app.state.agy_lock = asyncio.Lock()

    app.include_router(public)
    app.include_router(api, dependencies=[Depends(require_auth)] if app.state.auth else [])
    if cors:
        app.add_middleware(CORSMiddleware, allow_origins=cors, allow_methods=["GET", "POST", "DELETE"],
                           allow_headers=["Authorization", "Content-Type"])

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error(exc.status_code, _HTTP_CODES.get(exc.status_code, "http_error"), str(exc.detail),
                     getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        parts = []
        for e in exc.errors():
            where = ".".join(str(p) for p in e.get("loc", ())[1:])
            parts.append(f"{where}: {e.get('msg')}" if where else str(e.get("msg")))
        return error(422, "invalid", "; ".join(parts) or "Invalid request.")

    @app.exception_handler(TooManySessions)
    async def too_many(request: Request, exc: TooManySessions) -> JSONResponse:
        return error(429, "too_many_sessions", str(exc))

    @app.exception_handler(ValueError)
    async def bad_value(request: Request, exc: ValueError) -> JSONResponse:
        # e.g. a reply that was not JSON when JSON was asked for
        return error(422, "invalid", str(exc))

    @app.exception_handler(AIError)
    async def ai_error(request: Request, exc: AIError) -> JSONResponse:
        if isinstance(exc, (AINotInstalled, AIAuthError)):
            request.app.state.agy_check = None  # let /health show it right away
        for cls, status, code in _STATUS:
            if isinstance(exc, cls):
                return error(status, code, str(exc))
        return error(502, "agy_error", str(exc))

    @app.exception_handler(Exception)
    async def internal(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error(500, "internal", f"{type(exc).__name__}: {exc}")

    return app
