from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import budget_out, month_bounds

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


def shift_month(month: str, delta: int) -> str:
    year, mon = map(int, month.split("-"))
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def totals(db: Session, user_id: int, month: str) -> tuple[float, float]:
    start, end = month_bounds(month)
    rows = db.execute(
        select(models.Transaction.type, func.sum(models.Transaction.amount))
        .where(models.Transaction.user_id == user_id, models.Transaction.date >= start, models.Transaction.date < end)
        .group_by(models.Transaction.type)
    ).all()
    data = {t: float(total) for t, total in rows}
    return round(data.get("income", 0), 2), round(data.get("expense", 0), 2)


@router.get("/summary", response_model=schemas.Summary)
def summary(month: str | None = Query(default=None, pattern=MONTH), db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    month = month or date.today().strftime("%Y-%m")
    income, expenses = totals(db, user.id, month)
    start, end = month_bounds(month)
    by_category = db.execute(
        select(models.Category.name, func.sum(models.Transaction.amount).label("total"))
        .join(models.Category, models.Transaction.category_id == models.Category.id)
        .where(models.Transaction.user_id == user.id, models.Transaction.type == "expense",
               models.Transaction.date >= start, models.Transaction.date < end)
        .group_by(models.Category.name)
        .order_by(func.sum(models.Transaction.amount).desc())
    ).all()
    budgets = db.scalars(select(models.Budget).where(models.Budget.user_id == user.id, models.Budget.month == month))
    alerts = [b for b in (budget_out(db, b) for b in budgets) if b.status != "ok"]
    return schemas.Summary(
        month=month,
        income=income,
        expenses=expenses,
        balance=round(income - expenses, 2),
        savings_rate=round((income - expenses) / income * 100, 1) if income else 0,
        by_category=[schemas.CategoryTotal(category=name, total=round(total, 2)) for name, total in by_category],
        budget_alerts=alerts,
    )


@router.get("/trends", response_model=list[schemas.TrendPoint])
def trends(months: int = Query(default=6, ge=1, le=24), end_month: str | None = Query(default=None, pattern=MONTH),
           db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    end_month = end_month or date.today().strftime("%Y-%m")
    points = []
    for offset in range(months - 1, -1, -1):
        m = shift_month(end_month, -offset)
        income, expenses = totals(db, user.id, m)
        points.append(schemas.TrendPoint(month=m, income=income, expenses=expenses))
    return points
