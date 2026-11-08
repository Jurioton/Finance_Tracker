"""Pydantic schemas: they validate request bodies and shape API responses."""
import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

TxType = Literal["income", "expense"]
MonthStr = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-11"])


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)


class UserOut(ORM):
    id: int
    name: str
    email: EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Categories ----------
class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    type: TxType


class CategoryOut(ORM):
    id: int
    name: str
    type: TxType


# ---------- Transactions ----------
class TransactionBase(BaseModel):
    amount: float = Field(gt=0)
    type: TxType
    date: dt.date
    note: str = Field(default="", max_length=255)
    category_id: int


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    type: TxType | None = None
    date: dt.date | None = None
    note: str | None = Field(default=None, max_length=255)
    category_id: int | None = None


class TransactionOut(ORM, TransactionBase):
    id: int
    category: CategoryOut


# ---------- Budgets ----------
class BudgetCreate(BaseModel):
    category_id: int
    limit: float = Field(gt=0)
    month: str = MonthStr


class BudgetUpdate(BaseModel):
    limit: float = Field(gt=0)


class BudgetOut(ORM):
    id: int
    category: CategoryOut
    limit: float
    month: str
    spent: float = 0
    percent: float = 0
    status: Literal["ok", "warning", "over"] = "ok"


# ---------- Goals ----------
class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_amount: float = Field(gt=0)
    saved_amount: float = Field(default=0, ge=0)
    deadline: dt.date | None = None


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    target_amount: float | None = Field(default=None, gt=0)
    saved_amount: float | None = Field(default=None, ge=0)
    deadline: dt.date | None = None


class GoalContribution(BaseModel):
    amount: float = Field(gt=0)


class GoalOut(ORM):
    id: int
    name: str
    target_amount: float
    saved_amount: float
    deadline: dt.date | None
    percent: float = 0
    remaining: float = 0
    monthly_needed: float | None = None
    completed: bool = False


# ---------- Dashboard ----------
class CategoryTotal(BaseModel):
    category: str
    total: float


class Summary(BaseModel):
    month: str
    income: float
    expenses: float
    balance: float
    savings_rate: float
    by_category: list[CategoryTotal]
    budget_alerts: list[BudgetOut]


class TrendPoint(BaseModel):
    month: str
    income: float
    expenses: float


# ---------- AI ----------
Engine = Literal["ai", "rules"]


class AIStatus(BaseModel):
    ai_enabled: bool
    model: str | None


class CategorizeRequest(BaseModel):
    note: str = Field(min_length=1, max_length=255)
    type: TxType


class CategorizeResponse(BaseModel):
    category: CategoryOut | None
    engine: Engine


class InsightOut(BaseModel):
    kind: Literal["positive", "warning", "info", "tip"]
    title: str
    text: str


class InsightsResponse(BaseModel):
    month: str
    summary: str
    insights: list[InsightOut]
    engine: Engine
