"""Read a bank account statement from any Indian bank and turn it into transactions.

Banks all export statements differently, so nothing here is tied to one bank. The reader:

1. Works out the file type from its bytes, not its name: PDF, Excel (.xlsx or old .xls), CSV/TSV,
   an HTML table saved as ".xls" (several banks do this), or a plain-text statement.
2. Finds the header row by its words ("Txn Date", "Narration", "Withdrawal Amt.", "Deposit",
   "Dr / Cr", "Closing Balance", ...) and maps each column to a role. A PDF has no real columns, so
   the position of each header word on the line stands in for the column.
3. Reads each dated row. Lines without a date continue the previous row's description.
4. Decides debit or credit from, in order: separate debit and credit columns, a Dr/Cr marker or
   column, a minus sign, and keywords. Whenever the statement has a running balance, the change in
   balance overrides all of these, because it is arithmetic rather than a guess.
5. Checks that every balance follows from the previous one, so the person can see whether
   anything was missed.

Debits become expenses and credits become income. The narration ("UPI/DR/412345678901/SWIGGY/
YESB/swiggy@ybl/Payment") is cleaned into a readable payee ("Swiggy") for the note and for
category suggestions, and a UPI reference number is kept so the same payment imported from a
Google Pay statement is recognised as a duplicate.
"""
import csv
import hashlib
import io
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

MAX_ROWS = 5000


class StatementError(ValueError):
    """The file could not be read as a bank statement. The message is shown to the person."""


class PasswordRequired(StatementError):
    """The PDF is locked. `wrong` is True when a password was given but did not open it."""

    def __init__(self, wrong: bool):
        self.wrong = wrong
        super().__init__("That password did not open the PDF" if wrong else
                         "This PDF is password protected. Enter the statement password to open it.")


# ---------------------------------------------------------------- dates
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
MONTH_WORDS = set(MONTHS) | {"sept", "january", "february", "march", "april", "june", "july", "august",
                             "september", "october", "november", "december"}
NUMERIC_DATE = r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})(?![\d/])"
TEXT_DATE = r"(?<!\d)(\d{1,2})[\s\-/]?([A-Za-z]{3,9})[\s\-/,]{0,3}(\d{4}|\d{2})(?!\d)"
ISO_DATE = r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)"
ANY_DATE = re.compile(f"{ISO_DATE}|{NUMERIC_DATE}|{TEXT_DATE}")


def _year(text: str) -> int:
    year = int(text)
    return year + 2000 if year < 100 else year


def _make_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _date_from_match(m: re.Match, dayfirst: bool) -> date | None:
    if m.group(1):  # ISO 2026-10-01
        return _make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if m.group(4):  # 01/10/2026 (Indian banks put the day first)
        a, b, year = int(m.group(4)), int(m.group(5)), _year(m.group(6))
        day, month = (a, b) if dayfirst else (b, a)
        return _make_date(year, month, day)
    word = m.group(8).lower()  # 01-Oct-2026, 01 Oct 26, 1OCT2026
    if word not in MONTH_WORDS:
        return None
    return _make_date(_year(m.group(9)), MONTHS[word[:3]], int(m.group(7)))


def parse_date(value, dayfirst: bool = True) -> date | None:
    """A date from a cell: a datetime from Excel, or text in any of the usual formats."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    m = ANY_DATE.search(value.strip()[:40])
    return _date_from_match(m, dayfirst) if m else None


def detect_dayfirst(texts) -> bool:
    """True unless the numeric dates can only be month-first (some month part is above 12)."""
    month_first_seen = False
    for text in texts:
        if not isinstance(text, str):
            continue
        for m in re.finditer(NUMERIC_DATE, text):
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12:
                return True
            if b > 12:
                month_first_seen = True
    return not month_first_seen


# ---------------------------------------------------------------- amounts
MONEY_WORDS = re.compile(r"₹|\bRs\.?|\bINR\b", re.IGNORECASE)
MARKER = re.compile(r"\b(cr|dr|credit|debit)\b\.?", re.IGNORECASE)


def parse_amount(value) -> tuple[float | None, str | None]:
    """(amount, marker) from a cell: "1,23,456.50", "500.00 Dr", "(250.00)", "-75", 1200.0, "-".

    marker is "dr" / "cr" when the cell says so, and a negative amount comes back as "dr".
    """
    if isinstance(value, bool) or value is None:
        return None, None
    if isinstance(value, (int, float)):
        if value == 0:
            return None, None
        return (abs(float(value)), "dr") if value < 0 else (float(value), None)
    text = MONEY_WORDS.sub("", str(value)).strip()
    if not text:
        return None, None
    marker = None
    if (m := MARKER.search(text)):
        marker = "cr" if m.group(1).lower().startswith("c") else "dr"
        text = MARKER.sub("", text)
    text = text.replace(",", "").replace(" ", "")
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    text = text.strip("-+()")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None, None
    amount = float(text)
    if amount == 0:
        return None, None
    if negative and marker is None:
        marker = "dr"
    return amount, marker


def parse_balance(value) -> float | None:
    """A balance; "Dr" or a minus sign means overdrawn, so the balance is negative."""
    amount, marker = parse_amount(value)
    if amount is None:
        if isinstance(value, (int, float)) and value == 0 or (isinstance(value, str) and re.fullmatch(
                r"\s*0+(\.0+)?\s*(cr|dr)?\s*", value, re.IGNORECASE)):
            return 0.0
        return None
    return -amount if marker == "dr" else amount


# ---------------------------------------------------------------- header detection
def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", str(text).lower()))


def header_role(cell) -> str | None:
    """Which column a header cell names, or None."""
    if not isinstance(cell, str):
        return None
    text = cell.lower()
    w = _words(text)
    if not w or len(text) > 60:
        return None
    if w & {"balance", "bal", "balances"}:
        return "balance"
    if ({"dr", "cr"} <= w or {"debit", "credit"} <= w or w & {"drcr", "crdr"}
            or w in ({"type"}, {"txn", "type"}, {"transaction", "type"})):
        return "dctype"
    if w & {"date", "dt"}:
        return "value_date" if "value" in w else "date"
    if w & {"withdrawal", "withdrawals", "debit", "debits", "dr", "withdrawn"} or "paid out" in text \
            or "money out" in text:
        return "debit"
    if w & {"deposit", "deposits", "credit", "credits", "cr"} or "paid in" in text or "money in" in text:
        return "credit"
    if w & {"narration", "description", "particulars", "remarks", "remark", "details", "detail"}:
        return "desc"
    if w & {"amount", "amt"}:
        return "amount"
    if w & {"chq", "cheque", "chqno", "ref", "reference", "refno", "utr", "instrument"}:
        return "ref"
    return None


def columns_from_header(cells) -> dict[str, int] | None:
    """Maps roles to column indexes if this row looks like a statement header."""
    roles: dict[str, int] = {}
    for i, cell in enumerate(cells):
        role = header_role(cell)
        if role and role not in roles:
            roles[role] = i
    if "date" not in roles and "value_date" in roles:
        roles["date"] = roles.pop("value_date")
    has_money = ("debit" in roles and "credit" in roles) or "amount" in roles
    if "date" in roles and has_money and len(roles) >= 3:
        return roles
    return None


# ---------------------------------------------------------------- narration -> payee
NOISE_WORDS = {
    "upi", "dr", "cr", "p2m", "p2a", "p2p", "neft", "imps", "rtgs", "to", "by", "transfer", "trf", "tfr",
    "payment", "payments", "pay", "paid", "inb", "mb", "ib", "ref", "txn", "from", "na", "others", "sent",
    "received", "collect", "request", "mob", "mmt", "ach", "nach", "ecs", "pos", "via", "using", "upiintent",
    "intent", "mandate", "debit", "credit", "card", "inr", "rs", "no", "of", "the", "and", "for", "in", "at",
    "ft", "fund", "funds", "online", "net", "banking", "netbanking", "mobile", "app", "bil", "onl", "ecom",
    "purchase", "txnid", "id", "rrn", "chq", "cheque", "clg", "clearing", "self", "a", "c", "ac", "acct",
    "phone", "phonepe", "gpay", "paytm", "bhim", "ok", "upilite", "lite", "qr", "dynamic", "static", "sms",
}
BANK_CODES = {
    "sbin", "hdfc", "icic", "utib", "yesb", "kkbk", "punb", "barb", "cnrb", "ubin", "idib", "ioba", "bkid",
    "fdrl", "indb", "idfb", "airp", "pytm", "ippb", "cbin", "ucba", "mahb", "psib", "sibl", "karb", "kvbl",
    "ciub", "ibkl", "aubl", "dbss", "scbl", "hsbc", "citi", "bdbl", "ratn", "dlxb", "kscb", "jaka", "esfb",
    "ybl", "okaxis", "oksbi", "okhdfcbank", "okicici", "axl", "ibl", "apl", "upi",
}
IFSC = re.compile(r"^[A-Za-z]{4}0[A-Za-z0-9]{6}$")
UPI_REF = re.compile(r"(?<!\d)(\d{12})(?!\d)")
SPECIAL = [
    (re.compile(r"\b(atm|nfs|cash\s*wdl|cash\s*withdrawal|atw)\b", re.I), "ATM cash withdrawal"),
    (re.compile(r"\b(int\.?\s*pd|interest|int\.?\s*cr|int\s*coll|sb\s*int)\b", re.I), "Interest"),
    (re.compile(r"\b(charges?|chrgs?|chg|fee|fees|gst|amc|penalty|sms\s*alert)\b", re.I), "Bank charges"),
    (re.compile(r"\b(cash\s*dep|cash\s*deposit|by\s*cash|csh\s*dep)\b", re.I), "Cash deposit"),
]


def _nice(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" .,:;_#")
    # "SWIGGY" -> "Swiggy", "ACME TECH PVT LTD" -> "Acme Tech Pvt Ltd"; mixed case is left alone
    return text.title() if text.isupper() or text.islower() else text


def _useful_words(token: str) -> list[str]:
    keep = []
    for word in token.split():
        bare = word.strip(".,:;()[]#_").lower()
        letters = sum(ch.isalpha() for ch in bare)
        digits = sum(ch.isdigit() for ch in bare)
        if not bare or bare in NOISE_WORDS or bare in BANK_CODES or IFSC.match(bare):
            continue
        if digits >= 3 or (digits and digits >= letters) or "xx" in bare:  # numbers, masked cards
            continue
        if letters == 0:
            continue
        keep.append(word.strip(".,:;()[]#_"))
    return keep


def describe(narration: str) -> dict:
    """Turns a raw narration into {party, note, keywords, upi_ref}."""
    raw = re.sub(r"\s+", " ", narration or "").strip()
    upi_ref = None
    if re.search(r"\bupi\b", raw, re.I) and (m := UPI_REF.search(raw)):
        upi_ref = m.group(1)

    handles = []
    parts = []
    for token in re.split(r"[/\\|*:~]|\s-\s|-(?=\S)|(?<=\S)-", raw):
        token = token.strip()
        if "@" in token:  # a UPI id such as swiggy@ybl: keep the handle for category hints
            handle = re.sub(r"[^a-z]", " ", token.split("@")[0].lower()).strip()
            if handle and not handle.isdigit():
                handles.append(handle)
            continue
        if IFSC.match(token) or re.search(r"\bbank\b", token, re.I):  # "YES BANK", "State Bank of India"
            continue
        words = _useful_words(token)
        if words and sum(len(w) for w in words) >= 3:
            parts.append(" ".join(words))

    # drop repeats such as "SWIGGY ... Swiggy"
    seen, unique = set(), []
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    special = next((label for pattern, label in SPECIAL if pattern.search(raw)), None)
    if special:  # ATM withdrawals, interest, charges and cash deposits read better with a fixed label
        party = note = special
    elif unique:
        party = _nice(unique[0])
        rest = " ".join(unique[1:3])
        note = f"{party} ({_nice(rest)})" if rest else party
    elif handles:
        party = note = _nice(handles[0])
    else:
        party = note = raw[:60] or "Bank transaction"
    keywords = " ".join([note, *handles])
    return {"party": party[:80], "note": note[:200], "keywords": keywords, "upi_ref": upi_ref}


# ---------------------------------------------------------------- the common row model
@dataclass
class RawRow:
    date: date
    narration: str = ""
    debit: float | None = None
    credit: float | None = None
    amount: float | None = None
    marker: str | None = None  # "dr" / "cr" from a Dr/Cr column or suffix
    balance: float | None = None
    ref: str = ""


@dataclass
class BankRow:
    date: date
    type: str
    amount: float
    narration: str
    party: str
    note: str
    keywords: str
    balance: float | None = None
    upi_ref: str | None = None
    reference: str = ""
    balance_ok: bool | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


CREDIT_HINTS = re.compile(
    r"\b(cr|credit|credited|by|received|recd|salary|refund|reversal|rev|interest|int\.?\s*pd|deposit|"
    r"cashback|dividend|neft\s*cr|imps\s*cr|upi\s*cr|inward)\b", re.I)
DEBIT_HINTS = re.compile(r"\b(dr|debit|debited|to|paid|withdrawal|wdl|purchase|pos|atm|emi|charges?|bill)\b", re.I)
UPI_DIRECTION = re.compile(r"\bupi\s*[/\-]\s*(cr|dr)\b|\b(cr|dr)\s*[/\-]\s*upi\b", re.I)


def _guess_type(row: RawRow) -> str:
    if (m := UPI_DIRECTION.search(row.narration)):
        return "income" if (m.group(1) or m.group(2)).lower() == "cr" else "expense"
    text = row.narration
    if CREDIT_HINTS.search(text) and not DEBIT_HINTS.search(text.split("/")[0]):
        return "income"
    return "expense"


def resolve(raw_rows: list[RawRow], opening_balance: float | None = None) -> dict:
    """Decides type and amount for each row and checks the running balance."""
    rows = [r for r in raw_rows if (r.debit or r.credit or r.amount)]
    if not rows:
        raise StatementError("No transactions were found in this statement")
    if rows[0].date > rows[-1].date:  # newest first: walk the statement oldest first
        rows.reverse()

    any_negative = any(r.marker == "dr" for r in rows if r.amount and r.debit is None and r.credit is None)
    out: list[BankRow] = []
    prev_balance = opening_balance
    checked = mismatches = 0
    for r in rows:
        if r.debit and not r.credit:
            tx_type, amount = "expense", r.debit
        elif r.credit and not r.debit:
            tx_type, amount = "income", r.credit
        elif r.debit and r.credit:  # both filled (rare): keep the net movement
            amount = abs(r.credit - r.debit)
            tx_type = "income" if r.credit > r.debit else "expense"
        else:
            amount = r.amount
            if r.marker:
                tx_type = "expense" if r.marker == "dr" else "income"
            elif any_negative:  # a signed amount column: positives are credits
                tx_type = "income"
            else:
                tx_type = _guess_type(r)

        balance_ok = None
        if r.balance is not None and prev_balance is not None:
            delta = round(r.balance - prev_balance, 2)
            if abs(abs(delta) - amount) < 0.011:
                # The balance moved by exactly this amount: its direction settles debit vs credit.
                tx_type = "income" if delta > 0 else "expense"
                balance_ok = True
            else:
                balance_ok = False
                mismatches += 1
            checked += 1
        if r.balance is not None:
            prev_balance = r.balance

        info = describe(r.narration)
        out.append(BankRow(
            date=r.date, type=tx_type, amount=round(amount, 2), narration=r.narration.strip()[:300],
            party=info["party"], note=info["note"], keywords=info["keywords"], balance=r.balance,
            upi_ref=info["upi_ref"], balance_ok=balance_ok,
        ))

    _assign_references(out)
    first_balance = next((r for r in out if r.balance is not None), None)
    if opening_balance is None and first_balance is not None:
        signed = first_balance.amount if first_balance.type == "income" else -first_balance.amount
        if first_balance is out[0]:
            opening_balance = round(first_balance.balance - signed, 2)
    closing = next((r.balance for r in reversed(out) if r.balance is not None), None)
    return {
        "transactions": out,
        "opening_balance": opening_balance,
        "closing_balance": closing,
        "balance_checked": checked,
        "balance_mismatches": mismatches,
        "balance_ok": (mismatches == 0) if checked else None,
    }


def _assign_references(rows: list[BankRow]) -> None:
    """A stable id per row, so importing the same statement twice adds nothing.

    UPI payments use their 12 digit UPI reference (the same number Google Pay shows), so a payment
    imported from a Google Pay statement is also recognised here. Other rows use a fingerprint of
    date, amount, direction, balance and narration, plus a counter for identical rows.
    """
    counts: dict[str, int] = {}
    for r in rows:
        if r.upi_ref:
            r.reference = f"upi:{r.upi_ref}" + (":cr" if r.type == "income" else "")
            if counts.get(r.reference):  # same UPI ref twice in one direction: fall back to fingerprint
                r.reference = ""
            else:
                counts[r.reference] = 1
                continue
        text = re.sub(r"\s+", " ", r.narration.lower())
        bal = "" if r.balance is None else f"{r.balance:.2f}"
        base = f"{r.date}|{r.type}|{r.amount:.2f}|{bal}|{text}"
        n = counts.get(base, 0)
        counts[base] = n + 1
        r.reference = "bank:" + hashlib.sha1(f"{base}|{n}".encode()).hexdigest()[:24]


# ---------------------------------------------------------------- tables (CSV, Excel, HTML)
OPENING = re.compile(r"opening\s*balance|\bb/?f\b|brought\s*forward|balance\s*forward|\bobal\b", re.I)
END_OF_TABLE = re.compile(r"closing\s*balance|statement\s*summary|carried\s*forward|\bc/?f\b|"
                          r"^\s*total\b|grand\s*total|end\s*of\s*statement", re.I)


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_table(rows: list[list]) -> tuple[list[RawRow], float | None, int]:
    """Reads rows of cells. Returns (raw rows, opening balance, index of the header row)."""
    header_at, cols = None, None
    for i, row in enumerate(rows[:200]):
        if (found := columns_from_header(row)):
            header_at, cols = i, found
            break
    if cols is None:
        raise StatementError("Could not find the column headings (date, description, debit/credit, balance)")

    body = rows[header_at + 1:]
    dayfirst = detect_dayfirst(r[cols["date"]] for r in body if len(r) > cols["date"])

    def cell(row, role):
        i = cols.get(role)
        return row[i] if i is not None and i < len(row) else None

    raw: list[RawRow] = []
    opening = None
    current = None
    for row in body:
        if len(raw) > MAX_ROWS:
            raise StatementError(f"Statements with more than {MAX_ROWS} rows are not supported")
        if not any(_cell_text(c) for c in row):
            continue
        if columns_from_header(row):  # header repeated on every page
            current = None
            continue
        line = " ".join(_cell_text(c) for c in row)
        desc = _cell_text(cell(row, "desc"))
        when = parse_date(cell(row, "date"), dayfirst) or parse_date(cell(row, "value_date"), dayfirst)
        if OPENING.search(desc or line) and (bal := parse_balance(cell(row, "balance"))) is not None \
                and not (parse_amount(cell(row, "debit"))[0] or parse_amount(cell(row, "credit"))[0]):
            opening = bal if opening is None else opening
            continue
        if when is None:
            if END_OF_TABLE.search(line):
                if raw:
                    break
                continue
            has_money = any(parse_amount(cell(row, k))[0] for k in ("debit", "credit", "amount"))
            if current is not None and desc and not has_money and re.search(r"[A-Za-z]", desc):
                current.narration += " " + desc  # wrapped narration
            continue

        r = RawRow(date=when, narration=desc, ref=_cell_text(cell(row, "ref")))
        r.debit = parse_amount(cell(row, "debit"))[0] if "debit" in cols else None
        r.credit = parse_amount(cell(row, "credit"))[0] if "credit" in cols else None
        if "amount" in cols and not (r.debit or r.credit):
            r.amount, r.marker = parse_amount(cell(row, "amount"))
        if "dctype" in cols and (kind := _cell_text(cell(row, "dctype")).lower()):
            if kind.startswith(("d", "w")):
                r.marker = "dr"
            elif kind.startswith(("c", "dep")):
                r.marker = "cr"
            elif r.amount is None and (num := parse_amount(kind)[0]):
                r.amount = num
        r.balance = parse_balance(cell(row, "balance"))
        if not r.narration:
            # no description column (or it is empty): use the other text on the row
            skip = {cols.get(k) for k in ("date", "value_date", "debit", "credit", "amount", "balance", "dctype")}
            r.narration = " ".join(_cell_text(c) for i, c in enumerate(row) if i not in skip and _cell_text(c))
        if END_OF_TABLE.search(desc) and not (r.debit or r.credit or r.amount):
            break
        raw.append(r)
        current = r
    return raw, opening, header_at


def read_csv_text(text: str) -> list[list[str]]:
    sample = "\n".join(text.splitlines()[:60])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in ",;\t|"}
        delimiter = max(counts, key=counts.get)
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def read_xlsx(raw: bytes) -> list[list]:
    from openpyxl import load_workbook

    try:
        book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for broken files
        raise StatementError("The Excel file could not be opened") from exc
    rows = []
    for sheet in book.worksheets:  # statements are normally on the first sheet; read them all
        for row in sheet.iter_rows(values_only=True):
            rows.append(list(row))
            if len(rows) > MAX_ROWS * 3:
                break
    book.close()
    return rows


def read_xls(raw: bytes) -> list[list]:
    import xlrd

    try:
        book = xlrd.open_workbook(file_contents=raw)
    except xlrd.biffh.XLRDError as exc:
        if "encrypt" in str(exc).lower() or "password" in str(exc).lower():
            raise StatementError("This Excel file is password protected. Open it, save a copy without a "
                                 "password, and upload that.") from exc
        raise StatementError("The Excel file could not be opened") from exc
    except Exception as exc:
        raise StatementError("The Excel file could not be opened") from exc
    rows = []
    for sheet in book.sheets():
        for i in range(sheet.nrows):
            out = []
            for c in sheet.row(i):
                if c.ctype == xlrd.XL_CELL_DATE:
                    try:
                        out.append(xlrd.xldate.xldate_as_datetime(c.value, book.datemode))
                    except (ValueError, OverflowError):
                        out.append(None)
                elif c.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    out.append(None)
                else:
                    out.append(c.value)
            rows.append(out)
    return rows


class _TableHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.in_cell = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.in_cell, self.cell = True, []
        elif tag == "br" and self.in_cell:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.in_cell = False
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)


def read_html(text: str) -> list[list[str]]:
    parser = _TableHTML()
    parser.feed(text)
    return parser.rows


# ---------------------------------------------------------------- PDF and plain text (line based)
LINE_AMOUNT = re.compile(
    r"(?<![\d.,/])(-?\(?(?:\d{1,3}(?:,\d{2,3})+|\d+)\.\d{2}\)?)(?:\s?(Cr|Dr|CR|DR|cr|dr)\b\.?)?(?![\d.,/%])")
LEADING_DATE = re.compile(rf"^\s*(?:\d{{1,4}}\.?\s+)?(?:{ISO_DATE}|{NUMERIC_DATE}|{TEXT_DATE})")
PAGE_NOISE = re.compile(r"page\s*\d+\s*(of\s*\d+)?|^\s*\d+\s*$|computer\s*generated|does\s*not\s*require|"
                        r"signature|registered\s*office|customer\s*care|toll\s*free|www\.|http|"
                        r"this\s*is\s*a\s*system|statement\s*of\s*account|account\s*statement|"
                        r"please\s*(do|note|contact)|disclaimer|abbreviation", re.I)
MONEY_ROLES = ("debit", "credit", "amount", "balance")


def header_positions(line: str) -> dict[str, tuple[int, int]] | None:
    """Character spans of each column heading if this text line is a table header."""
    if LINE_AMOUNT.search(line):
        return None
    spans: dict[str, tuple[int, int]] = {}
    for m in re.finditer(r"\S+(?: \S+)*", line):  # cells are separated by two or more spaces
        cell = m.group()
        words = [(w.group(), m.start() + w.start(), m.start() + w.end()) for w in re.finditer(r"\S+", cell)]
        word_roles = {header_role(w) for w, _, _ in words} - {None, "amount", "ref"}
        if len(word_roles) >= 2:  # "Date Narration Debit Credit Balance" separated by single spaces
            for w, s, e in words:
                role = header_role(w)
                if role and role not in spans:
                    spans[role] = (s, e)
            continue
        role = header_role(cell)
        if role and role not in spans:
            spans[role] = (m.start(), m.end())
    if "date" not in spans and "value_date" in spans:
        spans["date"] = spans.pop("value_date")
    has_money = ("debit" in spans and "credit" in spans) or "amount" in spans
    if "date" in spans and has_money and len(spans) >= 3:
        return spans
    return None


def _nearest_role(start: int, end: int, spans: dict[str, tuple[int, int]]) -> str | None:
    best, best_dist = None, None
    for role in MONEY_ROLES:
        if role not in spans:
            continue
        s, e = spans[role]
        gap = 0 if start <= e and end >= s else min(abs(start - e), abs(s - end))
        center = abs((start + end) / 2 - (s + e) / 2)
        dist = (gap, center)
        if best_dist is None or dist < best_dist:
            best, best_dist = role, dist
    return best


def parse_lines(text: str) -> tuple[list[RawRow], float | None, str]:
    """Reads a statement laid out as text lines (a PDF, or a .txt statement).

    Returns (raw rows, opening balance, the text above the table for bank detection).
    """
    lines = text.splitlines()
    dayfirst = detect_dayfirst(lines)
    spans = None
    raw: list[RawRow] = []
    current: RawRow | None = None
    continuation = 0
    opening = None
    preamble_end = None

    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if (found := header_positions(line)):
            spans, current = found, None
            preamble_end = index if preamble_end is None else preamble_end
            continue
        dm = LEADING_DATE.match(line)
        amounts = []
        masked = line
        if dm:
            masked = " " * dm.end() + line[dm.end():]
        for d in ANY_DATE.finditer(masked):  # a value date column after the first date
            if d.start() < 40 or (spans and "value_date" in spans and abs(d.start() - spans["value_date"][0]) < 8):
                masked = masked[:d.start()] + " " * (d.end() - d.start()) + masked[d.end():]
        for m in LINE_AMOUNT.finditer(masked):
            amounts.append(m)

        if not dm:
            if OPENING.search(line) and amounts and opening is None and not raw:
                opening = parse_balance(amounts[-1].group(1) + " " + (amounts[-1].group(2) or ""))
                continue
            if END_OF_TABLE.search(line) or PAGE_NOISE.search(line):
                current = None if END_OF_TABLE.search(line) else current
                continue
            if current is None or continuation >= 3:
                continue
            if amounts and not (current.debit or current.credit or current.amount):
                _fill_amounts(current, amounts, spans)  # the amounts sat on a wrapped line
            text_part = LINE_AMOUNT.sub(" ", masked)
            if spans and "desc" in spans:
                stripped = len(text_part) - len(text_part.lstrip())
                money_start = min((spans[r][0] for r in MONEY_ROLES if r in spans), default=10**6)
                if stripped >= money_start:
                    continue
            words = re.sub(r"\s+", " ", text_part).strip()
            if words and re.search(r"[A-Za-z]", words) and not amounts:
                current.narration += " " + words
                continuation += 1
            continue

        when = parse_date(line[:dm.end()].strip().split(None, 1)[-1] if re.match(
            r"^\s*\d{1,4}\.?\s+\d", line) else line[:dm.end()], dayfirst)
        when = when or parse_date(line, dayfirst)
        if when is None:
            continue
        if OPENING.search(line) and len(amounts) == 1:
            if opening is None and not raw:
                opening = parse_balance(amounts[0].group(1) + " " + (amounts[0].group(2) or ""))
            continue
        r = RawRow(date=when)
        _fill_amounts(r, amounts, spans)
        desc = LINE_AMOUNT.sub(" ", masked)
        r.narration = re.sub(r"\s+", " ", desc).strip(" -")
        raw.append(r)
        current, continuation = r, 0
        if len(raw) > MAX_ROWS:
            raise StatementError(f"Statements with more than {MAX_ROWS} rows are not supported")

    preamble = "\n".join(lines[:preamble_end if preamble_end is not None else 30])
    return raw, opening, preamble


def _fill_amounts(r: RawRow, amounts: list[re.Match], spans) -> None:
    values = []
    for m in amounts:
        amount, marker = parse_amount(m.group(1) + (" " + m.group(2) if m.group(2) else ""))
        values.append((m, amount, marker))
    if spans and any(role in spans for role in MONEY_ROLES):
        for m, amount, marker in values:
            role = _nearest_role(m.start(1), m.end(1), spans)
            text = m.group(1) + (" " + m.group(2) if m.group(2) else "")
            if role == "balance":
                if r.balance is None:
                    r.balance = parse_balance(text)
            elif amount and role == "debit" and r.debit is None:
                r.debit = amount
            elif amount and role == "credit" and r.credit is None:
                r.credit = amount
            elif amount and r.amount is None:
                r.amount, r.marker = amount, marker
        return
    # No header: the last number is the balance when there are two or more.
    if len(values) >= 2:
        m, _, _ = values[-1]
        r.balance = parse_balance(m.group(1) + (" " + m.group(2) if m.group(2) else ""))
        _, r.amount, r.marker = values[-2]
    elif values:
        _, r.amount, r.marker = values[0]


def pdf_to_text(raw: bytes, password: str | None) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            opened = False
            for attempt in ([password] if password else []) + [""]:
                try:
                    if reader.decrypt(attempt):
                        opened = True
                        break
                except (FileNotDecryptedError, NotImplementedError, ValueError):
                    continue
            if not opened:
                raise PasswordRequired(wrong=bool(password))
        return "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)
    except StatementError:
        raise
    except (PdfReadError, FileNotDecryptedError, ValueError, KeyError, TypeError, OSError) as exc:
        raise StatementError("The uploaded file is not a readable PDF") from exc


# ---------------------------------------------------------------- bank name
BANK_NAMES = [
    ("State Bank of India", r"state\s*bank\s*of\s*india|\bsbi\b"), ("HDFC Bank", r"hdfc\s*bank"),
    ("ICICI Bank", r"icici\s*bank"), ("Axis Bank", r"axis\s*bank"), ("Kotak Mahindra Bank", r"kotak"),
    ("Punjab National Bank", r"punjab\s*national\s*bank|\bpnb\b"), ("Bank of Baroda", r"bank\s*of\s*baroda"),
    ("Canara Bank", r"canara\s*bank"), ("Union Bank of India", r"union\s*bank\s*of\s*india"),
    ("Indian Overseas Bank", r"indian\s*overseas\s*bank"), ("Central Bank of India", r"central\s*bank\s*of\s*india"),
    ("Bank of India", r"bank\s*of\s*india"), ("Indian Bank", r"\bindian\s*bank\b"),
    ("IDFC FIRST Bank", r"idfc\s*first"), ("Yes Bank", r"yes\s*bank"), ("IndusInd Bank", r"indusind"),
    ("Federal Bank", r"federal\s*bank"), ("UCO Bank", r"\buco\s*bank"), ("Bank of Maharashtra", r"bank\s*of\s*maharashtra"),
    ("Punjab & Sind Bank", r"punjab\s*(&|and)\s*sind"), ("South Indian Bank", r"south\s*indian\s*bank"),
    ("Karnataka Bank", r"karnataka\s*bank"), ("Karur Vysya Bank", r"karur\s*vysya"),
    ("City Union Bank", r"city\s*union\s*bank"), ("IDBI Bank", r"idbi"), ("AU Small Finance Bank", r"\bau\s*small"),
    ("Bandhan Bank", r"bandhan\s*bank"), ("RBL Bank", r"\brbl\s*bank"), ("Kerala Gramin Bank", r"kerala\s*gramin"),
    ("Dhanlaxmi Bank", r"dhanlaxmi"), ("CSB Bank", r"\bcsb\s*bank|catholic\s*syrian"),
    ("Tamilnad Mercantile Bank", r"tamilnad\s*mercantile"), ("Jammu & Kashmir Bank", r"j\s*&\s*k\s*bank|jammu"),
    ("Equitas Small Finance Bank", r"equitas"), ("Ujjivan Small Finance Bank", r"ujjivan"),
    ("Airtel Payments Bank", r"airtel\s*payments"), ("Paytm Payments Bank", r"paytm\s*payments"),
    ("India Post Payments Bank", r"india\s*post\s*payments"), ("DBS Bank", r"\bdbs\b"),
    ("Standard Chartered", r"standard\s*chartered"), ("HSBC", r"\bhsbc\b"), ("Citibank", r"citibank"),
]
IFSC_BANKS = {
    "SBIN": "State Bank of India", "HDFC": "HDFC Bank", "ICIC": "ICICI Bank", "UTIB": "Axis Bank",
    "KKBK": "Kotak Mahindra Bank", "PUNB": "Punjab National Bank", "BARB": "Bank of Baroda", "CNRB": "Canara Bank",
    "UBIN": "Union Bank of India", "IOBA": "Indian Overseas Bank", "CBIN": "Central Bank of India",
    "BKID": "Bank of India", "IDIB": "Indian Bank", "IDFB": "IDFC FIRST Bank", "YESB": "Yes Bank",
    "INDB": "IndusInd Bank", "FDRL": "Federal Bank", "UCBA": "UCO Bank", "MAHB": "Bank of Maharashtra",
    "PSIB": "Punjab & Sind Bank", "SIBL": "South Indian Bank", "KARB": "Karnataka Bank", "KVBL": "Karur Vysya Bank",
    "CIUB": "City Union Bank", "IBKL": "IDBI Bank", "AUBL": "AU Small Finance Bank", "BDBL": "Bandhan Bank",
    "RATN": "RBL Bank", "KLGB": "Kerala Gramin Bank", "DLXB": "Dhanlaxmi Bank", "CSBK": "CSB Bank",
    "TMBL": "Tamilnad Mercantile Bank", "JAKA": "Jammu & Kashmir Bank", "ESFB": "Equitas Small Finance Bank",
    "AIRP": "Airtel Payments Bank", "PYTM": "Paytm Payments Bank", "IPOS": "India Post Payments Bank",
    "DBSS": "DBS Bank", "SCBL": "Standard Chartered", "HSBC": "HSBC", "CITI": "Citibank",
}


def detect_bank(preamble: str) -> str | None:
    """The bank's name from the part of the statement above the transactions (not the narrations)."""
    for m in re.finditer(r"\b([A-Z]{4})0[A-Z0-9]{6}\b", preamble.upper()):
        if m.group(1) in IFSC_BANKS:
            return IFSC_BANKS[m.group(1)]
    for name, pattern in BANK_NAMES:
        if re.search(pattern, preamble, re.I):
            return name
    return None


# ---------------------------------------------------------------- entry point
def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = raw.decode(encoding)
            if "\x00" not in text:
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", errors="replace")


def detect_kind(raw: bytes) -> str:
    head = raw[:2048].lstrip()
    if head.startswith(b"%PDF"):
        return "pdf"
    if raw.startswith(b"PK\x03\x04"):
        return "xlsx"
    if raw.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    lowered = head.lower()
    if lowered.startswith((b"<", b"\xef\xbb\xbf<")) or b"<table" in lowered or b"<html" in lowered:
        return "html"
    if b"\x00" in raw[:1024] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise StatementError("This file type is not supported. Upload a PDF, Excel or CSV statement.")
    return "text"


def parse_bank_statement(raw: bytes, password: str | None = None) -> dict:
    """Reads a statement file and returns transactions plus a summary for the review screen."""
    kind = detect_kind(raw)
    preamble = ""
    if kind == "pdf":
        text = pdf_to_text(raw, password)
        if len(text.strip()) < 20:
            raise StatementError("This PDF has no readable text (it may be a scanned image). "
                                 "Download the statement from net banking as a PDF, Excel or CSV file.")
        raw_rows, opening, preamble = parse_lines(text)
        file_type = "PDF"
    else:
        if kind == "xlsx":
            table, file_type = read_xlsx(raw), "Excel"
        elif kind == "xls":
            table, file_type = read_xls(raw), "Excel"
        else:
            text = _decode(raw)
            if kind == "html":
                table, file_type = read_html(text), "Excel"
            else:
                table, file_type = read_csv_text(text), "CSV"
        try:
            raw_rows, opening, header_at = parse_table(table)
            preamble = "\n".join(" ".join(_cell_text(c) for c in row) for row in table[:header_at])
        except StatementError:
            if kind != "text":
                raise
            raw_rows, opening, preamble = parse_lines(text)  # a fixed width .txt statement
            file_type = "Text"

    result = resolve(raw_rows, opening)
    rows = result["transactions"]
    result.update({
        "file_type": file_type,
        "bank_name": detect_bank(preamble),
        "period": {"start": min(r.date for r in rows), "end": max(r.date for r in rows)},
        "parsed_totals": {
            "sent": round(sum(r.amount for r in rows if r.type == "expense"), 2),
            "received": round(sum(r.amount for r in rows if r.type == "income"), 2),
        },
    })
    return result
