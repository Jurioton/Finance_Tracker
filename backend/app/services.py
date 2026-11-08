"""Business logic shared by several routers (budget status, goal progress)."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas

WARNING_THRESHOLD = 80  # percent of a budget at which we warn the user

DEFAULT_CATEGORIES = {
    "expense": ["Food", "Rent", "Transport", "Shopping", "Bills", "Entertainment", "Health", "Other"],
    "income": ["Salary", "Freelance", "Gifts", "Other"],
}


def create_default_categories(db: Session, user: models.User) -> None:
    for tx_type, names in DEFAULT_CATEGORIES.items():
        for name in names:
            db.add(models.Category(name=name, type=tx_type, user_id=user.id))


def month_bounds(month: str) -> tuple[date, date]:
    """'2026-11' -> (2026-11-01, 2026-12-01). The end date is exclusive."""
    year, mon = map(int, month.split("-"))
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start, end


def spent_in_category(db: Session, user_id: int, category_id: int, month: str) -> float:
    start, end = month_bounds(month)
    total = db.scalar(
        select(func.coalesce(func.sum(models.Transaction.amount), 0)).where(
            models.Transaction.user_id == user_id,
            models.Transaction.category_id == category_id,
            models.Transaction.type == "expense",
            models.Transaction.date >= start,
            models.Transaction.date < end,
        )
    )
    return float(total or 0)


def budget_out(db: Session, budget: models.Budget) -> schemas.BudgetOut:
    spent = spent_in_category(db, budget.user_id, budget.category_id, budget.month)
    percent = round(spent / budget.limit * 100, 1) if budget.limit else 0
    status = "over" if percent >= 100 else "warning" if percent >= WARNING_THRESHOLD else "ok"
    return schemas.BudgetOut(
        id=budget.id,
        category=schemas.CategoryOut.model_validate(budget.category),
        limit=budget.limit,
        month=budget.month,
        spent=round(spent, 2),
        percent=percent,
        status=status,
    )


def goal_out(goal: models.Goal, today: date | None = None) -> schemas.GoalOut:
    today = today or date.today()
    remaining = max(goal.target_amount - goal.saved_amount, 0)
    percent = round(min(goal.saved_amount / goal.target_amount * 100, 100), 1)
    monthly_needed = None
    if goal.deadline and remaining > 0:
        months_left = (goal.deadline.year - today.year) * 12 + (goal.deadline.month - today.month)
        monthly_needed = round(remaining / max(months_left, 1), 2)
    return schemas.GoalOut(
        id=goal.id,
        name=goal.name,
        target_amount=goal.target_amount,
        saved_amount=goal.saved_amount,
        deadline=goal.deadline,
        percent=percent,
        remaining=round(remaining, 2),
        monthly_needed=monthly_needed,
        completed=remaining == 0,
    )
