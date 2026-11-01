"""Chat sessions: each one is a warm AGY process with its own instructions, model and transcript."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import Sequence
from typing import Any

from brain.agy import AgyOneShot, AgyProvider, agy_workspace, find_agy

log = logging.getLogger(__name__)

HISTORY_TO_AI = 8000  # chars of the transcript handed to AGY when its process had to restart
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """The first JSON object (or array) in a reply, also inside ```json fences."""
    for candidate in [*(m.group(1) for m in _FENCE.finditer(text)), text]:
        for opener in "{[":
            start = candidate.find(opener)
            while start != -1:
                try:
                    obj, _ = json.JSONDecoder().raw_decode(candidate[start:])
                    return obj
                except json.JSONDecodeError:
                    start = candidate.find(opener, start + 1)
    raise ValueError("no JSON in AI reply")


def json_request(message: str, schema: dict | None) -> str:
    """Stream-json sessions cannot enforce a schema, so the prompt asks for it."""
    if schema is None:
        return f"{message}\n\nReply with ONLY one JSON value, nothing outside it."
    return (f"{message}\n\nReply with ONLY one JSON value that matches this JSON schema, nothing outside it:\n"
            + json.dumps(schema, ensure_ascii=False))


class Session:
    def __init__(self, model: str, instructions: str, command: Sequence[str] | None,
                 turn_timeout: float, start_timeout: float):
        self.id = uuid.uuid4().hex
        self.model = model
        self.instructions = instructions
        self.created = time.time()
        self.last_used = self.created
        self.transcript: list[dict[str, Any]] = []
        self.lock = asyncio.Lock()  # one turn at a time keeps the transcript in order
        self.provider = AgyProvider(
            command=command, model=model, workdir=agy_workspace(), history=self.history_note,
            session_kwargs={"turn_timeout": turn_timeout, "start_timeout": start_timeout},
            oneshot_kwargs={"timeout": turn_timeout}, keep_spare=False,
        )
        self._start = asyncio.create_task(self.provider.start(instructions))

    def history_note(self) -> str:
        if not self.transcript:
            return ""
        lines = [f"{'USER' if t['role'] == 'user' else 'YOU'}: {t['content']}" for t in self.transcript]
        return ("This chat continues an earlier conversation (the AI session was restarted). Earlier messages:\n"
                + "\n".join(lines)[-HISTORY_TO_AI:])

    async def ready(self) -> None:
        await asyncio.shield(self._start)

    async def send(self, message: str, want_json: bool = False, schema: dict | None = None) -> dict[str, Any]:
        async with self.lock:
            await self.ready()
            self.last_used = time.time()
            prompt = json_request(message, schema) if want_json or schema is not None else message
            reply = await self.provider.ask(prompt)
            data = None
            if want_json or schema is not None:
                try:
                    data = extract_json(reply)
                except ValueError:
                    log.warning("Session %s: reply was not JSON: %s", self.id, reply[:300])
                    reply = await self.provider.ask("Your last reply was not valid JSON. Reply again with ONLY the JSON.")
                    data = extract_json(reply)
            now = time.time()
            self.transcript.append({"role": "user", "content": message, "time": now})
            self.transcript.append({"role": "assistant", "content": reply, "time": now})
            self.last_used = now
            return {"reply": reply, "json": data, "mode": self.provider.mode}

    async def reset(self) -> None:
        async with self.lock:
            self.transcript.clear()
            await self.provider.reset()

    async def close(self) -> None:
        self._start.cancel()
        await self.provider.close()

    def info(self, with_transcript: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id, "model": self.model, "instructions": self.instructions,
            "created": self.created, "last_used": self.last_used, "turns": len(self.transcript) // 2,
            "busy": self.lock.locked(), "ready": self._start.done() and not self._start.cancelled()
            and self._start.exception() is None,
        }
        if with_transcript:
            out["transcript"] = self.transcript
        return out


class TooManySessions(Exception):
    pass


class SessionManager:
    def __init__(self, default_model: str, command: Sequence[str] | None = None, max_sessions: int = 10,
                 idle_timeout: float = 1800, turn_timeout: float = 150, start_timeout: float = 120):
        self.default_model = default_model
        self.command = list(command) if command else None
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self.turn_timeout = turn_timeout
        self.start_timeout = start_timeout
        self.sessions: dict[str, Session] = {}
        self._reaper: asyncio.Task | None = None

    def start(self) -> None:
        self._reaper = asyncio.create_task(self._reap())

    def create(self, model: str | None = None, instructions: str = "") -> Session:
        if len(self.sessions) >= self.max_sessions:
            raise TooManySessions(f"At most {self.max_sessions} sessions; delete one first.")
        session = Session(model or self.default_model, instructions, self.command,
                          self.turn_timeout, self.start_timeout)
        self.sessions[session.id] = session
        log.info("Session %s created (model=%s)", session.id, session.model)
        return session

    def get(self, session_id: str) -> Session:
        return self.sessions[session_id]  # KeyError -> 404

    async def delete(self, session_id: str) -> None:
        session = self.sessions.pop(session_id)
        await session.close()
        log.info("Session %s deleted", session_id)

    async def ask_once(self, prompt: str, model: str | None = None, instructions: str = "",
                       schema: dict | None = None, want_json: bool = False) -> dict[str, Any]:
        """Stateless: one AGY process for one prompt (slower, ~10 s start), with native schema enforcement."""
        oneshot = AgyOneShot(self.command or [str(find_agy())], model or self.default_model,
                             workdir=agy_workspace(), timeout=self.turn_timeout)
        await oneshot.start(instructions)
        message = json_request(prompt, None) if want_json and schema is None else prompt
        reply = await oneshot.ask(message, schema=schema)
        data = extract_json(reply) if want_json or schema is not None else None
        return {"reply": reply, "json": data, "mode": "oneshot"}

    async def _reap(self) -> None:
        while True:
            await asyncio.sleep(60)
            cutoff = time.time() - self.idle_timeout
            for sid, session in list(self.sessions.items()):
                if session.last_used < cutoff and not session.lock.locked():
                    log.info("Session %s idle, closing", sid)
                    try:
                        await self.delete(sid)
                    except KeyError:
                        pass

    async def close(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
        for sid in list(self.sessions):
            await self.delete(sid)
