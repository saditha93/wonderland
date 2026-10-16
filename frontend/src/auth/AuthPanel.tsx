import { api } from "../shared/api";
import { useState } from "react";
import { signUp, confirmSignUp, signIn, confirmSignIn } from "aws-amplify/auth";
import {
  cognitoEnabled,
  authConfigurationError,
  managedAccessToken,
} from "./session";

type Mode = "login" | "register" | "confirm" | "challenge";
export function AuthPanel({
  onSession,
  portal = "visitor",
}: {
  onSession: (token: string) => Promise<void>;
  portal?: "visitor" | "admin";
}) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function finished() {
    await onSession(await managedAccessToken());
    setMessage("Signed in. Your permissions are verified by the backend.");
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (authConfigurationError) return;
    setBusy(true);
    setMessage("");
    try {
      if (!cognitoEnabled) {
        const result = await api<{ access_token: string }>("/api/booking/auth/local-login", "", {
          method: "POST",
          body: JSON.stringify({ email, password, portal }),
        });
        await onSession(result.access_token);
        setMessage("Signed in.");
      } else if (mode === "register") {
        const result = await signUp({
          username: email,
          password,
          options: { userAttributes: { email, name } },
        });
        if (result.nextStep.signUpStep === "CONFIRM_SIGN_UP") {
          setMode("confirm");
          setMessage("Enter the confirmation code sent to your email.");
        } else {
          setMode("login");
          setMessage("Registration completed. Sign in to continue.");
        }
      } else if (mode === "confirm") {
        await confirmSignUp({ username: email, confirmationCode: code });
        setMode("login");
        setMessage("Email confirmed. Sign in to continue.");
      } else {
        const result =
          mode === "challenge"
            ? await confirmSignIn({ challengeResponse: code })
            : await signIn({ username: email, password });
        if (result.isSignedIn) await finished();
        else if (
          [
            "CONFIRM_SIGN_IN_WITH_SMS_CODE",
            "CONFIRM_SIGN_IN_WITH_TOTP_CODE",
            "CONFIRM_SIGN_IN_WITH_EMAIL_CODE",
            "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED",
          ].includes(result.nextStep.signInStep)
        ) {
          setMode("challenge");
          setStep(result.nextStep.signInStep);
          setMessage("Complete the additional sign-in step.");
        } else {
          setMessage(
            "This user pool requires an additional authentication flow that is not enabled in this form.",
          );
        }
      }
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Authentication could not be completed.",
      );
    } finally {
      setPassword("");
      setCode("");
      setBusy(false);
    }
  }
  return (
    <section className="section narrow">
      <p className="eyebrow">{portal === "admin" ? "Wonderland administration" : "Your Wonderland account"}</p>
      <h1 className="page-title">
        {mode === "register"
          ? "Create your account"
          : mode === "confirm"
            ? "Confirm your email"
            : mode === "challenge"
              ? "Complete sign-in"
              : portal === "admin" ? "Administrator sign in" : "Welcome back"}
      </h1>
      {authConfigurationError && (
        <div role="alert" className="error">
          {authConfigurationError}
        </div>
      )}
      <form className="panel booking-form" onSubmit={submit}>
        {mode === "register" && (
          <label>
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={80}
              autoComplete="name"
            />
          </label>
        )}
        {mode !== "challenge" && (
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="username"
            />
          </label>
        )}
        {(mode === "login" || mode === "register") && (
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete={
                mode === "register" ? "new-password" : "current-password"
              }
            />
          </label>
        )}
        {(mode === "confirm" || mode === "challenge") && (
          <label>
            {step.includes("NEW_PASSWORD")
              ? "New password"
              : "Confirmation code"}
            <input
              type={step.includes("NEW_PASSWORD") ? "password" : "text"}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              autoComplete="one-time-code"
            />
          </label>
        )}
        {message && (
          <p role="status" className="notice">
            {message}
          </p>
        )}
        <button
          className="primary"
          disabled={busy || !!authConfigurationError}
        >
          {busy
            ? "Please wait…"
            : mode === "register"
              ? "Register"
              : mode === "confirm"
                ? "Confirm email"
                : mode === "challenge"
                  ? "Continue"
                  : "Sign in"}
        </button>
        {cognitoEnabled && portal === "visitor" && (
        <button
          type="button"
          className="text-button"
          onClick={() => {
            setMode(mode === "register" ? "login" : "register");
            setPassword("");
            setCode("");
            setMessage("");
          }}
        >
          {mode === "register"
            ? "Already registered? Sign in"
            : "New here? Create an account"}
        </button>
        )}
      </form>
    </section>
  );
}
