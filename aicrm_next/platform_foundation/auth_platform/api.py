from __future__ import annotations

from urllib.parse import parse_qs
import ipaddress

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from oauthlib.oauth2.rfc6749.errors import OAuth2Error

from aicrm_next.shared.runtime_settings import runtime_setting

from .context import AuthContext
from .client_authentication import (
    ClientAuthenticationError,
    mtls_sender_constraint,
    verify_dpop_proof,
    verify_private_key_jwt,
)
from .credentials import CredentialHasher
from .models import OAuthSubject
from .oauthlib_provider import OAuthLibProvider, OAuthLibRequestValidator
from .oidc_signing import OIDCSigner
from .repository import PostgresAuthPlatformRepository
from .sessions import AuthSessionService


router = APIRouter()


@router.get("/.well-known/openid-configuration")
def openid_configuration(request: Request):
    return JSONResponse(_metadata(_issuer(request)))


@router.get("/.well-known/oauth-authorization-server")
def oauth_authorization_server_metadata(request: Request):
    return JSONResponse(_metadata(_issuer(request)))


@router.get("/oauth/jwks")
def oauth_jwks(request: Request):
    return JSONResponse(_provider(request).validator.signer.jwks())


@router.api_route("/oauth/authorize", methods=["GET", "POST"])
async def oauth_authorize(request: Request):
    provider = _provider(request)
    subject = _request_subject(request)
    if subject is None:
        return _oauth_error("login_required", status_code=401)
    uri = str(request.url)
    body = (await request.body()).decode("utf-8") if request.method == "POST" else None
    query = parse_qs(body or request.url.query)
    scopes = str((query.get("scope") or [""])[0]).split()
    headers, response_body, status = provider.server.create_authorization_response(
        uri,
        http_method=request.method,
        body=body,
        headers=dict(request.headers),
        scopes=scopes,
        credentials={
            "user": subject,
            "audience": str((query.get("audience") or ["aicrm-admin"])[0]),
        },
    )
    return _oauth_response(headers, response_body, status)


@router.post("/oauth/token")
async def oauth_token(request: Request):
    body = (await request.body()).decode("utf-8")
    parameters = parse_qs(body)
    try:
        authenticated_client_id, sender_constraint = _authenticate_machine_client(request, parameters)
    except ClientAuthenticationError as exc:
        return _oauth_error("invalid_client", status_code=401, description=exc.error)
    credentials = {
        "audience": str((parameters.get("audience") or [""])[0]),
        "sender_constraint": sender_constraint,
        "authenticated_client_id": authenticated_client_id,
    }
    headers, response_body, status = _provider(request).server.create_token_response(
        str(request.url),
        http_method="POST",
        body=body,
        headers=dict(request.headers),
        credentials=credentials,
    )
    return _oauth_response(headers, response_body, status)


@router.post("/oauth/introspect")
async def oauth_introspect(request: Request):
    headers, response_body, status = _provider(request).server.create_introspect_response(
        str(request.url),
        http_method="POST",
        body=(await request.body()).decode("utf-8"),
        headers=dict(request.headers),
    )
    return _oauth_response(headers, response_body, status)


@router.post("/oauth/revoke")
async def oauth_revoke(request: Request):
    headers, response_body, status = _provider(request).server.create_revocation_response(
        str(request.url),
        http_method="POST",
        body=(await request.body()).decode("utf-8"),
        headers=dict(request.headers),
    )
    return _oauth_response(headers, response_body, status)


@router.get("/oauth/userinfo")
def oauth_userinfo(request: Request):
    try:
        headers, response_body, status = _provider(request).server.create_userinfo_response(
            str(request.url),
            http_method="GET",
            headers=dict(request.headers),
        )
    except OAuth2Error as exc:
        headers, response_body, status = exc.headers, exc.json, exc.status_code
    return _oauth_response(headers, response_body, status)


def build_runtime_oauth_provider() -> OAuthLibProvider:
    issuer = str(runtime_setting("AICRM_AUTH_ISSUER") or "").rstrip("/")
    pepper = str(runtime_setting("AICRM_AUTH_TOKEN_HASH_PEPPER") or "")
    private_key = str(runtime_setting("AICRM_AUTH_OIDC_SIGNING_PRIVATE_KEY") or "")
    key_id = str(runtime_setting("AICRM_AUTH_OIDC_SIGNING_KEY_ID") or "")
    if not issuer or not pepper or not private_key or not key_id:
        raise RuntimeError("RAUTH runtime configuration is incomplete")
    hasher = CredentialHasher(pepper)
    signer = OIDCSigner(issuer=issuer, private_key_pem=private_key, key_id=key_id)
    repository = PostgresAuthPlatformRepository()
    return OAuthLibProvider(OAuthLibRequestValidator(repository, hasher, signer))


def _provider(request: Request) -> OAuthLibProvider:
    configured = getattr(request.app.state, "auth_platform_provider", None)
    if isinstance(configured, OAuthLibProvider):
        return configured
    provider = build_runtime_oauth_provider()
    request.app.state.auth_platform_provider = provider
    return provider


def auth_session_service(request: Request) -> AuthSessionService:
    configured = getattr(request.app.state, "auth_session_service", None)
    if isinstance(configured, AuthSessionService):
        return configured
    pepper = str(runtime_setting("AICRM_AUTH_TOKEN_HASH_PEPPER") or "")
    if not pepper:
        raise RuntimeError("RAUTH session hashing pepper is not configured")
    service = AuthSessionService(PostgresAuthPlatformRepository(), CredentialHasher(pepper))
    request.app.state.auth_session_service = service
    return service


def _issuer(request: Request) -> str:
    configured = getattr(request.app.state, "auth_platform_provider", None)
    if isinstance(configured, OAuthLibProvider):
        return configured.validator.signer.issuer
    issuer = str(runtime_setting("AICRM_AUTH_ISSUER") or "").rstrip("/")
    if not issuer:
        raise RuntimeError("RAUTH issuer is not configured")
    return issuer


def _request_subject(request: Request) -> OAuthSubject | None:
    explicit = getattr(request.state, "oauth_subject", None)
    if isinstance(explicit, OAuthSubject):
        return explicit
    context = getattr(request.state, "auth_context", None)
    if not isinstance(context, AuthContext):
        return None
    return OAuthSubject(
        principal_id=context.sub,
        principal_type=context.principal_type,
        subject=context.sub,
        tenant_id=context.tenant_id,
        actor=context.actor,
        acr=context.acr,
        auth_time=context.auth_time,
    )


def _metadata(issuer: str) -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "introspection_endpoint": f"{issuer}/introspect",
        "revocation_endpoint": f"{issuer}/revoke",
        "userinfo_endpoint": f"{issuer}/userinfo",
        "jwks_uri": f"{issuer}/jwks",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "client_credentials", "refresh_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["private_key_jwt", "client_secret_basic", "none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["openid"],
    }


def _oauth_response(headers: dict, body: str | None, status: int) -> Response:
    response_headers = {str(key): str(value) for key, value in dict(headers or {}).items()}
    response_headers.setdefault("Cache-Control", "no-store")
    response_headers.setdefault("Pragma", "no-cache")
    return Response(content=body or "", status_code=int(status), headers=response_headers)


def _oauth_error(error: str, *, status_code: int, description: str = "") -> JSONResponse:
    payload = {"error": error}
    if description:
        payload["error_description"] = description
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _authenticate_machine_client(request: Request, parameters: dict[str, list[str]]) -> tuple[str, str]:
    provider = _provider(request)
    repository = provider.validator.repository
    assertion = str((parameters.get("client_assertion") or [""])[0])
    assertion_type = str((parameters.get("client_assertion_type") or [""])[0])
    client_id = str((parameters.get("client_id") or [""])[0])
    if assertion:
        result = verify_private_key_jwt(
            assertion=assertion,
            assertion_type=assertion_type,
            token_endpoint=f"{provider.validator.signer.issuer}/token",
            repository=repository,
        )
        client_id = result.client_id
    client = repository.oauth_client(client_id) if client_id else None
    if client is None:
        return "", ""
    if client.token_endpoint_auth_method == "tls_client_auth":
        sender_constraint = _trusted_mtls_sender_constraint(request)
        return client.client_id, sender_constraint
    if client.token_endpoint_auth_method != "private_key_jwt" or not assertion:
        return "", ""
    if client.sender_constraint_type == "dpop":
        proof = str(request.headers.get("dpop") or "")
        if not proof:
            raise ClientAuthenticationError("dpop_proof_required")
        dpop = verify_dpop_proof(
            proof=proof,
            client_id=client.client_id,
            method="POST",
            uri=f"{provider.validator.signer.issuer}/token",
            repository=repository,
        )
        return client.client_id, dpop.sender_constraint
    if client.sender_constraint_type == "mtls":
        return client.client_id, _trusted_mtls_sender_constraint(request)
    return client.client_id, ""


def _trusted_mtls_sender_constraint(request: Request) -> str:
    if str(request.headers.get("x-aicrm-mtls-verified") or "").upper() != "SUCCESS":
        raise ClientAuthenticationError("mtls_client_certificate_required")
    remote = request.client.host if request.client else ""
    configured = str(runtime_setting("AICRM_AUTH_TRUSTED_PROXY_ADDRESSES") or "127.0.0.1,::1")
    trusted = {value.strip() for value in configured.split(",") if value.strip()}
    try:
        remote_ip = ipaddress.ip_address(remote)
        allowed = any(remote_ip in ipaddress.ip_network(value, strict=False) for value in trusted)
    except ValueError:
        allowed = False
    if not allowed:
        raise ClientAuthenticationError("untrusted_mtls_proxy")
    return mtls_sender_constraint(str(request.headers.get("x-aicrm-mtls-client-cert-sha256") or ""))
