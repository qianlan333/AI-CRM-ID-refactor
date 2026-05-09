"""Customer value/segment data-access (阶段 5.1).

Extracted from repo.py.
"""

from __future__ import annotations

from typing import Any

from ._repo_helpers import _fetchone_dict, _normalized_text


def get_customer_value_segment_current(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_value_segment_current
        WHERE external_userid = ?
        LIMIT 1
        """,
        (_normalized_text(external_userid),),
    )




__all__ = ['get_customer_value_segment_current']
