from __future__ import annotations

from .dto import GrowthProgramList
from .repository import GrowthProgramRepository, build_growth_program_repository


def list_growth_programs(
    *,
    repo: GrowthProgramRepository | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    repository = repo or build_growth_program_repository()
    safe_limit = max(1, min(int(limit or 50), 100))
    safe_offset = max(0, int(offset or 0))
    items = repository.list_programs(limit=safe_limit, offset=safe_offset)
    return GrowthProgramList(items=items, limit=safe_limit, offset=safe_offset).model_dump()
