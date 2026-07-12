"""Unified AI-CRM OAuth 2.0/OIDC authorization platform."""

from .context import AuthContext, PrincipalType
from .service import AuthPlatformService

__all__ = ["AuthContext", "AuthPlatformService", "PrincipalType"]
