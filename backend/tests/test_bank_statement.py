"""The bank statement reader must give the same answer whatever the bank's layout or file type.

The fixtures are made-up statements (see fixtures/make_bank_fixtures.py) holding the same ten
transactions: 7 debits worth ₹13,780.50 and 3 credits worth ₹15,692.25, from ₹10,000 to ₹11,911.75.
"""
from pathlib import Path

import pytest

from app.bank_statement import (PasswordRequired, StatementError, describe, parse_amount,
                                parse_bank_statement, parse_date)

from .conftest import register

FIXTURES = Path(__file__).parent / "fixtures"
LAYOUTS = {
    "bank_sbi_style.csv": ("CSV", "State Bank of India"),
    "bank_amount_drcr.csv": ("CSV", None),  # one Amount column + Dr/Cr column, newest first, ";" separated
    "bank_icici_style.xlsx": ("Excel", "ICICI Bank"),
    "bank_hdfc_style.xls": ("Excel", "HDFC Bank"),  # binary .xls with wrapped narrations
    "bank_html_table.xls": ("Excel", None),  # an HTML table saved with an .xls name
    "bank_columns.pdf": ("PDF", "Axis Bank"),  # two pages, header repeated, opening balance line
}


def read(name, password=None):
    return parse_bank_statement((FIXTURES / name).read_bytes(), password)


@pytest.mark.parametrize("name", LAYOUTS)
def test_every_layout_reads_the_same_transactions(name):
    result = read(name)
    file_type, bank = LAYOUTS[name]
    rows = result["transactions"]

    assert result["file_type"] == file_type
    assert result["bank_name"] == bank
    assert len(rows) == 10
    assert result["parsed_totals"] == {"sent": 13780.5, "received": 15692.25}
    assert result["opening_balance"] == 10000.0 and result["closing_balance"] == 11911.75
    assert result["balance_ok"] is True
    assert str(result["period"]["start"]) == "2026-10-01" and str(result["period"]["end"]) == "2026-10-31"
    assert [r.type for r in rows] == ["expense", "income", "expense", "expense", "expense",
                                      "income", "expense", "expense", "expense", "income"]

    by_note = {r.note: r for r in rows}
    assert by_note["City Metro Transport"].upi_ref == "600000000001"
    assert by_note["ATM cash withdrawal"].amount == 2000.0
    assert by_note["Sunrise Pharmacy"].amount == 210.5
    assert by_note["Interest"].type == "income"
    # Two identical payments on the same day stay two transactions with different references,
    # and the references are the same whichever file type the statement came in.
    assert len({r.reference for r in rows}) == 10
    assert [r.reference for r in rows] == [r.reference for r in read("bank_sbi_style.csv")["transactions"]]


def test_locked_pdf_needs_the_password():
    with pytest.raises(PasswordRequired) as missing:
        read("bank_locked.pdf")
    assert missing.value.wrong is False
    with pytest.raises(PasswordRequired) as wrong:
        read("bank_locked.pdf", "nope")
    assert wrong.value.wrong is True

    # This one has a single Amount column with "Dr"/"Cr" after each figure and "Cr" balances
    result = read("bank_locked.pdf", "demo1234")
    assert len(result["transactions"]) == 10
    assert result["parsed_totals"] == {"sent": 13780.5, "received": 15692.25}
    assert result["balance_ok"] is True


def test_signed_amounts_without_balance():
    csv = ("Date,Details,Amount\n"
           "2026-11-02,UPI-ZOMATO-zomato@icici-ICIC0000001-512345678901-Order,-349.00\n"
           "2026-11-03,SALARY NOV ACME TECH,52000\n"
           "2026-11-04,Electricity bill KSEB,\"-1,250.00\"\n")
    result = parse_bank_statement(csv.encode())
    rows = result["transactions"]
    assert [(r.type, r.amount) for r in rows] == [("expense", 349.0), ("income", 52000.0), ("expense", 1250.0)]
    assert rows[0].party == "Zomato" and rows[0].reference == "upi:512345678901"
    assert result["balance_ok"] is None  # no balance column, nothing to check against


def test_balance_decides_direction_when_columns_do_not():
    # No Dr/Cr anywhere: the change in balance tells debits from credits.
    csv = ("Txn Date,Particulars,Amount,Balance\n"
           "01/11/2026,Opening Balance,,5000.00\n"
           "02/11/2026,TO TRANSFER-UPI/412300000001/Rent,3000.00,2000.00\n"
           "05/11/2026,BY TRANSFER-REFUND FROM SHOP,500.00,2500.00\n")
    rows = parse_bank_statement(csv.encode())["transactions"]
    assert [(r.type, r.amount) for r in rows] == [("expense", 3000.0), ("income", 500.0)]


def test_a_broken_balance_chain_is_reported():
    csv = ("Date,Narration,Withdrawal,Deposit,Balance\n"
           "01/11/2026,Coffee,100.00,,900.00\n"
           "02/11/2026,Lunch,200.00,,600.00\n")  # 900 - 200 is 700, so a row is missing
    result = parse_bank_statement(csv.encode())
    assert result["balance_ok"] is False and result["balance_mismatches"] == 1


def test_month_first_dates_are_detected():
    csv = ("Date,Description,Debit,Credit\n"
           "11/02/2026,Coffee,100.00,\n"
           "11/25/2026,Lunch,200.00,\n")
    rows = parse_bank_statement(csv.encode())["transactions"]
    assert [str(r.date) for r in rows] == ["2026-11-02", "2026-11-25"]


def test_plain_text_statement_without_a_header():
    text = ("Demo Bank statement\n"
            "03-11-2026  UPI/DR/700000000001/BLUE CAB CO/ybl     120.00    880.00\n"
            "04-11-2026  NEFT CR ACME TECH SALARY               5,000.00  5,880.00\n")
    rows = parse_bank_statement(text.encode())["transactions"]
    assert [(r.type, r.amount, r.balance) for r in rows] == [("expense", 120.0, 880.0), ("income", 5000.0, 5880.0)]


def test_helpers():
    assert parse_amount("1,23,456.50 Dr") == (123456.5, "dr")
    assert parse_amount("(250.00)") == (250.0, "dr")
    assert parse_amount("₹ 1,000") == (1000.0, None)
    assert parse_amount("-") == (None, None)
    assert str(parse_date("01-Oct-2026")) == "2026-10-01"
    assert str(parse_date("1 OCT 26")) == "2026-10-01"
    assert str(parse_date("01/10/26")) == "2026-10-01"
    assert str(parse_date("2026-10-01 10:30:00")) == "2026-10-01"
    assert describe("UPI-SWIGGY-swiggy@ybl-YESB0YBLUPI-412345678901-PAYMENT")["party"] == "Swiggy"
    assert describe("NEFT-HDFCN52026112412345-ACME TECH PVT LTD-SALARY OCT")["note"] == "Acme Tech Pvt Ltd (Salary Oct)"
    assert describe("POS 416021XXXXXX1234 AMAZON IN")["party"] == "Amazon"
    assert describe("UPI/412345678912/Payment/zomato@icici/ICICI Bank")["party"] == "Zomato"


def test_unreadable_files_are_rejected():
    with pytest.raises(StatementError):
        parse_bank_statement(b"hello, this is not a statement\n")
    with pytest.raises(StatementError):
        parse_bank_statement(b"%PDF-1.4 broken")


# ---------------------------------------------------------------- API
def upload(client, auth, name, password=None):
    data = {"password": password} if password else None
    return client.post("/statements/bank/preview", headers=auth, data=data,
                       files={"file": (name, (FIXTURES / name).read_bytes())})


def payload(preview):
    return {"transactions": [
        {"date": t["date"], "type": t["type"], "amount": t["amount"], "note": t["note"],
         "category_id": t["suggested_category_id"], "reference": t["reference"]}
        for t in preview["transactions"]
    ]}


def test_preview_suggests_categories_and_saves_nothing(client):
    auth = register(client)
    res = upload(client, auth, "bank_sbi_style.csv")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["bank_name"] == "State Bank of India" and data["totals_match"] is True
    assert len(data["transactions"]) == 10

    categories = {c["id"]: c["name"] for c in client.get("/categories", headers=auth).json()}
    by_note = {t["note"]: categories[t["suggested_category_id"]] for t in data["transactions"]}
    assert by_note["City Metro Transport"] == "Transport"
    assert by_note["Green Leaf Tea Kadai"] == "Food"
    assert by_note["Sunrise Pharmacy"] == "Health"
    assert by_note["Monthly Stipend Co (Stipend Oct)"] == "Salary"
    assert client.get("/transactions", headers=auth).json() == []


def test_locked_pdf_over_the_api(client):
    auth = register(client)
    res = upload(client, auth, "bank_locked.pdf")
    assert res.status_code == 423 and res.json()["detail"]["code"] == "password_required"
    res = upload(client, auth, "bank_locked.pdf", "wrong")
    assert res.status_code == 423 and res.json()["detail"]["code"] == "password_wrong"
    res = upload(client, auth, "bank_locked.pdf", "demo1234")
    assert res.status_code == 200 and len(res.json()["transactions"]) == 10


def test_import_then_reimport_from_another_format_adds_nothing(client):
    auth = register(client)
    preview = upload(client, auth, "bank_sbi_style.csv").json()
    res = client.post("/statements/bank/import", headers=auth, json=payload(preview))
    assert res.status_code == 201, res.text
    assert res.json() == {"imported": 10, "skipped_duplicates": 0}
    saved = client.get("/transactions", headers=auth).json()
    assert round(sum(t["amount"] for t in saved if t["type"] == "expense"), 2) == 13780.5

    again = upload(client, auth, "bank_sbi_style.csv").json()
    assert all(t["duplicate"] for t in again["transactions"])
    assert client.post("/statements/bank/import", headers=auth, json=payload(again)).json() == {
        "imported": 0, "skipped_duplicates": 10}


def test_upi_payment_from_google_pay_is_not_imported_twice(client):
    auth = register(client)
    category = next(c for c in client.get("/categories", headers=auth).json() if c["name"] == "Transport")
    gpay = {"transactions": [{"date": "2026-10-01", "type": "expense", "amount": 40, "note": "Paid to metro",
                              "category_id": category["id"], "upi_id": "600000000001"}]}
    assert client.post("/statements/gpay/import", headers=auth, json=gpay).json()["imported"] == 1

    preview = upload(client, auth, "bank_sbi_style.csv").json()
    metro = next(t for t in preview["transactions"] if t["note"] == "City Metro Transport")
    assert metro["duplicate"] is True
    assert sum(t["duplicate"] for t in preview["transactions"]) == 1
    result = client.post("/statements/bank/import", headers=auth, json=payload(preview)).json()
    assert result == {"imported": 9, "skipped_duplicates": 1}


def test_bad_reference_is_rejected(client):
    auth = register(client)
    category = client.get("/categories", headers=auth).json()[0]
    body = {"transactions": [{"date": "2026-10-01", "type": category["type"], "amount": 1, "note": "x",
                              "category_id": category["id"], "reference": "gpay:<script>"}]}
    assert client.post("/statements/bank/import", headers=auth, json=body).status_code == 422
