from __future__ import annotations

from fastapi import APIRouter

from .application import GetSystemHealthQuery

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return GetSystemHealthQuery()()


@router.get("/api/system/health")
def system_health() -> dict:
    return GetSystemHealthQuery()()
