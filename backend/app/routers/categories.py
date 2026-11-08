from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user

router = APIRouter(prefix="/categories", tags=["categories"])


def get_owned_category(db: Session, user: models.User, category_id: int) -> models.Category:
    category = db.get(models.Category, category_id)
    if not category or category.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


@router.get("", response_model=list[schemas.CategoryOut])
def list_categories(type: schemas.TxType | None = None, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    query = select(models.Category).where(models.Category.user_id == user.id)
    if type:
        query = query.where(models.Category.type == type)
    return db.scalars(query.order_by(models.Category.type, models.Category.name)).all()


@router.post("", response_model=schemas.CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: schemas.CategoryCreate, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    exists = db.scalar(select(models.Category).where(
        models.Category.user_id == user.id, models.Category.name == data.name, models.Category.type == data.type))
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This category already exists")
    category = models.Category(**data.model_dump(), user_id=user.id)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    category = get_owned_category(db, user, category_id)
    in_use = db.scalar(select(models.Transaction.id).where(models.Transaction.category_id == category.id).limit(1))
    if in_use:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Category has transactions; move or delete them first")
    for budget in db.scalars(select(models.Budget).where(models.Budget.category_id == category.id)):
        db.delete(budget)
    db.delete(category)
    db.commit()
