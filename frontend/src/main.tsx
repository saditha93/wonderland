import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  api,
  money,
  type Attraction,
  type Booking,
  type Checkout,
  type Ticket,
  type Tier,
} from "./api";
import "./style.css";
import { AuthPanel } from "./AuthPanel";
import { AdminPanel } from "./AdminPanel";
import { VisitorAccount } from "./VisitorAccount";
import { cognitoEnabled, clearManagedSession } from "./auth";

type Page =
  | "home"
  | "attractions"
  | "book"
  | "history"
  | "payment"
  | "ticket"
  | "login"
  | "profile"
  | "visits"
  | "admin";
const pages: Page[] = [
  "home",
  "attractions",
  "book",
  "history",
  "payment",
  "ticket",
  "login",
  "profile",
  "visits",
  "admin",
];
function readLocation(): { page: Page; reference: string } {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("page") as Page;
  return {
    page: pages.includes(value)
      ? value
      : params.has("booking")
        ? "payment"
        : "home",
    reference: params.get("booking") ?? "",
  };
}
function parkDate(daysAhead: number) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Colombo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(Date.now() + daysAhead * 86400000));
  const get = (type: string) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}
const initial = readLocation();
function App() {
  const [page, setPage] = useState<Page>(initial.page);
  const [reference, setReference] = useState(initial.reference);
  const [attractions, setAttractions] = useState<Attraction[]>([]);
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [detail, setDetail] = useState<Attraction | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");
  const [draft, setDraft] = useState("");
  const [identity, setIdentity] = useState("");
  const [role, setRole] = useState<"visitor" | "admin" | null>(null);
  const [history, setHistory] = useState<Booking[]>([]);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [checkout, setCheckout] = useState<Checkout | null>(null);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [tierId, setTierId] = useState("");
  const [guests, setGuests] = useState(1);
  const [visitDate, setVisitDate] = useState(() => parkDate(1));
  const [slot, setSlot] = useState("09:00");
  const commandKey = useRef(crypto.randomUUID());
  const epoch = useRef(0);
  const selectedTier = tiers.find((t) => t.id === tierId);

  function navigate(next: Page, ref = "") {
    setPage(next);
    setReference(ref);
    setError("");
    setDetail(null);
    const query = new URLSearchParams({ page: next });
    if (ref) query.set("booking", ref);
    window.history.pushState({}, "", `/?${query}`);
  }
  useEffect(() => {
    const listener = () => {
      const loc = readLocation();
      setPage(loc.page);
      setReference(loc.reference);
      setError("");
    };
    window.addEventListener("popstate", listener);
    return () => window.removeEventListener("popstate", listener);
  }, []);
  useEffect(() => {
    let active = true;
    void Promise.allSettled([
      api<Attraction[]>("/api/attractions/attractions"),
      api<Tier[]>("/api/booking/ticket-tiers"),
    ])
      .then(([a, t]) => {
        if (!active) return;
        const errors: string[] = [];
        if (a.status === "fulfilled") setAttractions(a.value);
        else errors.push("Attractions are temporarily unavailable.");
        if (t.status === "fulfilled") {
          setTiers(t.value);
          setTierId(t.value[0]?.id ?? "");
        } else errors.push("Ticket prices are temporarily unavailable.");
        setCatalogError(errors.join(" "));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    setHistory([]);
    if (page === "history" && token) {
      setBusy(true);
      void api<Booking[]>("/api/booking/bookings", token)
        .then((rows) => {
          if (active) setHistory(rows);
        })
        .catch((e) => {
          if (active) setError((e as Error).message);
        })
        .finally(() => {
          if (active) setBusy(false);
        });
    }
    return () => {
      active = false;
    };
  }, [page, token]);
  useEffect(() => {
    let active = true;
    setBooking(null);
    setTicket(null);
    setCheckout(null);
    if (reference && token && (page === "ticket" || page === "payment")) {
      setBusy(true);
      void api<Booking>(`/api/booking/bookings/${reference}`, token)
        .then(async (row) => {
          if (!active) return;
          setBooking(row);
          if (page === "ticket") {
            const result = await api<Ticket>(
              `/api/booking/bookings/${reference}/ticket`,
              token,
            );
            if (active) setTicket(result);
          }
        })
        .catch((e) => {
          if (active) setError((e as Error).message);
        })
        .finally(() => {
          if (active) setBusy(false);
        });
    }
    return () => {
      active = false;
    };
  }, [page, reference, token]);

  async function run(operation: (currentEpoch: number) => Promise<void>) {
    const current = epoch.current;
    setBusy(true);
    setError("");
    try {
      await operation(current);
    } catch (e) {
      if (current === epoch.current) setError((e as Error).message);
    } finally {
      if (current === epoch.current) setBusy(false);
    }
  }
  function disconnect() {
    epoch.current++;
    setToken("");
    setIdentity("");
    setRole(null);
    void clearManagedSession().catch(() =>
      setError("Managed sign-out could not complete. Local session cleared."),
    );
    setDraft("");
    setHistory([]);
    setBooking(null);
    setTicket(null);
    setCheckout(null);
    setBusy(false);
    setError("");
    commandKey.current = crypto.randomUUID();
  }
  async function connect(e: React.FormEvent) {
    e.preventDefault();
    await run(async (current) => {
      const result = await api<{ subject: string; role: "visitor" | "admin" }>(
        "/api/booking/identity",
        draft.trim(),
      );
      if (current !== epoch.current) return;
      epoch.current++;
      setToken(draft.trim());
      setIdentity(result.subject);
      setRole(result.role);
      setDraft("");
      setHistory([]);
      setBooking(null);
      setTicket(null);
      setCheckout(null);
      setBusy(false);
      commandKey.current = crypto.randomUUID();
    });
  }
  async function acceptManagedSession(value: string) {
    const current = epoch.current;
    const result = await api<{ subject: string; role: "visitor" | "admin" }>(
      "/api/booking/identity",
      value,
    );
    if (current !== epoch.current) return;
    epoch.current++;
    setToken(value);
    setIdentity(result.subject);
    setRole(result.role);
    setHistory([]);
    setBooking(null);
    setTicket(null);
    setCheckout(null);
    setBusy(false);
    commandKey.current = crypto.randomUUID();
    navigate(result.role === "admin" ? "admin" : "profile");
  }
  async function refreshPublicData() {
    const [a, t] = await Promise.allSettled([
      api<Attraction[]>("/api/attractions/attractions"),
      api<Tier[]>("/api/booking/ticket-tiers"),
    ]);
    if (a.status === "fulfilled") setAttractions(a.value);
    if (t.status === "fulfilled") {
      setTiers(t.value);
      setTierId(t.value[0]?.id ?? "");
      setGuests(t.value[0]?.min_guests ?? 1);
      changeCommand();
    }
  }
  async function createBooking(e: React.FormEvent) {
    e.preventDefault();
    await run(async (current) => {
      const result = await api<Booking>("/api/booking/bookings", token, {
        method: "POST",
        headers: { "Idempotency-Key": commandKey.current },
        body: JSON.stringify({
          tier_id: tierId,
          guest_count: guests,
          visit_date: visitDate,
          time_slot: slot,
        }),
      });
      if (current !== epoch.current) return;
      commandKey.current = crypto.randomUUID();
      navigate("payment", result.reference);
    });
  }
  function changeCommand() {
    commandKey.current = crypto.randomUUID();
  }
  const filtered = attractions.filter((a) =>
    `${a.name} ${a.category}`.toLowerCase().includes(search.toLowerCase()),
  );
  const authNotice = !token ? (
    <div className="notice">
      {cognitoEnabled
        ? "Sign in to book or view your history."
        : "Connect a signed local development token below to book or view your history."}{" "}
      Public attractions and prices are available without a token.
    </div>
  ) : null;
  const bookingSummary = booking && (
    <dl className="summary">
      <div>
        <dt>Ticket</dt>
        <dd>
          {booking.tier_name} · {booking.guest_count} guest
          {booking.guest_count > 1 ? "s" : ""}
        </dd>
      </div>
      <div>
        <dt>Visit</dt>
        <dd>
          {booking.visit_date} · {booking.time_slot}
        </dd>
      </div>
      <div>
        <dt>Stored total</dt>
        <dd>{money(booking.amount_cents, booking.currency)}</dd>
      </div>
      <div>
        <dt>Status</dt>
        <dd className="capitalize">
          {booking.status} · {booking.payment_status}
        </dd>
      </div>
    </dl>
  );

  return (
    <>
      <header className="site-header">
        <a
          href="/?page=home"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            navigate("home");
          }}
        >
          WONDERLAND <span>✳</span>
        </a>
        <nav aria-label="Main navigation">
          {(
            [
              ["attractions", "Explore"],
              ["book", "Book a visit"],
              ["history", "My bookings"],
              ["visits", "My visits"],
              ["profile", "My profile"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              onClick={() => navigate(id)}
              aria-current={page === id ? "page" : undefined}
            >
              {label}
            </button>
          ))}
          {role === "admin" && (
            <button
              onClick={() => navigate("admin")}
              aria-current={page === "admin" ? "page" : undefined}
            >
              Administrator
            </button>
          )}
          {token ? (
            <button onClick={disconnect}>Sign out</button>
          ) : (
            <button onClick={() => navigate("login")}>Sign in</button>
          )}
        </nav>
      </header>
      <main className="shell">
        {error && (
          <div role="alert" className="error">
            {error}
          </div>
        )}
        {catalogError && (
          <div role="alert" className="error">
            {catalogError}
          </div>
        )}
        {page === "home" && (
          <>
            <section className="hero">
              <p className="eyebrow">Your next great day out</p>
              <h1>
                A little wonder.
                <br />A world of possibility.
              </h1>
              <p>
                Big thrills, small discoveries, and the moments you share. Find
                your kind of adventure at Wonderland.
              </p>
              <button
                className="primary"
                onClick={() => navigate("attractions")}
              >
                Explore the park <span aria-hidden="true">↗</span>
              </button>
              <div className="hero-note">
                Local development · Test payments only
              </div>
            </section>
            <section className="section">
              <div className="section-top">
                <div>
                  <p className="eyebrow">Make a day of it</p>
                  <h2>One park. Your kind of adventure.</h2>
                </div>
                <button
                  className="text-button"
                  onClick={() => navigate("attractions")}
                >
                  See all attractions →
                </button>
              </div>
              <div className="catalog-grid">
                {attractions.slice(0, 3).map((a) => (
                  <AttractionCard
                    key={a.id}
                    attraction={a}
                    onSelect={() => {
                      navigate("attractions");
                      setDetail(a);
                    }}
                  />
                ))}
              </div>
            </section>
            <section className="section">
              <p className="eyebrow">Bring your favourite people</p>
              <h2>Choose your ticket</h2>
              <div className="tier-grid">
                {tiers.map((t) => (
                  <article className="tier-card" key={t.id}>
                    <h3>{t.name}</h3>
                    <p>
                      {t.min_guests === t.max_guests
                        ? t.max_guests
                        : `Up to ${t.max_guests}`}{" "}
                      guest{t.max_guests > 1 ? "s" : ""}
                    </p>
                    <strong>{money(t.price_cents)}</strong>
                    <button
                      className="secondary"
                      onClick={() => {
                        setTierId(t.id);
                        setGuests(t.min_guests);
                        changeCommand();
                        navigate("book");
                      }}
                    >
                      Choose {t.name}
                    </button>
                  </article>
                ))}
              </div>
            </section>
          </>
        )}
        {page === "attractions" && (
          <section className="section">
            <p className="eyebrow">Find your adventure</p>
            <h1 className="page-title">Explore Wonderland</h1>
            <p className="lead">
              From first discoveries to your next adrenaline rush.
            </p>
            <label className="search">
              Search attractions
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Try water, family, or coaster"
              />
            </label>
            {detail && (
              <article className="detail-panel">
                <button className="text-button" onClick={() => setDetail(null)}>
                  Close details ×
                </button>
                <h2>{detail.name}</h2>
                <p>{detail.description}</p>
                <p>
                  {detail.category} · {detail.thrill_level} thrill ·{" "}
                  {detail.operational_status}
                </p>
                <p>
                  Age guidance:{" "}
                  {detail.minimum_age
                    ? `${detail.minimum_age}+ years`
                    : "All ages"}{" "}
                  · Height guidance:{" "}
                  {detail.minimum_height_cm
                    ? `${detail.minimum_height_cm}+ cm`
                    : "No minimum"}
                </p>
                <button className="primary" onClick={() => navigate("book")}>
                  Plan your visit
                </button>
              </article>
            )}
            {loading ? (
              <p role="status">Loading attractions…</p>
            ) : (
              <div className="catalog-grid">
                {filtered.map((a) => (
                  <AttractionCard
                    key={a.id}
                    attraction={a}
                    onSelect={() =>
                      void run(async (current) => {
                        const row = await api<Attraction>(
                          `/api/attractions/attractions/${a.id}`,
                        );
                        if (current === epoch.current) setDetail(row);
                      })
                    }
                  />
                ))}
              </div>
            )}
            {!loading && !catalogError && filtered.length === 0 && (
              <p>No attractions match your search.</p>
            )}
          </section>
        )}
        {page === "book" && (
          <section className="section">
            <p className="eyebrow">Good times start here</p>
            <h1 className="page-title">Plan your visit</h1>
            {authNotice}
            <div className="booking-layout">
              <form className="panel booking-form" onSubmit={createBooking}>
                <label>
                  Ticket tier
                  <select
                    value={tierId}
                    required
                    onChange={(e) => {
                      setTierId(e.target.value);
                      setGuests(
                        tiers.find((t) => t.id === e.target.value)
                          ?.min_guests ?? 1,
                      );
                      changeCommand();
                    }}
                  >
                    {tiers.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name} — {money(t.price_cents)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Number of guests
                  <input
                    type="number"
                    min={selectedTier?.min_guests ?? 1}
                    max={selectedTier?.max_guests ?? 5}
                    required
                    value={guests}
                    onChange={(e) => {
                      setGuests(Number(e.target.value));
                      changeCommand();
                    }}
                  />
                </label>
                <label>
                  Visit date
                  <input
                    type="date"
                    min={parkDate(0)}
                    max={parkDate(365)}
                    required
                    value={visitDate}
                    onChange={(e) => {
                      setVisitDate(e.target.value);
                      changeCommand();
                    }}
                  />
                </label>
                <label>
                  Preferred arrival time
                  <select
                    value={slot}
                    onChange={(e) => {
                      setSlot(e.target.value);
                      changeCommand();
                    }}
                  >
                    {["09:00", "12:00", "15:00"].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
                <p className="muted">
                  Times are in Asia/Colombo. Time slots are provisional;
                  capacity limits are not defined yet.
                </p>
                <button
                  className="primary"
                  disabled={busy || !token || !selectedTier}
                >
                  {busy ? "Creating booking…" : "Continue to test payment →"}
                </button>
              </form>
              <aside className="panel order-summary">
                <p className="eyebrow">Your day at Wonderland</p>
                <h2>{selectedTier?.name ?? "Choose a tier"}</h2>
                <p>
                  {guests} guest{guests > 1 ? "s" : ""}
                </p>
                <strong className="price">
                  {selectedTier ? money(selectedTier.price_cents) : "—"}
                </strong>
                <p className="muted">
                  The server validates the current stored price and records a
                  price snapshot. Your pending booking will show the final total
                  before payment.
                </p>
              </aside>
            </div>
          </section>
        )}
        {page === "history" && (
          <section className="section">
            <p className="eyebrow">Your adventures</p>
            <h1 className="page-title">My bookings</h1>
            {authNotice}
            {busy && <p role="status">Loading…</p>}
            <div className="history-list">
              {history.map((b) => (
                <article className="panel history-row" key={b.reference}>
                  <div>
                    <span className={`badge ${b.status}`}>{b.status}</span>
                    <h3>
                      {b.tier_name} · {b.guest_count} guests
                    </h3>
                    <p>
                      {b.visit_date} at {b.time_slot} ·{" "}
                      {money(b.amount_cents, b.currency)}
                    </p>
                    <code>{b.reference}</code>
                  </div>
                  <button
                    className="secondary"
                    onClick={() =>
                      navigate(
                        b.status === "confirmed" ? "ticket" : "payment",
                        b.reference,
                      )
                    }
                  >
                    {b.status === "confirmed"
                      ? "View digital ticket"
                      : "Continue payment"}
                  </button>
                </article>
              ))}
            </div>
            {token && !busy && !error && history.length === 0 && (
              <p>No bookings yet. Your next adventure is waiting.</p>
            )}
          </section>
        )}
        {page === "payment" && (
          <section className="section narrow">
            <p className="eyebrow">One more step</p>
            <h1 className="page-title">Test payment</h1>
            {authNotice}
            {booking && (
              <div className="panel">
                <code>{booking.reference}</code>
                {bookingSummary}
                {booking.status === "confirmed" ? (
                  <>
                    <div className="notice">
                      Payment verified. Your ticket is ready.
                    </div>
                    <button
                      className="primary"
                      onClick={() => navigate("ticket", reference)}
                    >
                      View digital ticket
                    </button>
                  </>
                ) : (
                  <>
                    <p className="muted">
                      This is a test environment. No real-money payment is
                      supported. Returning from checkout never confirms a
                      booking by itself.
                    </p>
                    {!checkout && (
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() =>
                          void run(async (current) => {
                            const result = await api<Checkout>(
                              `/api/booking/bookings/${reference}/checkout`,
                              token,
                              { method: "POST" },
                            );
                            if (current === epoch.current) setCheckout(result);
                          })
                        }
                      >
                        Start test checkout
                      </button>
                    )}
                    {checkout?.provider === "local" && (
                      <div className="simulator">
                        <h3>Local payment simulator</h3>
                        <p>
                          No card details or payment provider connection. This
                          sends a server-signed test event through verification
                          and confirmation.
                        </p>
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() =>
                            void run(async (current) => {
                              await api(
                                `/api/booking/bookings/${reference}/sandbox-pay`,
                                token,
                                { method: "POST" },
                              );
                              if (current === epoch.current)
                                navigate("ticket", reference);
                            })
                          }
                        >
                          {busy
                            ? "Verifying…"
                            : "Simulate successful test payment"}
                        </button>
                      </div>
                    )}
                    {checkout?.provider === "stripe" &&
                      checkout.checkout_url && (
                        <a
                          className="primary inline-button"
                          href={checkout.checkout_url}
                        >
                          Open Stripe test checkout ↗
                        </a>
                      )}
                    <div className="button-row">
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() =>
                          void run(async (current) => {
                            const result = await api<Booking>(
                              `/api/booking/bookings/${reference}`,
                              token,
                            );
                            if (current === epoch.current) setBooking(result);
                          })
                        }
                      >
                        Refresh verified status
                      </button>
                      <button
                        className="text-button"
                        onClick={() => navigate("history")}
                      >
                        Return without paying
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </section>
        )}
        {page === "ticket" && (
          <section className="section narrow">
            <p className="eyebrow">Your adventure awaits</p>
            <h1 className="page-title">Your digital ticket</h1>
            {authNotice}
            {ticket && (
              <article className="panel digital-ticket">
                <div className="badge confirmed">Payment verified</div>
                <h2>Wonderland Theme Park</h2>
                <img
                  src={ticket.qr_data_url}
                  alt="Signed QR ticket for this confirmed booking"
                  width="240"
                  height="240"
                />
                <code>{ticket.booking.reference}</code>
                {bookingSummary}
                <p className="muted">
                  Valid until the end of the visit date in Asia/Colombo. Gate
                  scanning is a Phase 3 feature.
                </p>
                <a
                  className="secondary inline-button"
                  href={ticket.qr_data_url}
                  download={`${ticket.booking.reference}.png`}
                >
                  Download QR ticket
                </a>
              </article>
            )}
          </section>
        )}
        {page === "login" && <AuthPanel onSession={acceptManagedSession} />}
        {(page === "profile" || page === "visits") && (
          <VisitorAccount key={identity + page} token={token} view={page} />
        )}
        {page === "admin" &&
          (role === "admin" && token ? (
            <AdminPanel
              key={identity}
              token={token}
              onDataChanged={() => void refreshPublicData()}
            />
          ) : (
            <div role="alert" className="error">
              Administrator access is required. Backend permissions are checked
              on every operation.
            </div>
          ))}
        {!cognitoEnabled && (
          <details className="developer-panel">
            <summary>
              Local development identity{" "}
              {identity ? `· ${identity}` : "· not connected"}
            </summary>
            <p>
              This phase uses signed developer tokens, not Cognito login. Tokens
              stay in memory and are cleared on refresh. Generate one with{" "}
              <code>.venv/bin/python scripts/local-token.py</code>, then paste
              it here. Never use AWS credentials or payment secrets.
            </p>
            <form onSubmit={connect}>
              <label>
                Local access token
                <input
                  type="password"
                  autoComplete="off"
                  value={draft}
                  maxLength={8192}
                  onChange={(e) => setDraft(e.target.value)}
                  required
                />
              </label>
              <div className="button-row">
                <button className="secondary" disabled={busy}>
                  Connect token
                </button>
                {token && (
                  <button
                    type="button"
                    className="text-button"
                    onClick={disconnect}
                  >
                    Disconnect
                  </button>
                )}
              </div>
            </form>
          </details>
        )}
      </main>
      <footer>
        Wonderland Theme Park · SE6020 · Phase 3 local development · No AWS
        deployment
      </footer>
    </>
  );
}
function AttractionCard({
  attraction: a,
  onSelect,
}: {
  attraction: Attraction;
  onSelect: () => void;
}) {
  const categoryClass =
    a.thrill_level === "high"
      ? "thrill"
      : a.category === "Water ride"
        ? "water"
        : "gentle";
  return (
    <article className="attraction-card">
      <div className={`attraction-art ${categoryClass}`} aria-hidden="true">
        <span>
          {a.thrill_level === "high"
            ? "↟"
            : a.category === "Water ride"
              ? "≈"
              : "✳"}
        </span>
        <div className="art-orbit" />
      </div>
      <div className="attraction-copy">
        <div className="card-meta">
          <span>{a.category}</span>
          <span className="capitalize">{a.operational_status}</span>
        </div>
        <h3>{a.name}</h3>
        <p>{a.description}</p>
        <p className="guidance">
          {a.thrill_level} thrill ·{" "}
          {a.minimum_height_cm ? `${a.minimum_height_cm}+ cm` : "All heights"}
        </p>
        <button className="text-button" onClick={onSelect}>
          Explore attraction →
        </button>
      </div>
    </article>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
