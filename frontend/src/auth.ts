import { Amplify } from "aws-amplify";
import { cognitoUserPoolsTokenProvider } from "aws-amplify/auth/cognito";
import { fetchAuthSession, signOut } from "aws-amplify/auth";

export const cognitoEnabled = import.meta.env.VITE_AUTH_MODE === "cognito";
const pool = import.meta.env.VITE_COGNITO_USER_POOL_ID;
const client = import.meta.env.VITE_COGNITO_USER_POOL_CLIENT_ID;
export const authConfigurationError =
  cognitoEnabled && (!pool || !client)
    ? "Configure the Cognito user pool and public app client before enabling managed authentication."
    : "";
const memory = new Map<string, string>();
// Access/refresh tokens stay in memory; no localStorage/sessionStorage persistence.
if (cognitoEnabled && !authConfigurationError) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: pool,
        userPoolClientId: client,
        loginWith: { email: true },
      },
    },
  });
  cognitoUserPoolsTokenProvider.setKeyValueStorage({
    async setItem(key: string, value: string) {
      memory.set(key, value);
    },
    async getItem(key: string) {
      return memory.get(key) ?? null;
    },
    async removeItem(key: string) {
      memory.delete(key);
    },
    async clear() {
      memory.clear();
    },
  });
}
export async function managedAccessToken() {
  if (!cognitoEnabled || authConfigurationError)
    throw new Error(
      authConfigurationError ||
        "Managed authentication is disabled in local mode.",
    );
  const session = await fetchAuthSession();
  const token = session.tokens?.accessToken.toString();
  if (!token) throw new Error("Sign in again to continue.");
  return token;
}
export async function clearManagedSession() {
  try {
    if (cognitoEnabled && !authConfigurationError) await signOut();
  } finally {
    memory.clear();
  }
}
