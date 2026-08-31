from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.users import User


class Item(Base):
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(index=True)
    description: Mapped[Optional[str]] = mapped_column(index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))
    owner: Mapped[Optional["User"]] = relationship(back_populates="items")
