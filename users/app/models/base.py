from typing import Any, Dict

import humps
from sqlalchemy import inspect
from sqlalchemy.orm import as_declarative, declared_attr


@as_declarative()
class Base:
    __name__: str

    # The three ignores in this file and in core/security.py are all the same
    # thing: these models still use SQLAlchemy 1.x `Column()`, which tells a type
    # checker nothing. They go away with the Mapped[]/mapped_column() migration.
    @declared_attr  # type: ignore[arg-type]
    def __tablename__(cls) -> str:
        return humps.depascalize(cls.__name__)

    def dict(self) -> Dict[str, Any]:
        return {
            c.key: getattr(self, c.key)
            for c in inspect(self).mapper.column_attrs  # type: ignore[union-attr]
        }
