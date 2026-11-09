from conftest import register


def test_analytics_returns_period_totals_and_breakdowns(client, auth):
    categories = client.get("/categories", headers=auth).json()
    food = next(category for category in categories if category["name"] == "Food")
    salary = next(category for category in categories if category["name"] == "Salary")

    transactions = [
        {"amount": 50000, "type": "income", "date": "2026-01-01", "note": "Salary", "category_id": salary["id"]},
        {"amount": 1200, "type": "expense", "date": "2026-01-04", "note": "Groceries", "category_id": food["id"]},
        {"amount": 2500, "type": "expense", "date": "2026-02-08", "note": "Dinner", "category_id": food["id"]},
    ]
    for transaction in transactions:
        response = client.post("/transactions", json=transaction, headers=auth)
        assert response.status_code == 201, response.text

    response = client.get(
        "/dashboard/analytics?start_month=2026-01&end_month=2026-03",
        headers=auth,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["income"] == 50000
    assert data["expenses"] == 3700
    assert data["balance"] == 46300
    assert data["average_monthly_expenses"] == round(3700 / 3, 2)
    assert data["transaction_count"] == 3
    assert len(data["monthly"]) == 3
    assert data["monthly"][2]["month"] == "2026-03"
    assert data["by_category"] == [{"category": "Food", "total": 3700}]
    assert data["top_expense"]["amount"] == 2500
    assert data["top_expense"]["merchant"] == "Dinner"


def test_analytics_rejects_invalid_ranges(client, auth):
    reversed_range = client.get(
        "/dashboard/analytics?start_month=2026-03&end_month=2026-01",
        headers=auth,
    )
    assert reversed_range.status_code == 400

    too_long = client.get(
        "/dashboard/analytics?start_month=2024-01&end_month=2026-02",
        headers=auth,
    )
    assert too_long.status_code == 400


def test_analytics_requires_authentication(client):
    response = client.get("/dashboard/analytics?start_month=2026-01&end_month=2026-03")
    assert response.status_code == 401
