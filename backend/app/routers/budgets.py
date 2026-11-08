from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import budget_out
from .categories import get_owned_category

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=list[schemas.BudgetOut])
def list_budgets(month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
                 db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    month = month or date.today().strftime("%Y-%m")
    budgets = db.scalars(select(models.Budget).where(models.Budget.user_id == user.id, models.Budget.month == month))
    return [budget_out(db, b) for b in budgets]


@router.post("", response_model=schemas.BudgetOut, status_code=status.HTTP_201_CREATED)
def create_budget(data: schemas.BudgetCreate, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    category = get_owned_category(db, user, data.category_id)
    if category.type != "expense":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Budgets can only be set on expense categories")
    exists = db.scalar(select(models.Budget).where(
        models.Budget.user_id == user.id, models.Budget.category_id == data.category_id,
        models.Budget.month == data.month))
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A budget for this category and month already exists")
    budget = models.Budget(**data.model_dump(), user_id=user.id)
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget_out(db, budget)


def get_owned_budget(db, user, budget_id) -> models.Budget:
    budget = db.get(models.Budget, budget_id)
    if not budget or budget.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Budget not found")
    return budget


@router.put("/{budget_id}", response_model=schemas.BudgetOut)
def update_budget(budget_id: int, data: schemas.BudgetUpdate, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    budget = get_owned_budget(db, user, budget_id)
    budget.limit = data.limit
    db.commit()
    return budget_out(db, budget)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db.delete(get_owned_budget(db, user, budget_id))
    db.commit()
