from __future__ import annotations

from .calculator import (
    calculate_marketing_state,
    pool_stage_key,
    resolve_current_segment,
    resolve_pool_key_for_customer,
    resolve_pool_reference_at,
    should_enter_silent_pool,
)
from .evaluator import evaluate_marketing_eligibility
from . import state_defs

__all__ = [
    "calculate_marketing_state",
    "evaluate_marketing_eligibility",
    "pool_stage_key",
    "resolve_current_segment",
    "resolve_pool_key_for_customer",
    "resolve_pool_reference_at",
    "should_enter_silent_pool",
    "state_defs",
]
