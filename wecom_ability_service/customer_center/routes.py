from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def parse_customer_filters(args: Mapping[str, Any]) -> dict[str, str]:
    return {
        "owner_userid": str(args.get("owner_userid", "") or "").strip() or str(args.get("owner", "") or "").strip(),
        "tag": str(args.get("tag", "") or "").strip(),
        "status": str(args.get("status", "") or "").strip(),
        "is_bound": str(args.get("is_bound", "") or "").strip(),
        "mobile": str(args.get("mobile", "") or "").strip(),
        "keyword": str(args.get("keyword", "") or "").strip(),
        "limit": str(args.get("limit", "") or "").strip(),
        "offset": str(args.get("offset", "") or "").strip(),
    }
