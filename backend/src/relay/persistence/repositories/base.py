from typing import Any, Protocol

from sqlalchemy import Select

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(limit, MAX_PAGE_SIZE))


def paginate_desc[*Ts](
    stmt: Select[*Ts], id_column: Any, *, before: str | None, limit: int
) -> Select[*Ts]:
    """Keyset pagination over time-sortable ids, newest first. Fetches one extra row
    so callers can tell whether another page exists."""
    if before is not None:
        stmt = stmt.where(id_column < before)
    return stmt.order_by(id_column.desc()).limit(limit + 1)


class Identified(Protocol):
    @property
    def id(self) -> str: ...


def split_page[T: Identified](rows: list[T], limit: int) -> tuple[list[T], str | None]:
    if len(rows) <= limit:
        return rows, None
    page = rows[:limit]
    return page, page[-1].id
