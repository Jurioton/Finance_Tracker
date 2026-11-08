import calendar
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import ai, models, schemas
from ..config import AI_MODEL
from ..database import get_db
from ..security import get_current_user
from ..services import budget_out, goal_out, month_bounds
from .dashboard import MONTH, shift_month, totals

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status", response_model=schemas.AIStatus)
def status(user: models.User = Depends(get_current_user)):
    return schemas.AIStatus(ai_enabled=ai.ai_enabled(), model=AI_MODEL if ai.ai_enabled() else None)


@router.post("/categorize", response_model=schemas.CategorizeResponse)
def categorize(data: schemas.CategorizeRequest, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    categories = db.scalars(select(models.Category).where(
        models.Category.user_id == user.id, models.Category.type == data.type)).all()
    recent = db.scalars(
        select(models.Transaction)
        .where(models.Transaction.user_id == user.id, models.Transaction.type == data.type,
               models.Transaction.note != "")
        .order_by(models.Transaction.id.desc()).limit(200)
    ).all()
    history = [{"note": t.note, "category": t.category.name} for t in recent]
    name, engine = ai.suggest_category(data.note, data.type, [{"name": c.name} for c in categories], history)
    match = next((c for c in categories if c.name == name), None)
    return schemas.CategorizeResponse(category=match, engine=engine)


def by_category(db: Session, user_id: int, month: str) -> dict[str, float]:
    start, end = month_bounds(month)
    rows = db.execute(
        select(models.Category.name, func.sum(models.Transaction.amount))
        .join(models.Category, models.Transaction.category_id == models.Category.id)
        .where(models.Transaction.user_id == user_id, models.Transaction.type == "expense",
               models.Transaction.date >= start, models.Transaction.date < end)
        .group_by(models.Category.name)
    ).all()
    return {name: round(float(total), 2) for name, total in rows}


def month_stats(db: Session, user_id: int, month: str) -> dict:
    income, expenses = totals(db, user_id, month)
    return {
        "month": month,
        "income": income,
        "expenses": expenses,
        "savings_rate": round((income - expenses) / income * 100, 1) if income else 0,
        "by_category": by_category(db, user_id, month),
    }


def build_stats(db: Session, user: models.User, month: str, today: date | None = None) -> dict:
    today = today or date.today()
    year, mon = map(int, month.split("-"))
    days_in_month = calendar.monthrange(year, mon)[1]
    if (year, mon) == (today.year, today.month):
        days_left = days_in_month - today.day
    elif (year, mon) > (today.year, today.month):
        days_left = days_in_month
    else:
        days_left = 0
    budgets = db.scalars(select(models.Budget).where(models.Budget.user_id == user.id, models.Budget.month == month))
    goals = db.scalars(select(models.Goal).where(models.Goal.user_id == user.id))
    return {
        "current": month_stats(db, user.id, month),
        "previous": month_stats(db, user.id, shift_month(month, -1)),
        "days_left": days_left,
        "budgets": [
            {"category": b.category.name, "limit": b.limit, "spent": b.spent, "status": b.status}
            for b in (budget_out(db, b) for b in budgets)
        ],
        "goals": [
            {"name": g.name, "target": g.target_amount, "saved": g.saved_amount, "deadline": str(g.deadline or ""),
             "monthly_needed": g.monthly_needed}
            for g in (goal_out(g) for g in goals) if not g.completed
        ],
    }


@router.get("/insights", response_model=schemas.InsightsResponse)
def insights(month: str | None = Query(default=None, pattern=MONTH), db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    month = month or date.today().strftime("%Y-%m")
    summary, items, engine = ai.monthly_insights(user.id, build_stats(db, user, month))
    return schemas.InsightsResponse(month=month, summary=summary, insights=[i.model_dump() for i in items],
                                    engine=engine)
