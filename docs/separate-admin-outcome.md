# Separate administrator application — 15 October 2026

The visitor and administrator interfaces now have independent React entry points, local URLs and production builds. Visitor navigation and its production bundle no longer contain the administrator dashboard. Both apps use email/password sign-in; the Local development identity/token-paste panel has been removed.

## Run and sign in

Start the existing database/APIs as described in [the complete local guide](local-test-guide.md). For an existing installation, rerun database start and restart the API runner once to load generated local account hashes. Run the two frontends in separate terminals:

```bash
npm --prefix frontend run dev
npm --prefix frontend run dev:admin
```

Visitor: http://localhost:5173 (`visitor@wonderland.local`). Administrator: http://localhost:5174 (`admin@wonderland.local`). Passwords are generated once in private `secrets/local.accounts.json`; open it locally. The existing smoke identities have matching accounts so previous bookings remain accessible. No signing keys, passwords or data are rotated by repeated setup.

The shared booking API verifies local passwords using salted scrypt hashes and issues the existing one-hour access tokens without exposing a token-copy workflow. Subjects/roles come from server configuration; wrong-portal credentials are rejected. Protected APIs still independently enforce administrator permissions. Sessions remain in memory and clear on refresh/sign-out. Login attempts are bounded to 20 per minute per API process; this local demo mechanism is not production distributed identity. Local accounts fail closed outside local/test mode; Cognito remains the prepared cloud authentication path.

`npm --prefix frontend run build` produces visitor `frontend/dist` and administrator `frontend/dist-admin`. Shared API/components are reused; there is no duplicated business backend. Compose has a separate administrator frontend service on 5174. The local Kubernetes image includes both static builds with separate nginx listeners, forwarded on visitor 5180 and administrator 5181; rebuild/deploy the cluster to use the updated images and account configuration. Its private passwords are in `secrets/kubernetes.accounts.json`. Separate admin cloud hosting/Cognito configuration is pending the approved cloud phase; cloud rendering excludes the local admin listener and local password accounts.

## Verification performed

- Full Python suite: **131 passed, no skips**; one existing Starlette TestClient deprecation warning.
- TypeScript checks and both production builds passed, including builds inside the Node 22 container.
- HTTP checks against running 5173/5174 verified separate HTML titles/entry modules, password sign-in, backend identity/role and wrong-portal rejection. Credential values were kept in memory and not printed.
- Visitor production bundle excludes the administrator dashboard; neither bundle contains the token-copy panel.
- Native readiness and Phase 2/3/4 HTTP smoke flows passed: booking, signed simulated payment/ticket, profile, permission checks, arrival/duplicate denial, ride/retry/history and reporting reconciliation.
- Compose configuration validated without printing resolved credentials.
- Frontend and booking images built; both nginx listeners passed syntax validation; booking image imported the login route with networking disabled.
- Cloud configuration regression checks passed with local account environment and local admin listener excluded.

Interactive browser appearance has not been reviewed in this change. Existing Minikube workloads were not rebuilt/redeployed by this update, and the separate Compose runtime was not started. No AWS account or external payment provider was contacted.
