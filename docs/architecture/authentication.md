# Cognito integration: implemented, offline-tested, cloud verification pending
No AWS account, user pool, app client or group was created or contacted during this phase. Native developer mode remains local. Configuration below is for a future explicitly approved integration test, not an instruction to create chargeable infrastructure now.

## Backend configuration
Set APP_AUTH_MODE=cognito, APP_COGNITO_REGION, APP_COGNITO_USER_POOL_ID and APP_COGNITO_CLIENT_ID consistently for all three APIs. APP_COGNITO_ADMIN_GROUP defaults to administrators. APP_COGNITO_AUDIENCE is optional for access tokens with a resource-bound audience; client_id is always checked. Use APP_ENVIRONMENT=aws in future cloud deployments; local identity mode is forbidden there.

The issuer is derived from the validated region and pool ID, not untrusted token URLs. PyJWKClient fetches only that issuer's JWKS with a three-second timeout, caches its key set for five minutes and refreshes for unknown keys. Token alg must be RS256. Access token use, issuer, client ID, expiry and human-user claims are required. Administrator access comes only from the signed configured cognito:groups entry; a role field from the browser/profile or arbitrary JWT role claim cannot grant it. Missing/unavailable signing keys cause 401/503, not an authorization bypass.

## Frontend configuration
frontend/.env.example shows public IDs only. In a future approved setup, set VITE_AUTH_MODE=cognito, VITE_COGNITO_USER_POOL_ID, VITE_COGNITO_USER_POOL_CLIENT_ID and the approved VITE_API_BASE_URL if needed. Vite values are public build output: never place app-client secrets, AWS keys, signing keys or payment secrets there. Use a browser/public app client with no client secret. Configure email signup and allowed name/email attributes; do not expose administrator group assignment through signup.

The Amplify SDK handles signUp, confirmSignUp, signIn, confirmSignIn, fetchAuthSession and signOut. Common code challenges and required-new-password responses are supported; additional flow-selection challenges are explicitly reported as unsupported. In-memory storage holds access/refresh state; reload clears it. Each protected API call fetches the current managed access token so the SDK can refresh while the session remains in memory. No AWS network request is made in default local mode.

Profiles/preferences are stored in booking.visitor_profiles, keyed only by verified sub; roles are not editable profile attributes. Use trusted administrator provisioning to assign groups only after approval. A group name or user-access scope containing 'admin' is not itself application administrator permission.

## Required approved verification
- Confirm target account/region and user pool/client configuration; define allowed frontend origins and HTTPS API endpoints.
- Verify email signup/confirmation, login, failure/expiry, actual MFA and required-password challenges.
- Verify visitor/admin groups and forbidden operations from direct HTTP clients, not only navigation visibility.
- Check token issuer/client_id/token_use/audience and JWKS rotation/unavailability against the actual pool.
- Verify logout/revocation expectations; local JWT validation cannot immediately revoke an otherwise valid signed token without additional state.
- Record actual results separately; offline generated RSA tokens are not evidence of AWS integration.

Primary references consulted for this implementation: [Cognito access-token claims](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html), [Amplify sign-in](https://docs.amplify.aws/react/frontend/auth/sign-in/), [Amplify sign-up](https://docs.amplify.aws/react/frontend/auth/sign-up/), [PyJWT validation/JWKS](https://pyjwt.readthedocs.io/en/stable/usage.html).
