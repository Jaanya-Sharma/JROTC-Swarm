# Threat model

## Scope and assets

This application is intended for local development and demonstration. It serves
an MP4, a live WebSocket track stream, replay samples, zones, and zone events.
Assets to protect are operator credentials and JWTs, the local video and SQLite
database, the integrity of the tactical display, and service availability.

## Threats and current controls

| Attacker and goal | Current mitigation |
| --- | --- |
| A malicious website attempts to read or issue browser requests to the API. | CORS accepts only `http://localhost:<port>` and `http://127.0.0.1:<port>`, with explicit `GET`, `POST`, and `OPTIONS` methods plus the required headers. It does not use wildcard origins, methods, or headers. CORS is browser protection, not authentication. |
| A client sends malformed, oversized, or out-of-range API input to cause errors or corrupt state. | Request schemas forbid unknown fields; zone coordinates are bounded to `[0, 1]`; names and credentials are length-limited; replay/event windows and limits are capped; malformed and unsatisfiable video ranges are rejected. FastAPI request-validation errors are normalized to safe HTTP `400` responses. |
| A client sends malformed WebSocket connection input. | The only WebSocket query input, `access_token`, is bounded to 4096 characters. Invalid authentication or policy input is rejected with WebSocket close code `1008`; internal stream failures close with `1011` without exposing an exception. A WebSocket cannot send HTTP `400` after it has upgraded. |
| A local/network client brute-forces credentials or opens excessive requests/streams. | In-memory per-IP limiting protects all HTTP requests and WebSocket connection attempts; token issuance has a stricter five-attempts-per-minute limiter. Replay spans are limited to 10 minutes and 20,000 rows. |
| A client attempts SQL injection through replay or stored samples. | The runtime `SELECT` and `INSERT` statements use SQLite placeholders and bound values. Schema and index statements are static application text, never constructed from client input. |
| Someone reads the repository to obtain credentials or signing keys. | Runtime credentials and `JWT_SECRET` are read from environment variables. `.env` files, databases, videos, models, and logs are ignored; the committed `.env.example` contains placeholders only. |
| A stolen JWT is used to access protected endpoints. | When `AUTH_REQUIRED=true`, bearer tokens are verified with HS256 using the environment-only secret, limited to 4096 characters, and expire after `JWT_EXPIRES_MINUTES` (60 by default). Password comparison uses constant-time comparison. |
| A vulnerable dependency is exploited. | Direct Python and Node dependencies are pinned. `npm audit` reported no vulnerabilities at the last review; non-critical transitive Python updates should be reviewed during routine maintenance. |

## Deployment assumptions and residual risk

Authentication is deliberately disabled by default for the local demo
(`AUTH_REQUIRED=false`). Before binding the service beyond a trusted local
machine, enable authentication, set a long random `JWT_SECRET`, use HTTPS, and
place it behind a trusted reverse proxy. Do not trust forwarded-IP headers until
that proxy is configured.

The rate limiter, zone list, and event list are process-local, so they do not
coordinate across multiple workers or survive restarts. This application is not
a production security boundary; an internet-facing deployment also needs
persistent auditing, centralized rate limiting, secure secret management, and a
real identity provider.
