import pytest

from app import ai

from .test_api import add_tx, category_id


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    """Tests run offline: force the rules engine unless a test opts in."""
    monkeypatch.setattr(ai, "ANTHROPIC_API_KEY", "")
    ai._insight_cache.clear()


def categorize(client, auth, note, type="expense"):
    res = client.post("/ai/categorize", json={"note": note, "type": type}, headers=auth)
    assert res.status_code == 200, res.text
    body = res.json()
    return (body["category"] or {}).get("name"), body["engine"]


def test_status_without_key(client, auth):
    assert client.get("/ai/status", headers=auth).json() == {"ai_enabled": False, "model": None}


@pytest.mark.parametrize("note,type,expected", [
    ("Swiggy order", "expense", "Food"),
    ("Uber to office", "expense", "Transport"),
    ("Electricity bill October", "expense", "Bills"),
    ("Netflix subscription", "expense", "Bills"),  # 'subscription' and 'netflix' tie-break is fine either way
    ("Bought shoes on Myntra", "expense", "Shopping"),
    ("Pharmacy - cough syrup", "expense", "Health"),
    ("November salary", "income", "Salary"),
    ("Invoice for client website", "income", "Freelance"),
])
def test_keyword_rules(client, auth, note, type, expected):
    name, engine = categorize(client, auth, note, type)
    assert engine == "rules"
    if note.startswith("Netflix"):
        assert name in {"Bills", "Entertainment"}
    else:
        assert name == expected


def test_unknown_note_returns_none(client, auth):
    assert categorize(client, auth, "xyzzy")[0] is None


def test_learns_from_history(client, auth):
    # "Chai point" isn't in any keyword list; once the user files it under Entertainment, it is suggested
    assert categorize(client, auth, "Chai point")[0] != "Entertainment"
    add_tx(client, auth, 80, "expense", "Entertainment", note="Chai point with friends")
    assert categorize(client, auth, "chai point")[0] == "Entertainment"


def test_custom_category_name_match(client, auth):
    client.post("/categories", json={"name": "Education", "type": "expense"}, headers=auth)
    assert categorize(client, auth, "Education fees for course")[0] == "Education"


def test_insights_rules(client, auth):
    add_tx(client, auth, 40000, "income", "Salary", day="2026-10-01")
    add_tx(client, auth, 5000, "expense", "Food", day="2026-10-05")
    add_tx(client, auth, 40000, "income", "Salary", day="2026-11-01")
    add_tx(client, auth, 9000, "expense", "Food", day="2026-11-05")
    add_tx(client, auth, 12000, "expense", "Rent", day="2026-11-02")
    client.post("/budgets", json={"category_id": category_id(client, auth, "Food"), "limit": 8000,
                                  "month": "2026-11"}, headers=auth)

    body = client.get("/ai/insights", params={"month": "2026-11"}, headers=auth).json()
    assert body["engine"] == "rules"
    assert "₹40,000" in body["summary"]
    titles = [i["title"] for i in body["insights"]]
    assert "Healthy savings" in titles            # 47.5% saved
    assert "Spending is up" in titles             # 21,000 vs 5,000
    assert "Food went up" in titles
    assert "Food budget exceeded" in titles


def test_insights_empty_month(client, auth):
    body = client.get("/ai/insights", params={"month": "2026-11"}, headers=auth).json()
    assert body["insights"][0]["kind"] == "tip"


def test_ai_engine_used_when_key_set(client, auth, monkeypatch):
    monkeypatch.setattr(ai, "ANTHROPIC_API_KEY", "test-key")
    calls = []

    def fake_claude(system, prompt, schema, max_tokens=2000):
        calls.append(prompt)
        if "category" in schema["properties"]:
            return {"category": "Entertainment"}
        return {"summary": "AI summary", "insights": [{"kind": "tip", "title": "T", "text": "Do X"}]}

    monkeypatch.setattr(ai, "_ask_claude", fake_claude)
    assert categorize(client, auth, "Swiggy order") == ("Entertainment", "ai")

    add_tx(client, auth, 100, "expense", "Food", day="2026-11-05")
    body = client.get("/ai/insights", params={"month": "2026-11"}, headers=auth).json()
    assert (body["engine"], body["summary"]) == ("ai", "AI summary")
    client.get("/ai/insights", params={"month": "2026-11"}, headers=auth)
    assert len(calls) == 2  # second insights request served from cache


def test_falls_back_to_rules_when_ai_fails(client, auth, monkeypatch):
    monkeypatch.setattr(ai, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai, "_ask_claude", lambda *a, **k: None)
    assert categorize(client, auth, "Swiggy order") == ("Food", "rules")
    assert client.get("/ai/insights", headers=auth).json()["engine"] == "rules"


def test_ask_claude_handles_api_errors(monkeypatch):
    monkeypatch.setattr(ai, "ANTHROPIC_API_KEY", "test-key")

    class Broken:
        class beta:
            class messages:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("network down")

    monkeypatch.setattr(ai, "_get_client", lambda: Broken)
    assert ai._ask_claude("s", "p", {"type": "object"}) is None
