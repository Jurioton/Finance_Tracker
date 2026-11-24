import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    # Fresh in-memory database for every test
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def register(client, email="a@example.com"):
    res = client.post("/auth/register", json={"name": "Test", "email": email, "password": "secret123"})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture()
def auth(client):
    return register(client)


class FakeOllama:
    """A tiny stand-in for the Ollama HTTP API, so tests exercise the real client code without a model.

    Set `replies` to the assistant messages it should answer with, in order. A reply can also be
    {"status": 404, "error": "..."} to simulate an Ollama error.
    """

    def __init__(self):
        self.models = ["llama3.2:latest"]
        self.replies: list[dict] = []
        self.requests: list[dict] = []


@pytest.fixture()
def fake_ollama(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from app import config

    fake = FakeOllama()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, status, body: bytes, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/tags":
                self._send(200, json.dumps({"models": [{"name": n} for n in fake.models]}).encode())
            else:
                self._send(404, b"{}")

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            fake.requests.append(body)
            reply = fake.replies.pop(0) if fake.replies else {"content": "ok"}
            if "status" in reply:
                self._send(reply["status"], json.dumps({"error": reply["error"]}).encode())
                return
            message = {"role": "assistant", "content": reply.get("content", ""), **(
                {"tool_calls": reply["tool_calls"]} if reply.get("tool_calls") else {})}
            if not body.get("stream"):
                self._send(200, json.dumps({"message": message, "done": True}).encode())
                return
            # Streaming: content in small pieces, tool calls in their own chunk, then a final "done"
            lines = []
            text = message["content"]
            for i in range(0, len(text), 4):
                lines.append({"message": {"role": "assistant", "content": text[i:i + 4]}, "done": False})
            if message.get("tool_calls"):
                lines.append({"message": {"role": "assistant", "content": "", "tool_calls": message["tool_calls"]},
                              "done": False})
            lines.append({"message": {"role": "assistant", "content": ""}, "done": True})
            self._send(200, "".join(json.dumps(line) + "\n" for line in lines).encode(), "application/x-ndjson")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "OLLAMA_URL", f"http://127.0.0.1:{server.server_port}")
    yield fake
    server.shutdown()
