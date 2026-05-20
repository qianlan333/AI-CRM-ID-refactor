from __future__ import annotations

from .domain import normalize_identity_request
from .dto import IdentityResolution, ResolvePersonIdentityRequest
from .repo import FixtureIdentityRepository


class ResolvePersonIdentityQuery:
    def __init__(self, repo: FixtureIdentityRepository | None = None) -> None:
        self._repo = repo or FixtureIdentityRepository()

    def execute(self, query: ResolvePersonIdentityRequest) -> IdentityResolution | None:
        normalized = normalize_identity_request(query)
        return self._repo.resolve(normalized)

    __call__ = execute
