import { useEffect, useState } from "react";
import { api } from "../shared/api";

type Profile = { display_name: string; preferred_language: string };
type Visits = {
  visits: {
    booking_reference: string;
    guest_count: number;
    visit_date: string;
    checked_in_at: string;
  }[];
  ride_events: {
    event_id: string;
    booking_reference: string;
    attraction_name: string;
    guest_count: number;
    occurred_at: string;
  }[];
};
export function AccountPanel({
  token,
  view,
}: {
  token: string;
  view: "profile" | "visits";
}) {
  const [profile, setProfile] = useState<Profile>({
    display_name: "",
    preferred_language: "en",
  });
  const [visits, setVisits] = useState<Visits>({ visits: [], ride_events: [] });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setMessage("");
    setVisits({ visits: [], ride_events: [] });
    setProfile({ display_name: "", preferred_language: "en" });
    if (token) {
      setBusy(true);
      void (
        view === "profile"
          ? api<Profile>("/api/booking/profile", token).then((p) => {
              if (active) setProfile(p);
            })
          : api<Visits>("/api/gate/visits", token).then((v) => {
              if (active) setVisits(v);
            })
      )
        .catch((e) => {
          if (active) setMessage((e as Error).message);
        })
        .finally(() => {
          if (active) setBusy(false);
        });
    }
    return () => {
      active = false;
    };
  }, [token, view]);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/api/booking/profile", token, {
        method: "PUT",
        body: JSON.stringify({
          display_name: profile.display_name,
          preferred_language: profile.preferred_language,
        }),
      });
      setMessage("Profile saved.");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="section">
      <p className="eyebrow">Your Wonderland account</p>
      <h1 className="page-title">
        {view === "profile" ? "My profile" : "My visits"}
      </h1>
      {!token && (
        <div className="notice">
          Sign in to view your account.
        </div>
      )}
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
      {token && view === "profile" && (
        <form className="panel booking-form narrow" onSubmit={save}>
          <label>
            Display name
            <input
              required
              maxLength={80}
              value={profile.display_name}
              onChange={(e) =>
                setProfile({ ...profile, display_name: e.target.value })
              }
            />
          </label>
          <label>
            Preferred language
            <select
              value={profile.preferred_language}
              onChange={(e) =>
                setProfile({ ...profile, preferred_language: e.target.value })
              }
            >
              <option value="en">English</option>
              <option value="si">Sinhala</option>
              <option value="ta">Tamil</option>
            </select>
          </label>
          <button className="primary" disabled={busy}>
            Save profile
          </button>
        </form>
      )}
      {token && view === "visits" && (
        <>
          <div className="history-list">
            {visits.visits.map((v) => (
              <article className="panel" key={v.booking_reference}>
                <h3>
                  {v.visit_date} · {v.guest_count} guests
                </h3>
                <code>{v.booking_reference}</code>
                <p className="muted">
                  Arrived{" "}
                  {new Date(v.checked_in_at).toLocaleString("en-GB", {
                    timeZone: "Asia/Colombo",
                  })}{" "}
                  (Asia/Colombo)
                </p>
              </article>
            ))}
          </div>
          <h2>Ride history</h2>
          <div className="history-list">
            {visits.ride_events.map((r) => (
              <article className="panel" key={r.event_id}>
                <h3>
                  {r.attraction_name} · {r.guest_count} riders
                </h3>
                <p>
                  {new Date(r.occurred_at).toLocaleString("en-GB", {
                    timeZone: "Asia/Colombo",
                  })}{" "}
                  (Asia/Colombo)
                </p>
              </article>
            ))}
          </div>
          {!busy && !visits.visits.length && <p>No gate check-ins yet.</p>}
        </>
      )}
    </section>
  );
}
