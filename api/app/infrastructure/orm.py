from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class UserRecord(Base):
    """ORM mapping (code-first). The schema is created by migrations/."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
