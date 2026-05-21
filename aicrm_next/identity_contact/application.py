from __future__ import annotations

from aicrm_next.integration_gateway.customer_sync_adapters import build_identity_mapping_adapter
from aicrm_next.shared.typing import JsonDict

from .domain import normalize_identity_request
from .dto import IdentityResolution, ResolvePersonIdentityRequest
from .repo import FixtureIdentityRepository


class ResolvePersonIdentityQuery:
    def __init__(self, repo: FixtureIdentityRepository | None = None, identity_adapter=None) -> None:
        self._repo = repo or FixtureIdentityRepository()
        self._identity_adapter = identity_adapter or build_identity_mapping_adapter()

    def execute(self, query: ResolvePersonIdentityRequest) -> IdentityResolution | None:
        normalized = normalize_identity_request(query)
        self._identity_adapter.resolve_person_identity(
            external_userid=normalized.external_userid or "",
            openid=normalized.openid or "",
            unionid=normalized.unionid or "",
            mobile=normalized.mobile or "",
        )
        return self._repo.resolve(normalized)

    __call__ = execute


class UpsertIdentityMappingCommand:
    def __init__(self, identity_adapter=None) -> None:
        self._identity_adapter = identity_adapter or build_identity_mapping_adapter()

    def execute(
        self,
        *,
        external_userid: str = "",
        openid: str = "",
        unionid: str = "",
        mobile: str = "",
        person_id: str = "",
        corp_id: str = "",
        idempotency_key: str | None = None,
    ) -> JsonDict:
        return self._identity_adapter.upsert_identity_mapping(
            external_userid=external_userid,
            openid=openid,
            unionid=unionid,
            mobile=mobile,
            person_id=person_id,
            corp_id=corp_id,
            idempotency_key=idempotency_key,
        )

    __call__ = execute


class LinkOpenidUnionidExternalUseridCommand:
    def __init__(self, identity_adapter=None) -> None:
        self._identity_adapter = identity_adapter or build_identity_mapping_adapter()

    def execute(
        self,
        *,
        external_userid: str,
        openid: str = "",
        unionid: str = "",
        corp_id: str = "",
        idempotency_key: str | None = None,
    ) -> JsonDict:
        return self._identity_adapter.link_openid_unionid_external_userid(
            external_userid=external_userid,
            openid=openid,
            unionid=unionid,
            corp_id=corp_id,
            idempotency_key=idempotency_key,
        )

    __call__ = execute
