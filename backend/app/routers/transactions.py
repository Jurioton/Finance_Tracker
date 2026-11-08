import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import month_bounds
from .categories import get_owned_category

router = APIRouter(prefix="/transactions", tags=["transactions"])


def filtered_query(user: models.User, type, category_id, month, start, end, search):
    query = select(models.Transaction).where(models.Transaction.user_id == user.id)
    if type:
        query = query.where(models.Transaction.type == type)
    if category_id:
        query = query.where(models.Transaction.category_id == category_id)
    if month:
        m_start, m_end = month_bounds(month)
        query = query.where(models.Transaction.date >= m_start, models.Transaction.date < m_end)
    if start:
        query = query.where(models.Transaction.date >= start)
    if end:
        query = query.where(models.Transaction.date <= end)
    if search:
        query = query.where(models.Transaction.note.ilike(f"%{search}%"))
    return query.order_by(models.Transaction.date.desc(), models.Transaction.id.desc())


def check_category(db, user, category_id, tx_type):
    category = get_owned_category(db, user, category_id)
    if category.type != tx_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Category '{category.name}' is for {category.type}, not {tx_type}")


# Reusable filter parameters for list and export
def filters(
    type: schemas.TxType | None = None,
    category_id: int | None = None,
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    start: date | None = None,
    end: date | None = None,
    search: str | None = None,
):
    return dict(type=type, category_id=category_id, month=month, start=start, end=end, search=search)


@router.get("", response_model=list[schemas.TransactionOut])
def list_transactions(f: dict = Depends(filters), db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    return db.scalars(filtered_query(user, **f)).all()


@router.get("/export")
def export_csv(f: dict = Depends(filters), db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "type", "category", "amount", "note"])
    for tx in db.scalars(filtered_query(user, **f)):
        writer.writerow([tx.date.isoformat(), tx.type, tx.category.name, f"{tx.amount:.2f}", tx.note])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="transactions.csv"'},
    )


@router.post("", response_model=schemas.TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(data: schemas.TransactionCreate, db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)):
    check_category(db, user, data.category_id, data.type)
    tx = models.Transaction(**data.model_dump(), user_id=user.id)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def get_owned_tx(db, user, tx_id) -> models.Transaction:
    tx = db.get(models.Transaction, tx_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return tx


@router.get("/{tx_id}", response_model=schemas.TransactionOut)
def get_transaction(tx_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return get_owned_tx(db, user, tx_id)


@router.put("/{tx_id}", response_model=schemas.TransactionOut)
def update_transaction(tx_id: int, data: schemas.TransactionUpdate, db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)):
    tx = get_owned_tx(db, user, tx_id)
    changes = data.model_dump(exclude_unset=True)
    check_category(db, user, changes.get("category_id", tx.category_id), changes.get("type", tx.type))
    for key, value in changes.items():
        setattr(tx, key, value)
    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(tx_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db.delete(get_owned_tx(db, user, tx_id))
    db.commit()
