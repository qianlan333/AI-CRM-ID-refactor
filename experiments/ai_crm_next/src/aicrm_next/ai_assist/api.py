from __future__ import annotations

from fastapi import APIRouter

from .application import GetAiAssistContractQuery

router = APIRouter()


@router.get("/api/admin/ai-assist/contract")
def ai_assist_contract() -> dict:
    return GetAiAssistContractQuery()()
