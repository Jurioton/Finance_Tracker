from pathlib import Path

import pytest

from app.gpay_statement import StatementError, parse_statement_pdf, parse_statement_text

from .conftest import register

SAMPLE = (Path(__file__).parent / "fixtures" / "gpay_statement_sample.pdf").read_bytes()


def test_parses_every_row_and_matches_statement_totals():
    result = parse_statement_pdf(SAMPLE)
    rows = result["transactions"]
    assert len(rows) == 9
    assert result["totals_match"] is True
    assert result["statement_totals"] == {"sent": 416.0, "received": 3250.5}
    assert str(result["period"]["start"]) == "2026-10-01" and str(result["period"]["end"]) == "2026-10-31"

    first = rows[0]
    assert (first.type, first.amount, first.party, first.upi_id, first.time) == (
        "expense", 40.0, "CITY METRO TRANSPORT", "100000000001", "09:15")
    assert rows[1].type == "income" and rows[1].amount == 2000.0
    assert rows[5].type == "transfer"
    # "13Oct, 2026" (no space) and a decimal amount with a thousands separator
    assert str(rows[6].date) == "2026-10-13" and rows[6].amount == 1250.5
    # A row whose payee name is blank on the statement
    assert rows[7].party == "Unknown payee" and rows[7].note == "Paid to Unknown payee"


def test_text_without_transactions_is_rejected():
    with pytest.raises(StatementError):
        parse_statement_text("Transaction statement\nNothing here")


def test_preview_suggests_categories_and_saves_nothing(client):
    auth = register(client)
    res = client.post("/statements/gpay/preview", headers=auth,
                      files={"file": ("statement.pdf", SAMPLE, "application/pdf")})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["totals_match"] is True
    assert data["skipped_transfers"] == 1
    assert len(data["transactions"]) == 8

    categories = {c["id"]: c["name"] for c in client.get("/categories", headers=auth).json()}
    by_party = {t["party"]: t for t in data["transactions"]}
    assert categories[by_party["CITY METRO TRANSPORT"]["suggested_category_id"]] == "Transport"
    assert categories[by_party["GREEN LEAF TEA KADAI"]["suggested_category_id"]] == "Food"
    assert categories[by_party["Monthly Stipend Co"]["suggested_category_id"]] == "Salary"
    assert categories[by_party["Asha Kumar"]["suggested_category_id"]] == "Other"
    assert not any(t["duplicate"] for t in data["transactions"])
    assert client.get("/transactions", headers=auth).json() == []


def test_import_creates_transactions_and_skips_duplicates(client):
    auth = register(client)
    preview = client.post("/statements/gpay/preview", headers=auth,
                          files={"file": ("statement.pdf", SAMPLE, "application/pdf")}).json()
    payload = {"transactions": [
        {"date": t["date"], "type": t["type"], "amount": t["amount"], "note": t["note"],
         "category_id": t["suggested_category_id"], "upi_id": t["upi_id"]}
        for t in preview["transactions"]
    ]}
    res = client.post("/statements/gpay/import", headers=auth, json=payload)
    assert res.status_code == 201, res.text
    assert res.json() == {"imported": 8, "skipped_duplicates": 0}

    saved = client.get("/transactions", headers=auth).json()
    assert len(saved) == 8
    assert round(sum(t["amount"] for t in saved if t["type"] == "expense"), 2) == 416.0
    assert round(sum(t["amount"] for t in saved if t["type"] == "income"), 2) == 3250.5

    # Uploading the same statement again marks every row as already imported...
    again = client.post("/statements/gpay/preview", headers=auth,
                        files={"file": ("statement.pdf", SAMPLE, "application/pdf")}).json()
    assert all(t["duplicate"] for t in again["transactions"])
    # ...and importing it again adds nothing.
    res = client.post("/statements/gpay/import", headers=auth, json=payload)
    assert res.json() == {"imported": 0, "skipped_duplicates": 8}
    assert len(client.get("/transactions", headers=auth).json()) == 8


def test_import_rejects_category_of_wrong_type(client):
    auth = register(client)
    expense_cat = next(c for c in client.get("/categories", headers=auth).json() if c["type"] == "expense")
    res = client.post("/statements/gpay/import", headers=auth, json={"transactions": [
        {"date": "2026-10-01", "type": "income", "amount": 10, "note": "x", "category_id": expense_cat["id"]}]})
    assert res.status_code == 400
    assert client.get("/transactions", headers=auth).json() == []


def test_preview_rejects_non_pdf_and_requires_auth(client):
    assert client.post("/statements/gpay/preview",
                       files={"file": ("s.pdf", SAMPLE, "application/pdf")}).status_code == 401
    auth = register(client)
    res = client.post("/statements/gpay/preview", headers=auth,
                      files={"file": ("s.txt", b"hello", "text/plain")})
    assert res.status_code == 415
