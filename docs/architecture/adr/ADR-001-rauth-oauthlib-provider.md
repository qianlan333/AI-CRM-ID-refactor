# ADR-001: OAuthLib provider core for RAUTH

- Status: Accepted
- Date: 2026-07-12
- Owner: `platform_foundation.auth_platform`
- Decision scope: AI-CRM-owned authentication and authorization only

## Context

AI-CRM must replace signed admin authorization cookies, purpose-specific shared
bearer environment variables, route-local token comparisons and permissive
"token present" checks with one standards-compliant OAuth 2.0/OpenID Connect
authorization platform. The application is a FastAPI modular monolith, so the
provider core must not require a second Flask or Django runtime.

The implementation must support Authorization Code with S256 PKCE, Client
Credentials, rotating refresh tokens, opaque access-token introspection and
revocation, OIDC, metadata, service principals, delegated actors and
sender-constrained machine credentials. It must preserve upstream WeCom and
payment-provider protocols as integration concerns.

## Decision

Pin `oauthlib==3.3.1` as the OAuth 2.0/OIDC provider protocol engine.
Pin `PyJWT[crypto]==2.13.0` for asymmetric OIDC ID-token and registered
client-assertion JWS validation; algorithm allow-lists and required claims are
always supplied explicitly.

OAuthLib is framework-independent and its provider endpoints cover RFC 6749
authorization and token handling, RFC 7009 revocation, RFC 7636 PKCE, RFC 7662
introspection, RFC 8414 metadata and OpenID Connect Core. FastAPI adapters only
translate HTTP requests/responses and inject the repository-backed
`RequestValidator`; they do not reimplement grant dispatch or protocol error
semantics.

OAuthLib does not provide all required sender/client authentication profiles.
RAUTH therefore adds narrowly scoped extensions before OAuthLib dispatch:

- `private_key_jwt` client assertions are verified against registered public
  JWKs, exact issuer/subject/client/audience/time claims and a persisted one-use
  `jti` boundary.
- mTLS binds an access token to the verified certificate SHA-256 thumbprint
  supplied by the trusted reverse-proxy boundary.
- DPoP verifies the proof JWK/signature, method, URI, issued-at window and
  persisted one-use `jti`, then binds the access token to the JWK thumbprint.
- AI-CRM partner webhooks use registered HMAC/HTTP Message Signature keys with
  timestamp and persisted nonce replay protection; supplier-native callbacks
  remain unchanged.

The authorization server issues short-lived opaque access tokens. Only keyed
SHA-256 digests are persisted. Confidential client shared secrets use scrypt;
registered asymmetric clients store public JWKs only. High-risk writes expire
after five minutes and ordinary reads after ten minutes. Client Credentials
never issue refresh tokens. Human/delegated refresh tokens rotate on every use;
reuse revokes the entire family.

## Security invariants

- Raw access, refresh and authorization-code values are returned exactly once
  and never stored, logged, audited or placed in URLs except the standards-
  required short-lived authorization code redirect.
- Authorization handlers, repositories and workers receive an immutable
  `AuthContext`, never a raw bearer credential.
- Audience, capability, scope, resource constraints and sender constraints are
  evaluated together; no single claim grants access by itself.
- The authorization platform's token-hash pepper and any server signing key are
  secret-store references, never database values.
- OIDC ID tokens are asymmetric and short-lived; opaque access tokens remain
  the only AI-CRM API authorization credential.
- Legacy credentials and fallback flags are removed in the same release.

## Alternatives rejected

- Hand-written OAuth/OIDC endpoints: rejected because protocol parsing, grant
  dispatch and error behavior are security-critical and already implemented by
  mature provider libraries.
- Authlib server integration: its supported first-class authorization-server
  integrations are Flask and Django; its Starlette/FastAPI support is a client
  integration. Adopting it would require a second runtime or a larger custom
  server adapter than OAuthLib's documented framework-neutral interface.
- External identity platform: rejected for this release because the approved
  scope requires one deployable modular monolith release and must preserve the
  current single-tenant infrastructure boundary.
- JWT access tokens: rejected because immediate revocation, resource-policy
  changes and short incident containment require authoritative introspection.

## Consequences

- The PostgreSQL repository implements OAuthLib's `RequestValidator` contract
  and remains the source of client, code, token, grant and revocation truth.
- Protocol compliance tests invoke OAuthLib endpoints through FastAPI and test
  invalid as well as successful requests.
- The deployment must bootstrap every client/service principal and sender key
  before the single cutover. Rollback restores the previous exact release and
  runtime configuration as a unit; no dual-stack or legacy-token fallback is
  permitted.
