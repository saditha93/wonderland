# booking-service

Independent health-only process/image. Config: `APP_ENVIRONMENT=local`, `APP_VERSION=0.1.0`. Endpoints: `/health`, `/health/live`, `/health/ready`, `/docs`. Readiness currently means skeleton initialization only; it does not validate PostgreSQL, Cognito, queues or payments. No authentication is needed for these metadata-only endpoints. No domain routes exist. Structured stdout logs include validated request ID, route template, status and timing, without headers, bodies or query strings. See root README for build/run/test commands.
