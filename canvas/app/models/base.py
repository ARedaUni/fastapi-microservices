from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base, and the metadata Alembic autogenerates against.

    `users/` derives __tablename__ from the class name with pyhumps. One model
    does not justify the dependency; this service names its one table itself.
    """
