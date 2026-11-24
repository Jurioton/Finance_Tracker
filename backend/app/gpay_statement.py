"""Parse a Google Pay "Transaction statement" PDF into a list of transactions.

A statement row looks like this once the PDF is turned into text:

    01 Oct, 2026   Paid to AMUL APO 2                               ₹40
    11:04 AM       UPI Transaction ID: 130512135802
                   Paid by Union Bank of India 2731

"Paid to ..." is money that left the account (an expense) and "Received from ..." is money that
came in (income). Text extraction from PDFs is not perfectly consistent about spaces (we have seen
"13Oct, 2026" and "UPI Transaction ID:1305..."), so every pattern below tolerates missing or extra
whitespace.
"""
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

# "01 Oct, 2026  Paid to AMUL APO 2   ₹40"  (the amount may be missing if it sits on another line)
ROW = re.compile(
    r"^\s*(?P<day>\d{1,2})\s*(?P<mon>[A-Za-z]{3})[a-z]*\s*,?\s*(?P<year>\d{4})\s+"
    r"(?P<kind>Paid\s*to|Received\s*from|Self\s*transfer\s*(?:to|from)?)\b(?P<party>.*?)"
    r"(?:\s*(?:₹|Rs\.?|INR)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?))?\s*$",
    re.IGNORECASE,
)
AMOUNT = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)")
TIME = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([AP]M)", re.IGNORECASE)
UPI_ID = re.compile(r"UPI\s*Transaction\s*ID\s*:?\s*(\d+)", re.IGNORECASE)
ACCOUNT = re.compile(r"Paid\s*(?:by|to)\s+(.+?)\s*$", re.IGNORECASE)
PERIOD = re.compile(
    r"(\d{1,2})\s*([A-Za-z]+)\s*(\d{4})\s*-\s*(\d{1,2})\s*([A-Za-z]+)\s*(\d{4})")
HEADER_TOTALS = re.compile(r"₹\s*([\d,]+(?:\.\d{1,2})?)\s+₹\s*([\d,]+(?:\.\d{1,2})?)")
NOISE = re.compile(r"^\s*(Note:|received\.|Page\s*\d+\s*of|Transaction\s*statement|Date\s*&\s*time)",
                   re.IGNORECASE)


class StatementError(ValueError):
    """The file could not be read as a Google Pay statement."""


@dataclass
class StatementRow:
    date: date
    time: str | None
    type: str  # "income", "expense" or "transfer"
    amount: float
    party: str
    upi_id: str | None = None
    account: str | None = None

    @property
    def note(self) -> str:
        if self.type == "income":
            return f"Received from {self.party}"
        if self.type == "expense":
            return f"Paid to {self.party}"
        return f"Self transfer ({self.party})" if self.party != "Unknown payee" else "Self transfer"

    def as_dict(self) -> dict:
        data = asdict(self)
        data["note"] = self.note
        return data


def _money(text: str) -> float:
    return float(text.replace(",", ""))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" :-")


def _parse_date(day: str, mon: str, year: str) -> date | None:
    month = MONTHS.get(mon[:3].lower())
    if not month:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def pdf_to_text(raw: bytes) -> str:
    """Extracts text from every page, keeping the visual layout (one statement row per line)."""
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            raise StatementError("This PDF is password protected. Download an unlocked statement from Google Pay.")
        return "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)
    except StatementError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise StatementError("The uploaded file is not a readable PDF") from exc


def parse_statement_text(text: str) -> dict:
    """Turns the statement text into {period, totals, transactions}."""
    lines = text.splitlines()
    rows: list[StatementRow] = []
    current: StatementRow | None = None

    for line in lines:
        if not line.strip() or NOISE.match(line):
            continue
        match = ROW.match(line)
        if match:
            when = _parse_date(match["day"], match["mon"], match["year"])
            if when is None:
                current = None
                continue
            kind = match["kind"].lower().replace(" ", "")
            tx_type = "expense" if kind.startswith("paidto") else "income" if kind.startswith("received") else "transfer"
            party = _clean(match["party"]) or "Unknown payee"
            amount = _money(match["amount"]) if match["amount"] else None
            current = StatementRow(date=when, time=None, type=tx_type, amount=amount or 0.0, party=party)
            rows.append(current)
            continue
        if current is None:
            continue
        # Lines that follow a row belong to it: time, UPI id, bank account, or a stray amount.
        if current.time is None and (t := TIME.match(line)):
            hour, minute, ampm = t.groups()
            current.time = datetime.strptime(f"{hour}:{minute} {ampm.upper()}", "%I:%M %p").strftime("%H:%M")
            rest = line[t.end():]
            if (u := UPI_ID.search(rest)):
                current.upi_id = u.group(1)
            continue
        if current.upi_id is None and (u := UPI_ID.search(line)):
            current.upi_id = u.group(1)
            continue
        if current.account is None and (a := ACCOUNT.search(line)):
            # "Union Bank of India2731" -> "Union Bank of India 2731"
            current.account = re.sub(r"(?<=[A-Za-z])(\d{4})$", r" \1", _clean(a.group(1)))
            continue
        if not current.amount and (m := AMOUNT.search(line)):
            current.amount = _money(m.group(1))

    transactions = [r for r in rows if r.amount > 0]
    if not transactions:
        raise StatementError("No Google Pay transactions were found in this PDF")

    period = None
    if (p := PERIOD.search(text)):
        start = _parse_date(p[1], p[2], p[3])
        end = _parse_date(p[4], p[5], p[6])
        if start and end:
            period = {"start": start, "end": end}

    # The statement header lists "Sent" and "Received" totals; we report them so the UI can show
    # whether everything was picked up. Self transfers are not part of those totals.
    statement_totals = None
    header = text[: p.end() + 200] if p else ""
    if (h := HEADER_TOTALS.search(header)):
        statement_totals = {"sent": _money(h[1]), "received": _money(h[2])}

    parsed_totals = {
        "sent": round(sum(r.amount for r in transactions if r.type == "expense"), 2),
        "received": round(sum(r.amount for r in transactions if r.type == "income"), 2),
    }
    return {
        "period": period,
        "statement_totals": statement_totals,
        "parsed_totals": parsed_totals,
        "totals_match": statement_totals == parsed_totals if statement_totals else None,
        "transactions": transactions,
    }


def parse_statement_pdf(raw: bytes) -> dict:
    text = pdf_to_text(raw)
    if "upi" not in text.lower() and "google pay" not in text.lower():
        raise StatementError("This does not look like a Google Pay statement")
    return parse_statement_text(text)
