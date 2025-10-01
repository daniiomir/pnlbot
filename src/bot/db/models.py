from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    Column,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

Base = declarative_base()


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        UniqueConstraint("dedup_hash", name="uq_operations_dedup_hash"),
        {"schema": "finance"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    op_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    category_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("finance.categories.id"), nullable=False)
    amount_kop: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="RUB", server_default="RUB")
    free_text_reason: Mapped[str | None] = mapped_column(Text)
    receipt_url: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("finance.users.id"), nullable=False)
    is_general: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    dedup_hash: Mapped[str] = mapped_column(Text, nullable=False)


OperationChannel = Table(
    "operation_channels",
    Base.metadata,
    Column("operation_id", BigInteger, ForeignKey("finance.operations.id"), primary_key=True, nullable=False),
    Column("channel_id", BigInteger, ForeignKey("finance.channels.id"), primary_key=True, nullable=False),
    schema="finance",
)


__all__ = ["Base", "Channel", "Category", "User", "Operation", "OperationChannel"]
