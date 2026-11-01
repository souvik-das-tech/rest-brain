"""Request and response models. They drive validation and the Swagger / OpenAPI docs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# "json" and "schema" are attribute names on BaseModel, so those fields use aliases.
_ALIASED = ConfigDict(populate_by_name=True)


# ---- errors -----------------------------------------------------------------------------------

class ErrorBody(BaseModel):
    code: str = Field(description="Machine-readable error code.", examples=["not_found"])
    message: str = Field(description="Human-readable explanation.", examples=["Session not found."])


class ErrorResponse(BaseModel):
    """Every error has this shape, whatever the status code."""
    error: ErrorBody


# ---- health -----------------------------------------------------------------------------------

class ApiStatus(BaseModel):
    running: bool = Field(True, description="Always true: if you got a response, the API is up.")
    version: str = Field(description="Rest Brain version.", examples=["2.0.0"])
    started_at: datetime = Field(description="When this API process started (UTC).")
    uptime_seconds: float = Field(description="Seconds since the API started.", examples=[3600.5])


class SystemInfo(BaseModel):
    os: str = Field(description="Operating system name.", examples=["Linux", "Windows"])
    os_release: str = Field(description="OS release / kernel version.", examples=["6.8.0-45-generic", "11"])
    arch: str = Field(description="CPU architecture.", examples=["x86_64", "AMD64"])
    python: str = Field(description="Python version running the API.", examples=["3.12.10"])


class AgyStatus(BaseModel):
    installed: bool = Field(description="True when the AGY CLI was found on this system.")
    signed_in: bool | None = Field(
        None, description="True when AGY is signed in (checked with `agy models`, which needs the account). "
                          "False: installed but not signed in. Null: not installed, or the check failed for "
                          "another reason (see `error`).")
    path: str | None = Field(None, description="Full path of the AGY CLI that will be used.",
                             examples=["/home/ubuntu/.local/bin/agy"])
    version: str | None = Field(None, description="Output of `agy --version`, when it ran.", examples=["1.4.7"])
    checked_at: datetime | None = Field(None, description="When the sign-in check ran (UTC). It is cached for "
                                                          "60 seconds; pass `?refresh=true` to check now.")
    error: str | None = Field(None, description="Why AGY is not usable, when it is not.")
    action: str | None = Field(None, description="What to do to fix it, when something is wrong.",
                               examples=["Sign in: open a terminal on this machine as user 'ubuntu', run `agy` "
                                         "and complete the login, then call /health?refresh=true."])
    install_url: str | None = Field(None, description="Where to get AGY, shown only when it is missing.")


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = Field(
        description="`ok`: the API runs and AGY is installed and signed in. `degraded`: the API runs but AGY "
                    "is missing, not signed in or broken, so AI endpoints will fail; see `agy.action`.")
    api: ApiStatus
    system: SystemInfo
    run_as_user: str = Field(description="OS user the API runs as. AGY must be signed in as this user.",
                             examples=["ubuntu"])
    agy: AgyStatus
    default_model: str = Field(description="Model used when a request does not name one.",
                               examples=["gemini-3.8-flash-medium"])
    sessions: int = Field(description="Number of open chat sessions.", examples=[0])
    auth_enabled: bool = Field(description="True when Basic auth is required on the other endpoints.")


# ---- models -----------------------------------------------------------------------------------

class ModelInfo(BaseModel):
    id: str = Field(description="Pass this as `model`.", examples=["gemini-3.8-flash-low"])
    label: str = Field(description="Display name from AGY.", examples=["Gemini 3.8 Flash (Low)"])


class ModelsResponse(BaseModel):
    default: str = Field(description="The API's default model.", examples=["gemini-3.8-flash-medium"])
    models: list[ModelInfo]


# ---- replies ----------------------------------------------------------------------------------

class ReplyResponse(BaseModel):
    model_config = _ALIASED

    reply: str = Field(description="The AI's reply text (for schema requests, the JSON as text).",
                       examples=["Use `sudo systemctl restart nginx`."])
    json_data: Any | None = Field(None, alias="json",
                                  description="The reply parsed as JSON when `json` or `schema` was sent, "
                                              "otherwise null.", examples=[None])
    mode: Literal["session", "oneshot"] = Field(
        description="`session`: answered by a warm AGY process. `oneshot`: a new process for this request.")


class MessageResponse(ReplyResponse):
    session: str = Field(description="The session that answered.", examples=["acb39d5e0f7a4c41a5f0f3f0b1e6d2aa"])


# ---- requests ---------------------------------------------------------------------------------

class AskRequest(BaseModel):
    model_config = _ALIASED

    prompt: str = Field(min_length=1, description="The question or task.",
                        examples=["What is the command to restart nginx?"])
    instructions: str = Field("", description="System prompt: role and rules for the AI.",
                              examples=["You are a Linux expert. Be brief."])
    model: str | None = Field(None, description="Model id from `GET /models`. Empty uses the default.")
    want_json: bool = Field(False, alias="json",
                            description="Parse the reply as JSON into the `json` field of the response.")
    json_schema: dict[str, Any] | None = Field(
        None, alias="schema",
        description="A JSON Schema. AGY enforces it natively and the parsed result is in `json`.")


class SessionCreate(BaseModel):
    instructions: str = Field("", description="System prompt for the whole chat, sent once at the start.",
                              examples=["You are a helpful assistant. Reply in Banglish."])
    model: str | None = Field(None, description="Model id from `GET /models`. Empty uses the default.")
    wait: bool = Field(False, description="Wait until the AGY process is warm (about 10-20 s) before "
                                          "returning, so the first message is fast.")


class MessageRequest(BaseModel):
    model_config = _ALIASED

    message: str = Field(min_length=1, description="The user's chat message.",
                         examples=["nginx restart er command ki?"])
    want_json: bool = Field(False, alias="json",
                            description="Ask for a JSON-only reply and parse it into `json`. If the first "
                                        "reply is not JSON, the AI is asked once more.")
    json_schema: dict[str, Any] | None = Field(
        None, alias="schema",
        description="A JSON Schema the reply should match. In a session it goes into the prompt and the "
                    "reply is parsed into `json`.")


# ---- sessions ---------------------------------------------------------------------------------

class SessionInfo(BaseModel):
    id: str = Field(description="Session id, used in the URL of the other session endpoints.",
                    examples=["acb39d5e0f7a4c41a5f0f3f0b1e6d2aa"])
    model: str = Field(examples=["gemini-3.8-flash-medium"])
    instructions: str = Field(examples=["You are a helpful assistant."])
    created: float = Field(description="Unix time the session was created.", examples=[1793462400.0])
    last_used: float = Field(description="Unix time of the last message.", examples=[1793462460.0])
    turns: int = Field(description="Number of user/assistant exchanges so far.", examples=[3])
    busy: bool = Field(description="True while a message is being answered.")
    ready: bool = Field(description="True once the AGY process is warm.")


class TranscriptEntry(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(examples=["hello"])
    time: float = Field(description="Unix time.", examples=[1793462460.0])


class SessionDetail(SessionInfo):
    transcript: list[TranscriptEntry] = Field(description="The whole conversation, oldest first.")


class SessionList(BaseModel):
    sessions: list[SessionInfo]


class DeleteResponse(BaseModel):
    deleted: str = Field(description="Id of the closed session.", examples=["acb39d5e0f7a4c41a5f0f3f0b1e6d2aa"])
