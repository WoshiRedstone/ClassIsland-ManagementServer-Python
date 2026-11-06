"""Pagination helpers mirroring ``PaginatedList<T>`` of the original server."""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence


class PaginationError(Exception):
    """Raised when ``pageIndex`` is out of range (original throws
    ``ArgumentOutOfRangeException``)."""


def _validate(page_index: int) -> None:
    if page_index <= 0:
        raise PaginationError("Page index should larger than 0")


def paginated_list(items: Sequence[Any], count: int, page_index: int, page_size: int) -> dict[str, Any]:
    total_pages = int(math.ceil(count / float(page_size))) if page_size else 0
    return {
        "pageIndex": page_index,
        "totalPages": total_pages,
        "pageSize": page_size,
        "itemCount": count,
        "items": list(items),
        "hasPreviousPage": page_index > 1,
        "hasNextPage": page_index < total_pages,
    }


def paginate_query(rows: Iterable[Any], page_index: int, page_size: int, serialize) -> dict[str, Any]:
    """``PaginatedList<T>.CreateFromRawList`` equivalent for already sorted rows."""
    _validate(page_index)
    rows = list(rows)
    count = len(rows)
    start = (page_index - 1) * page_size
    chunk = rows[start:start + page_size]
    return paginated_list([serialize(item) for item in chunk], count, page_index, page_size)
