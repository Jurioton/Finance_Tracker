"""Regenerates the made-up bank statements used by test_bank_statement.py.

Each file holds the same ten transactions laid out the way a different kind of bank exports them,
so the tests can check that the reader gives the same answer for every layout. Every name, number
and account here is fictional.

Needs reportlab and xlwt, which the app itself does not require:
    pip install reportlab xlwt && python tests/fixtures/make_bank_fixtures.py
"""
import csv
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
OPENING = 10000.00

# (date, narration, debit, credit)
ROWS = [
    (date(2026, 10, 1), "UPI/DR/600000000001/CITY METRO TRANSPORT/YESB/citymetro@ybl/Payment", 40.00, None),
    (date(2026, 10, 1), "NEFT-DEMO0001234-MONTHLY STIPEND CO-STIPEND OCT", None, 15000.00),
    (date(2026, 10, 3), "UPI/DR/600000000002/GREEN LEAF TEA KADAI/SBIN/greenleaf@oksbi/UPI", 30.00, None),
    (date(2026, 10, 5), "ATM WDL-ATM CASH 4321 MG ROAD", 2000.00, None),
    (date(2026, 10, 9), "POS 416021XXXXXX1234 SUNRISE PHARMACY", 210.50, None),
    (date(2026, 10, 12), "UPI/CR/600000000003/ASHA KUMAR/HDFC/asha.k@okhdfcbank/Dinner split", None, 650.00),
    (date(2026, 10, 15), "ACH D- DEMO FINANCE LTD-EMI 7788", 3500.00, None),
    (date(2026, 10, 20), "UPI/DR/600000000004/RAVI SHANKAR/ICIC/ravi.s@okicici/rent share", 4000.00, None),
    (date(2026, 10, 20), "UPI/DR/600000000004/RAVI SHANKAR/ICIC/ravi.s@okicici/rent share", 4000.00, None),
    (date(2026, 10, 31), "SB INTEREST CREDIT", None, 42.25),
]


def with_balances():
    balance, out = OPENING, []
    for when, narration, debit, credit in ROWS:
        balance = round(balance - (debit or 0) + (credit or 0), 2)
        out.append((when, narration, debit, credit, balance))
    return out


def money(value):
    return "" if value is None else f"{value:,.2f}"


def sbi_csv():
    """SBI-like CSV: account details above the table, "01 Oct 2026" dates, Debit/Credit/Balance."""
    path = HERE / "bank_sbi_style.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Account Name", ":", "DEMO USER"])
        w.writerow(["Account Number", ":", "00000012345678"])
        w.writerow(["Branch", ":", "State Bank of India, Demo Branch"])
        w.writerow(["IFS Code", ":", "SBIN0000001"])
        w.writerow([])
        w.writerow(["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Debit", "Credit", "Balance"])
        for when, narration, debit, credit, balance in with_balances():
            d = when.strftime("%d %b %Y")
            w.writerow([d, d, narration, "", money(debit), money(credit), money(balance)])
        w.writerow([])
        w.writerow(["**This is a computer generated statement**"])


def kotak_csv():
    """Semicolon separated, one Amount column plus a Dr / Cr column, dd-mm-yyyy dates, newest first."""
    path = HERE / "bank_amount_drcr.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Sl. No.", "Transaction Date", "Value Date", "Description", "Chq / Ref No.", "Amount",
                    "Dr / Cr", "Balance", "Dr / Cr"])
        rows = with_balances()
        for i, (when, narration, debit, credit, balance) in enumerate(reversed(rows), start=1):
            d = when.strftime("%d-%m-%Y")
            w.writerow([i, d, d, narration, "", f"{debit or credit:.2f}", "DR" if debit else "CR",
                        f"{balance:.2f}", "CR"])


def icici_xlsx():
    """ICICI-like .xlsx: real date cells, "Withdrawal Amount (INR )" headings, numbers as numbers."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["DETAILED STATEMENT"])
    ws.append(["Account Number", "000101234567 ( INR ) - DEMO USER"])
    ws.append(["ICICI Bank Ltd"])
    ws.append([])
    ws.append(["S No.", "Value Date", "Transaction Date", "Cheque Number", "Transaction Remarks",
               "Withdrawal Amount (INR )", "Deposit Amount (INR )", "Balance (INR )"])
    for i, (when, narration, debit, credit, balance) in enumerate(with_balances(), start=1):
        ws.append([i, when, when, "-", narration, debit or 0, credit or 0, balance])
    ws.append([])
    ws.append(["Legends Used in Account Statement"])
    wb.save(HERE / "bank_icici_style.xlsx")


def hdfc_xls():
    """HDFC-like binary .xls: dd/mm/yy dates, "*****" rule, wrapped narration on a second row."""
    import xlwt

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Statement")
    lines = [
        ["HDFC BANK Ltd.", "", "", "", "", "", ""],
        ["Statement of account", "", "", "", "", "", ""],
        ["", "", "", "", "", "", ""],
        ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
        ["********", "********", "********", "********", "********", "********", "********"],
    ]
    for when, narration, debit, credit, balance in with_balances():
        d = when.strftime("%d/%m/%y")
        first, rest = (narration[:40], narration[40:]) if len(narration) > 40 else (narration, "")
        lines.append([d, first, "0000600000000000", d, debit or "", credit or "", balance])
        if rest:
            lines.append(["", rest, "", "", "", "", ""])
    lines += [["", "", "", "", "", "", ""], ["STATEMENT SUMMARY :-", "", "", "", "", "", ""],
              ["Opening Balance", "Dr Count", "Cr Count", "Debits", "Credits", "Closing Bal", ""],
              [OPENING, 7, 3, 13780.50, 15692.25, with_balances()[-1][4], ""]]
    for r, line in enumerate(lines):
        for c, value in enumerate(line):
            ws.write(r, c, value)
    wb.save(str(HERE / "bank_hdfc_style.xls"))


def html_xls():
    """Some banks' "Excel" download is really an HTML table with an .xls name."""
    rows = "".join(
        f"<tr><td>{w:%d-%b-%Y}</td><td>{n}</td><td>{money(d)}</td><td>{money(c)}</td><td>{money(b)}</td></tr>"
        for w, n, d, c, b in with_balances())
    html = ("<html><body><p>Federal Bank - Account Statement</p><table>"
            "<tr><th>Date</th><th>Particulars</th><th>Withdrawals</th><th>Deposits</th><th>Balance</th></tr>"
            f"{rows}</table></body></html>")
    (HERE / "bank_html_table.xls").write_text(html, encoding="utf-8")


def pdf(path: Path, encrypt: str | None = None, style: str = "columns"):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4, encrypt=encrypt)
    width, height = A4
    rows = with_balances()
    pages = [rows[:6], rows[6:]]
    for number, page_rows in enumerate(pages, start=1):
        c.setFont("Helvetica", 8)
        y = height - 40
        if number == 1:
            for line in ["Axis Bank Ltd", "Statement of Account for the period 01-10-2026 to 31-10-2026",
                         "Customer: DEMO USER   IFSC: UTIB0000001"]:
                c.drawString(40, y, line)
                y -= 12
            y -= 8
        if style == "columns":
            heads = [(40, "Tran Date"), (100, "Particulars"), (380, "Debit"), (450, "Credit"), (520, "Balance")]
        else:
            heads = [(40, "Date"), (100, "Narration"), (430, "Amount"), (520, "Balance")]
        for x, text in heads:
            c.drawString(x, y, text)
        y -= 16
        if number == 1:
            c.drawString(100, y, "OPENING BALANCE")
            c.drawRightString(560, y, f"{OPENING:,.2f}" + (" Cr" if style != "columns" else ""))
            y -= 14
        for when, narration, debit, credit, balance in page_rows:
            first, rest = (narration[:48], narration[48:]) if len(narration) > 48 else (narration, "")
            c.drawString(40, y, when.strftime("%d-%m-%Y"))
            c.drawString(100, y, first)
            if style == "columns":
                if debit:
                    c.drawRightString(410, y, f"{debit:,.2f}")
                if credit:
                    c.drawRightString(480, y, f"{credit:,.2f}")
                c.drawRightString(560, y, f"{balance:,.2f}")
            else:
                c.drawRightString(480, y, f"{debit or credit:,.2f} {'Dr' if debit else 'Cr'}")
                c.drawRightString(560, y, f"{balance:,.2f} Cr")
            y -= 12
            if rest:
                c.drawString(100, y, rest)
                y -= 12
        c.drawString(40, 40, f"Page {number} of {len(pages)}")
        c.showPage()
    c.save()


if __name__ == "__main__":
    sbi_csv()
    kotak_csv()
    icici_xlsx()
    hdfc_xls()
    html_xls()
    pdf(HERE / "bank_columns.pdf")
    pdf(HERE / "bank_locked.pdf", encrypt="demo1234", style="drcr")
    print("written")
