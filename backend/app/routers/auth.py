from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import create_access_token, get_current_user, hash_password, verify_password
from ..services import create_default_categories

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.Token, status_code=status.HTTP_201_CREATED)
def register(data: schemas.UserCreate, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An account with this email already exists")
    user = models.User(name=data.name, email=email, hashed_password=hash_password(data.password))
    db.add(user)
    db.flush()  # gives the user an id so we can attach categories
    create_default_categories(db, user)
    db.commit()
    db.refresh(user)
    return schemas.Token(access_token=create_access_token(user.id), user=user)


@router.post("/login", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Uses the standard OAuth2 form (field `username` holds the email) so the /docs 'Authorize' button works."""
    user = db.scalar(select(models.User).where(models.User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return schemas.Token(access_token=create_access_token(user.id), user=user)


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user
