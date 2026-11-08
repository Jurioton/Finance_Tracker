from .conftest import register


def category_id(client, auth, name, type="expense"):
    cats = client.get("/categories", params={"type": type}, headers=auth).json()
    return next(c["id"] for c in cats if c["name"] == name)


def add_tx(client, auth, amount, type, cat, day="2026-11-05", note=""):
    res = client.post("/transactions", headers=auth, json={
        "amount": amount, "type": type, "date": day, "note": note,
        "category_id": category_id(client, auth, cat, type)})
    assert res.status_code == 201, res.text
    return res.json()


def test_register_login_and_me(client):
    register(client)
    res = client.post("/auth/login", data={"username": "a@example.com", "password": "secret123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["email"] == "a@example.com"
    assert client.post("/auth/login", data={"username": "a@example.com", "password": "wrong"}).status_code == 401


def test_duplicate_email_rejected(client):
    register(client)
    res = client.post("/auth/register", json={"name": "X", "email": "A@example.com", "password": "secret123"})
    assert res.status_code == 400


def test_protected_routes_need_token(client):
    assert client.get("/transactions").status_code == 401


def test_default_categories_created(client, auth):
    names = {c["name"] for c in client.get("/categories", headers=auth).json()}
    assert {"Food", "Rent", "Salary"} <= names


def test_transaction_crud_and_filters(client, auth):
    tx = add_tx(client, auth, 250, "expense", "Food", note="Groceries")
    add_tx(client, auth, 50000, "income", "Salary")
    add_tx(client, auth, 100, "expense", "Food", day="2026-10-20")

    assert len(client.get("/transactions", headers=auth).json()) == 3
    assert len(client.get("/transactions", params={"month": "2026-11"}, headers=auth).json()) == 2
    assert len(client.get("/transactions", params={"type": "income"}, headers=auth).json()) == 1
    assert len(client.get("/transactions", params={"search": "grocer"}, headers=auth).json()) == 1

    res = client.put(f"/transactions/{tx['id']}", json={"amount": 300}, headers=auth)
    assert res.json()["amount"] == 300
    assert client.delete(f"/transactions/{tx['id']}", headers=auth).status_code == 204
    assert client.get(f"/transactions/{tx['id']}", headers=auth).status_code == 404


def test_category_type_must_match(client, auth):
    res = client.post("/transactions", headers=auth, json={
        "amount": 10, "type": "income", "date": "2026-11-01",
        "category_id": category_id(client, auth, "Food")})
    assert res.status_code == 400


def test_negative_amount_rejected(client, auth):
    res = client.post("/transactions", headers=auth, json={
        "amount": -5, "type": "expense", "date": "2026-11-01",
        "category_id": category_id(client, auth, "Food")})
    assert res.status_code == 422


def test_users_cannot_see_each_other(client, auth):
    tx = add_tx(client, auth, 99, "expense", "Food")
    other = register(client, "b@example.com")
    assert client.get("/transactions", headers=other).json() == []
    assert client.get(f"/transactions/{tx['id']}", headers=other).status_code == 404


def test_budget_status(client, auth):
    food = category_id(client, auth, "Food")
    budget = client.post("/budgets", headers=auth, json={"category_id": food, "limit": 1000, "month": "2026-11"}).json()
    assert budget["status"] == "ok"
    add_tx(client, auth, 850, "expense", "Food")
    b = client.get("/budgets", params={"month": "2026-11"}, headers=auth).json()[0]
    assert (b["spent"], b["status"]) == (850, "warning")
    add_tx(client, auth, 200, "expense", "Food")
    b = client.get("/budgets", params={"month": "2026-11"}, headers=auth).json()[0]
    assert b["status"] == "over"


def test_goals(client, auth):
    goal = client.post("/goals", headers=auth, json={"name": "Laptop", "target_amount": 60000}).json()
    assert goal["percent"] == 0
    goal = client.post(f"/goals/{goal['id']}/contribute", json={"amount": 15000}, headers=auth).json()
    assert (goal["percent"], goal["remaining"]) == (25, 45000)
    goal = client.post(f"/goals/{goal['id']}/contribute", json={"amount": 50000}, headers=auth).json()
    assert goal["completed"] is True


def test_dashboard(client, auth):
    add_tx(client, auth, 40000, "income", "Salary")
    add_tx(client, auth, 10000, "expense", "Rent")
    add_tx(client, auth, 2000, "expense", "Food")
    add_tx(client, auth, 500, "expense", "Food", day="2026-10-03")

    s = client.get("/dashboard/summary", params={"month": "2026-11"}, headers=auth).json()
    assert (s["income"], s["expenses"], s["balance"], s["savings_rate"]) == (40000, 12000, 28000, 70)
    assert s["by_category"][0] == {"category": "Rent", "total": 10000}

    t = client.get("/dashboard/trends", params={"months": 3, "end_month": "2026-11"}, headers=auth).json()
    assert [p["month"] for p in t] == ["2026-09", "2026-10", "2026-11"]
    assert t[1]["expenses"] == 500


def test_csv_export(client, auth):
    add_tx(client, auth, 250, "expense", "Food", note="Lunch")
    res = client.get("/transactions/export", headers=auth)
    assert res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0] == "date,type,category,amount,note"
    assert "Food,250.00,Lunch" in lines[1]
