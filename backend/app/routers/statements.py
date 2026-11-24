"""Import transactions from a Google Pay statement PDF.

Two steps, like receipt scanning:
  1. POST /statements/gpay/preview  - parse the PDF and suggest a category for each row (saves nothing)
  2. POST /statements/gpay/import   - save the rows the user kept, skipping ones already imported
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..ai import categorize_with_rules
from ..database import get_db
from ..gpay_statement import StatementError, parse_statement_pdf
from ..security import get_current_user

router = APIRouter(prefix="/statements", tags=["statements"])
MAX_PDF_BYTES = 10 * 1024 * 1024


def existing_references(db: Session, user_id: int) -> set[str]:
    return set(db.scalars(select(models.Transaction.reference).where(
        models.Transaction.user_id == user_id, models.Transaction.reference.is_not(None))).all())


@router.post("/gpay/preview", response_model=schemas.StatementPreview)
async def preview_gpay_statement(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Reads a Google Pay statement and returns its transactions for review. Nothing is saved."""
    raw = await file.read(MAX_PDF_BYTES + 1)
    await file.close()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")
    if len(raw) > MAX_PDF_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "PDF must be 10 MB or smaller")
    if not raw.lstrip().startswith(b"%PDF"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload the statement as a PDF")

    try:
        parsed = parse_statement_pdf(raw)
    except StatementError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    categories = db.scalars(select(models.Category).where(models.Category.user_id == user.id)).all()
    by_type = {t: [c for c in categories if c.type == t] for t in ("income", "expense")}
    recent = db.scalars(
        select(models.Transaction)
        .where(models.Transaction.user_id == user.id, models.Transaction.note != "")
        .order_by(models.Transaction.id.desc()).limit(300)
    ).all()
    history = {t: [{"note": r.note, "category": r.category.name} for r in recent if r.type == t]
               for t in ("income", "expense")}
    seen = existing_references(db, user.id)

    rows, transfers, cache = [], 0, {}
    for tx in parsed["transactions"]:
        if tx.type == "transfer":
            transfers += 1  # money moved between your own accounts is neither income nor expense
            continue
        key = (tx.type, tx.party.lower())
        if key not in cache:
            # Built-in rules only (no AI call per row): fast for statements with hundreds of rows.
            cats = by_type[tx.type]
            name = categorize_with_rules(tx.note, tx.type, [{"name": c.name} for c in cats], history[tx.type])
            match = next((c for c in cats if c.name == name), None) or next(
                (c for c in cats if c.name == "Other"), None)
            cache[key] = match.id if match else None
        rows.append(schemas.StatementTransaction(
            date=tx.date, time=tx.time, type=tx.type, amount=tx.amount, party=tx.party, note=tx.note,
            upi_id=tx.upi_id, suggested_category_id=cache[key],
            duplicate=bool(tx.upi_id and f"gpay:{tx.upi_id}" in seen),
        ))

    period = parsed["period"] or {}
    return schemas.StatementPreview(
        period_start=period.get("start"), period_end=period.get("end"),
        statement_totals=parsed["statement_totals"], parsed_totals=parsed["parsed_totals"],
        totals_match=parsed["totals_match"], skipped_transfers=transfers, transactions=rows,
    )


@router.post("/gpay/import", response_model=schemas.StatementImportResult, status_code=status.HTTP_201_CREATED)
def import_gpay_statement(
    data: schemas.StatementImportRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Saves reviewed statement rows as transactions. Rows already imported (same UPI id) are skipped."""
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
        reference = f"gpay:{item.upi_id}" if item.upi_id else None
        if reference and reference in seen:
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
