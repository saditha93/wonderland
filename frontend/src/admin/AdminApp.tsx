import { useRef, useState } from "react";
import { AdminPanel } from "./AdminPanel";
import { AuthPanel } from "../auth/AuthPanel";
import { api } from "../shared/api";
import { clearManagedSession } from "../auth/session";

export function AdminApp() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const epoch = useRef(0);
  async function signIn(value: string) {
    const current = epoch.current;
    const identity = await api<{ role: "visitor" | "admin" }>("/api/booking/identity", value);
    if (current !== epoch.current) return;
    if (identity.role !== "admin") {
      await clearManagedSession();
      throw new Error("Administrator access is required for this portal.");
    }
    setError("");
    setToken(value);
  }
  async function signOut() {
    epoch.current++;
    setToken("");
    try {
      await clearManagedSession();
    } catch {
      setError("Your local session was cleared. Managed sign-out could not complete.");
    }
  }
  return <>
    <header className="site-header">
      <a className="brand" href="/">WONDERLAND <span>✳</span></a>
      <nav aria-label="Administrator navigation">
        <span className="admin-portal-label">Administrator portal</span>
        {token && <button onClick={() => void signOut()}>Sign out</button>}
      </nav>
    </header>
    <main className="shell">
      {error && <div role="alert" className="error">{error}</div>}
      {token ? <AdminPanel token={token} onDataChanged={() => {}} /> : <AuthPanel portal="admin" onSession={signIn} />}
    </main>
    <footer>Wonderland Theme Park · Park operations</footer>
  </>;
}

