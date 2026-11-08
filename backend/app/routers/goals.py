from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import goal_out

router = APIRouter(prefix="/goals", tags=["goals"])


def get_owned_goal(db, user, goal_id) -> models.Goal:
    goal = db.get(models.Goal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Goal not found")
    return goal


@router.get("", response_model=list[schemas.GoalOut])
def list_goals(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    goals = db.scalars(select(models.Goal).where(models.Goal.user_id == user.id).order_by(models.Goal.deadline))
    return [goal_out(g) for g in goals]


@router.post("", response_model=schemas.GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(data: schemas.GoalCreate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    goal = models.Goal(**data.model_dump(), user_id=user.id)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal_out(goal)


@router.put("/{goal_id}", response_model=schemas.GoalOut)
def update_goal(goal_id: int, data: schemas.GoalUpdate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    goal = get_owned_goal(db, user, goal_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(goal, key, value)
    db.commit()
    return goal_out(goal)


@router.post("/{goal_id}/contribute", response_model=schemas.GoalOut)
def contribute(goal_id: int, data: schemas.GoalContribution, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    goal = get_owned_goal(db, user, goal_id)
    goal.saved_amount += data.amount
    db.commit()
    return goal_out(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db.delete(get_owned_goal(db, user, goal_id))
    db.commit()
