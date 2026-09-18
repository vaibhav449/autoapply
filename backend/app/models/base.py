import enum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column


class Base(DeclarativeBase):
    pass


_EnumT = TypeVar("_EnumT", bound=enum.Enum)


def str_enum_column(
    enum_cls: type[_EnumT], name: str, default: _EnumT | None = None
) -> MappedColumn[_EnumT]:
    """A mapped_column for a str Enum that stores the lowercase .value in
    Postgres, not SQLAlchemy's default of the uppercase member NAME.

    Without values_callable, a column would store "INTERESTED" (the member's
    NAME) instead of "interested" (its .value) — every reader in this codebase,
    from API schemas to raw comparisons, expects the latter. This was hand-rolled
    identically on two models before being pulled out here.
    """
    return mapped_column(
        SAEnum(enum_cls, name=name, values_callable=lambda cls: [member.value for member in cls]),
        default=default,
    )
