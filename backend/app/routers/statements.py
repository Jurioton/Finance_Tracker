"""Import transactions from a Google Pay statement PDF or a bank statement (any bank).

Two steps, like receipt scanning:
  1. POST /statements/{gpay|bank}/preview  - read the file and suggest a category per row (saves nothing)
  2. POST /statements/{gpay|bank}/import   - save the rows the user kept, skipping ones already imported

Every imported row stores a reference so the same row is never imported twice. A UPI payment has
the same 12 digit reference in Google Pay and on the bank statement, so importing both does not
count it twice either.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..ai import categorize_with_rules
from ..database import get_db
from ..bank_statement import PasswordRequired, parse_bank_statement
from ..bank_statement import StatementError as BankStatementError
from ..gpay_statement import StatementError, parse_statement_pdf
from ..security import get_current_user

router = APIRouter(prefix="/statements", tags=["statements"])
MAX_PDF_BYTES = 10 * 1024 * 1024


def existing_references(db: Session, user_id: int) -> set[str]:
    return set(db.scalars(select(models.Transaction.reference).where(
        models.Transaction.user_id == user_id, models.Transaction.reference.is_not(None))).all())


def same_payment_keys(reference: str, tx_type: str) -> set[str]:
    """Every reference under which this payment may already be stored.

    "gpay:<id>" (Google Pay import) and "upi:<id>" / "upi:<id>:cr" (bank import) are the same UPI
    payment seen from two places.
    """
    keys = {reference}
    kind, _, rest = reference.partition(":")
    upi = rest.removesuffix(":cr")
    if kind == "gpay":
        keys.add(f"upi:{upi}" + (":cr" if tx_type == "income" else ""))
    elif kind == "upi":
        keys.add(f"gpay:{upi}")
    return keys


async def read_upload(file: UploadFile) -> bytes:
    raw = await file.read(MAX_PDF_BYTES + 1)
    await file.close()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")
    if len(raw) > MAX_PDF_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file must be 10 MB or smaller")
    return raw


class CategorySuggester:
    """Suggests a category per row with the built-in rules (no AI call per row, so it stays fast)."""

    def __init__(self, db: Session, user: models.User):
        categories = db.scalars(select(models.Category).where(models.Category.user_id == user.id)).all()
        self.by_type = {t: [c for c in categories if c.type == t] for t in ("income", "expense")}
        recent = db.scalars(
            select(models.Transaction)
            .where(models.Transaction.user_id == user.id, models.Transaction.note != "")
            .order_by(models.Transaction.id.desc()).limit(300)
        ).all()
        self.history = {t: [{"note": r.note, "category": r.category.name} for r in recent if r.type == t]
                        for t in ("income", "expense")}
        self.cache: dict = {}

    def suggest(self, text: str, tx_type: str, key: str) -> int | None:
        cache_key = (tx_type, key.lower())
        if cache_key not in self.cache:
            cats = self.by_type[tx_type]
            name = categorize_with_rules(text, tx_type, [{"name": c.name} for c in cats], self.history[tx_type])
            match = next((c for c in cats if c.name == name), None) or next(
                (c for c in cats if c.name == "Other"), None)
            self.cache[cache_key] = match.id if match else None
        return self.cache[cache_key]


@router.post("/gpay/preview", response_model=schemas.StatementPreview)
async def preview_gpay_statement(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Reads a Google Pay statement and returns its transactions for review. Nothing is saved."""
    raw = await read_upload(file)
    if not raw.lstrip().startswith(b"%PDF"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload the statement as a PDF")

    try:
        parsed = parse_statement_pdf(raw)
    except StatementError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    suggester = CategorySuggester(db, user)
    seen = existing_references(db, user.id)

    rows, transfers = [], 0
    for tx in parsed["transactions"]:
        if tx.type == "transfer":
            transfers += 1  # money moved between your own accounts is neither income nor expense
            continue
        rows.append(schemas.StatementTransaction(
            date=tx.date, time=tx.time, type=tx.type, amount=tx.amount, party=tx.party, note=tx.note,
            upi_id=tx.upi_id, suggested_category_id=suggester.suggest(tx.note, tx.type, tx.party),
            duplicate=bool(tx.upi_id and same_payment_keys(f"gpay:{tx.upi_id}", tx.type) & seen),
        ))

    period = parsed["period"] or {}
    return schemas.StatementPreview(
        period_start=period.get("start"), period_end=period.get("end"),
        statement_totals=parsed["statement_totals"], parsed_totals=parsed["parsed_totals"],
        totals_match=parsed["totals_match"], skipped_transfers=transfers, transactions=rows,
    )


def save_rows(data: schemas.StatementImportRequest, db: Session, user: models.User) -> schemas.StatementImportResult:
    categories = {c.id: c for c in db.scalars(
        select(models.Category).where(models.Category.user_id == user.id)).all()}
    seen = existing_references(db, user.id)
    imported = skipped = 0
    for item in data.transactions:
        category = categories.get(item.category_id)
        if category is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
        if category.type != item.type:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Category '{category.name}' is for {category.type}, not {item.type}")
        reference = item.reference or (f"gpay:{item.upi_id}" if item.upi_id else None)
        if reference and same_payment_keys(reference, item.type) & seen:
            skipped += 1
            continue
        db.add(models.Transaction(
            amount=round(item.amount, 2), type=item.type, date=item.date, note=item.note,
            category_id=category.id, user_id=user.id, reference=reference,
        ))
        if reference:
            seen.add(reference)
        imported += 1
    db.commit()
    return schemas.StatementImportResult(imported=imported, skipped_duplicates=skipped)


@router.post("/gpay/import", response_model=schemas.StatementImportResult, status_code=status.HTTP_201_CREATED)
def import_gpay_statement(
    data: schemas.StatementImportRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Saves reviewed statement rows as transactions. Rows already imported (same UPI id) are skipped."""
    return save_rows(data, db, user)


@router.post("/bank/preview", response_model=schemas.StatementPreview)
async def preview_bank_statement(
    file: UploadFile = File(...),
    password: str | None = Form(default=None, max_length=100),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Reads a bank statement from any bank (PDF, Excel, CSV) for review. Nothing is saved.

    A locked PDF answers 423 (Locked) with `password_required` (or `password_wrong`) so the app can ask for it.
    The password is only used to open the file and is never stored.
    """
    raw = await read_upload(file)
    try:
        parsed = parse_bank_statement(raw, password or None)
    except PasswordRequired as exc:
        raise HTTPException(status.HTTP_423_LOCKED,
                            {"code": "password_wrong" if exc.wrong else "password_required", "message": str(exc)})
    except BankStatementError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    suggester = CategorySuggester(db, user)
    seen = existing_references(db, user.id)
    rows = [
        schemas.StatementTransaction(
            date=tx.date, type=tx.type, amount=tx.amount, party=tx.party, note=tx.note,
            narration=tx.narration, balance=tx.balance, reference=tx.reference,
            upi_id=tx.upi_ref, suggested_category_id=suggester.suggest(tx.keywords, tx.type, tx.party),
            duplicate=bool(same_payment_keys(tx.reference, tx.type) & seen),
        )
        for tx in parsed["transactions"]
    ]
    return schemas.StatementPreview(
        period_start=parsed["period"]["start"], period_end=parsed["period"]["end"],
        parsed_totals=parsed["parsed_totals"], totals_match=parsed["balance_ok"], transactions=rows,
        bank_name=parsed["bank_name"], file_type=parsed["file_type"],
        opening_balance=parsed["opening_balance"], closing_balance=parsed["closing_balance"],
        balance_mismatches=parsed["balance_mismatches"],
    )


@router.post("/bank/import", response_model=schemas.StatementImportResult, status_code=status.HTTP_201_CREATED)
def import_bank_statement(
    data: schemas.StatementImportRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Saves reviewed bank statement rows. Rows already imported, from either statement, are skipped."""
    return save_rows(data, db, user)
