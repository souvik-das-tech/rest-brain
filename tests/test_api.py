"""REST API against a fake AGY that speaks stream-json (sessions) and -p json (one-shot)."""

import base64
import sys

import httpx
import pytest

from brain.server import create_app
from brain.sessions import SessionManager, extract_json

# Session turns echo the message (and the history preamble, so a restart can be checked);
# "--json-schema" one-shots return structured_output. A message containing "DIE" kills the process.
FAKE_AGY = r'''
import json, os, sys
args = sys.argv[1:]
if "--version" in args:
    print("fake-agy 0.0"); sys.exit(0)
if "models" in args:
    if os.environ.get("FAKE_AGY_SIGNED_OUT"):
        print("Error: not authenticated, run agy to sign in", file=sys.stderr); sys.exit(1)
    print("Fetching models..."); print("fake-low\tFake Low"); print("fake-high\tFake High"); sys.exit(0)
if "-p" in args:
    prompt = args[args.index("-p") + 1]
    out = {"status": "SUCCESS", "response": "once:" + prompt}
    if "--json-schema" in args:
        out["structured_output"] = {"answer": 42}
    print(json.dumps(out)); sys.exit(0)
print(json.dumps({"event": "init", "conversation_id": str(os.getpid())}), flush=True)
for line in sys.stdin:
    text = json.loads(line)["message"]["content"]
    if "DIE" in text:
        sys.exit(3)
    if "JSON" in text:
        reply = 'sure: ```json\n{"echo": "%s"}\n```' % text.splitlines()[0]
    else:
        reply = f"{os.getpid()}|{text}"
    print(json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": reply}}), flush=True)
'''


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_DATA_DIR", str(tmp_path / "data"))
    script = tmp_path / "fake_agy.py"
    script.write_text(FAKE_AGY, encoding="utf-8")
    manager = SessionManager("fake-low", command=[sys.executable, str(script)], max_sessions=2)
    app = create_app(manager, username="admin", password="pw", cors=["http://app.local"])
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", auth=("admin", "pw"),
                                     timeout=60) as c:
            yield c


async def test_health_and_models(client):
    health = (await client.get("/health", auth=None)).json()
    assert health["status"] == "ok" and health["api"]["running"] and health["auth_enabled"]
    assert health["agy"]["installed"] and health["agy"]["signed_in"] and health["agy"]["version"] == "fake-agy 0.0"
    assert health["agy"]["action"] is None and health["run_as_user"]
    models = (await client.get("/models")).json()
    assert [m["id"] for m in models["models"]] == ["fake-low", "fake-high"]


async def test_health_without_agy(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("brain.server.agy_available", lambda: None)
    app = create_app(SessionManager("fake-low"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        health = (await c.get("/health")).json()
    assert health["status"] == "degraded" and not health["agy"]["installed"] and health["agy"]["install_url"]
    assert health["agy"]["signed_in"] is None and health["agy"]["action"]
    assert not health["auth_enabled"]


async def test_health_signed_out(client, monkeypatch):
    monkeypatch.setenv("FAKE_AGY_SIGNED_OUT", "1")
    health = (await client.get("/health")).json()
    assert health["status"] == "degraded"
    assert health["agy"]["installed"] and health["agy"]["signed_in"] is False
    assert "run `agy`" in health["agy"]["action"] and health["run_as_user"] in health["agy"]["action"]
    monkeypatch.delenv("FAKE_AGY_SIGNED_OUT")
    assert (await client.get("/health")).json()["agy"]["signed_in"] is False  # still cached
    assert (await client.get("/health?refresh=true")).json()["status"] == "ok"


async def test_basic_auth_required(client):
    resp = await client.get("/sessions", auth=("admin", "wrong"))
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "unauthorized"
    assert resp.headers["WWW-Authenticate"].startswith("Basic")
    assert (await client.get("/sessions", auth=None)).status_code == 401
    token = base64.b64encode(b"admin:pw").decode()
    assert (await client.get("/sessions", auth=None, headers={"Authorization": f"Basic {token}"})).status_code == 200
    assert (await client.get("/health", auth=None)).status_code == 200
    assert (await client.get("/openapi.json", auth=None)).status_code == 200


async def test_cors_preflight(client):
    resp = await client.options("/sessions", auth=None, headers={
        "Origin": "http://app.local", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization"})
    assert resp.status_code == 200 and resp.headers["Access-Control-Allow-Origin"] == "http://app.local"


async def test_session_conversation(client):
    resp = await client.post("/sessions", json={"instructions": "be brief", "wait": True})
    assert resp.status_code == 201
    sid = resp.json()["id"]

    reply = (await client.post(f"/sessions/{sid}/messages", json={"message": "hello"})).json()
    assert reply["reply"].endswith("|hello") and reply["mode"] == "session" and reply["session"] == sid

    data = (await client.post(f"/sessions/{sid}/messages", json={"message": "give", "json": True})).json()
    assert data["json"] == {"echo": "give"}

    info = (await client.get(f"/sessions/{sid}")).json()
    assert info["turns"] == 2 and info["transcript"][0] == {**info["transcript"][0], "role": "user", "content": "hello"}

    assert (await client.post(f"/sessions/{sid}/reset")).status_code == 200
    assert (await client.get(f"/sessions/{sid}")).json()["turns"] == 0
    assert (await client.delete(f"/sessions/{sid}")).json() == {"deleted": sid}
    assert (await client.get(f"/sessions/{sid}")).status_code == 404


async def test_crashed_process_restarts_with_history(client):
    sid = (await client.post("/sessions", json={"wait": True})).json()["id"]
    first = (await client.post(f"/sessions/{sid}/messages", json={"message": "remember 7"})).json()["reply"]
    # the process dies on this turn; the provider restarts it and the transcript is replayed
    resp = await client.post(f"/sessions/{sid}/messages", json={"message": "DIE now"})
    assert resp.status_code in (200, 502)
    after = (await client.post(f"/sessions/{sid}/messages", json={"message": "what number?"})).json()["reply"]
    assert "USER: remember 7" in after
    assert after.split("|")[0] != first.split("|")[0]


async def test_ask_once_with_schema(client):
    resp = await client.post("/ask", json={"prompt": "q", "schema": {"type": "object"}})
    assert resp.json()["json"] == {"answer": 42}
    plain = (await client.post("/ask", json={"prompt": "hi", "instructions": "sys"})).json()
    assert plain["reply"] == "once:sys\n\nhi" and plain["json"] is None


async def test_errors(client):
    resp = await client.post("/ask", json={})
    assert resp.status_code == 422 and resp.json()["error"] == {"code": "invalid", "message": "prompt: Field required"}
    assert (await client.post("/ask", json={"prompt": 5})).status_code == 422
    resp = await client.post("/sessions/nope/messages", json={"message": "x"})
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"
    for _ in range(2):
        assert (await client.post("/sessions", json={})).status_code == 201
    assert (await client.post("/sessions")).status_code == 429


def test_openapi_docs():
    spec = create_app(SessionManager("fake-low"), username="u", password="p").openapi()
    assert spec["components"]["securitySchemes"]["HTTPBasic"]["scheme"] == "basic"
    assert "security" not in spec["paths"]["/health"]["get"]
    assert spec["paths"]["/ask"]["post"]["security"] == [{"HTTPBasic": []}]
    props = spec["components"]["schemas"]["AskRequest"]["properties"]
    assert {"prompt", "json", "schema"} <= props.keys()


def test_extract_json():

    assert extract_json('text ```json\n{"a": 1}\n``` more') == {"a": 1}
    assert extract_json("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        extract_json("no json here")
