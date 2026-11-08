from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    categories: Mapped[list["Category"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    goals: Mapped[list["Goal"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name", "type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(10))  # "income" or "expense"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user: Mapped[User] = relationship(back_populates="categories")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(10))  # "income" or "expense"
    date: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    user: Mapped[User] = relationship(back_populates="transactions")
    category: Mapped[Category] = relationship()


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    limit: Mapped[float] = mapped_column(Float)
    month: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    user: Mapped[User] = relationship(back_populates="budgets")
    category: Mapped[Category] = relationship()


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    target_amount: Mapped[float] = mapped_column(Float)
    saved_amount: Mapped[float] = mapped_column(Float, default=0)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    user: Mapped[User] = relationship(back_populates="goals")
