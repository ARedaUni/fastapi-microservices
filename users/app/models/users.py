from typing import TYPE_CHECKING, List, Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.items import Item


class User(Base):
    # Optional[] where the column is nullable, which is the schema as it stands
    # rather than a judgement about it: is_active and is_superuser have Python-side
    # defaults but no NOT NULL behind them.
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]
    is_active: Mapped[Optional[bool]] = mapped_column(default=True)
    is_superuser: Mapped[Optional[bool]] = mapped_column(default=False)
    items: Mapped[List["Item"]] = relationship(back_populates="owner", lazy="selectin")
