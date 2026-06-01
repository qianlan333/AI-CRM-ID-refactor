#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.customer_read_model.backfill import (  # noqa: E402
    CustomerReadModelBackfillService,
    FixtureCustomerReadModelSource,
    LegacyShadowCustomerReadModelSource,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill the Next-native customer read model.")
    parser.add_argument("--execute", action="store_true", help="Write to the configured read model repository. Defaults to dry-run.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--external-userid", action="append", default=[])
    parser.add_argument("--source", choices=["legacy-shadow", "fixture"], default="legacy-shadow")
    args = parser.parse_args()

    source = FixtureCustomerReadModelSource() if args.source == "fixture" else LegacyShadowCustomerReadModelSource()
    result = CustomerReadModelBackfillService(source=source).run(
        dry_run=not bool(args.execute),
        limit=args.limit,
        external_userids=args.external_userid,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
