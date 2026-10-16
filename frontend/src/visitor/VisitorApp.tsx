import { useEffect, useRef, useState } from "react";
import {
  api,
  money,
  type Attraction,
  type Booking,
  type Checkout,
  type Ticket,
  type Tier,
} from "../shared/api";
import { AuthPanel } from "../auth/AuthPanel";
import { AccountPanel } from "./AccountPanel";
import { clearManagedSession } from "../auth/session";

import { type Page, readLocation, parkDate } from "./navigation";
import { AttractionCard } from "./AttractionCard";
const initial = readLocation();
export function VisitorApp() {
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
  const [identity, setIdentity] = useState("");
  const [history, setHistory] = useState<Booking[]>([]);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [checkout, setCheckout] = useState<Checkout | null>(null);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [tierId, setTierId] = useState("");
  const [guests, setGuests] = useState(1);
  const [visitDate, setVisitDate] = useState(() =>
    parkDate(import.meta.env.VITE_DEMO_MODE === "true" ? 0 : 1),
  );
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
    void clearManagedSession().catch(() =>
      setError("Managed sign-out could not complete. Local session cleared."),
    );
    setHistory([]);
    setBooking(null);
    setTicket(null);
    setCheckout(null);
    setBusy(false);
    setError("");
    commandKey.current = crypto.randomUUID();
  }
  async function acceptManagedSession(value: string) {
    const current = epoch.current;
    const result = await api<{ subject: string; role: "visitor" | "admin" }>(
      "/api/booking/identity",
      value,
    );
    if (current !== epoch.current) return;
    if (result.role !== "visitor") {
      await clearManagedSession();
      throw new Error(
        "Use the administrator portal to sign in with this account.",
      );
    }
    epoch.current++;
    setToken(value);
    setIdentity(result.subject);
    setHistory([]);
    setBooking(null);
    setTicket(null);
    setCheckout(null);
    setBusy(false);
    commandKey.current = crypto.randomUUID();
    navigate("profile");
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
      Sign in to book or view your history.{" "}
      <button className="text-button" onClick={() => navigate("login")}>
        Sign in
      </button>
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
        <dt>Total</dt>
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
              ["profile", "My account"],
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
          {token ? (
            <button onClick={disconnect}>Sign out</button>
          ) : (
            <button onClick={() => navigate("login")}>Sign in</button>
          )}
        </nav>
      </header>
      <main className="shell">
        {import.meta.env.VITE_DEMO_MODE === "true" && (
          <p className="demo-note">
            Demo · No real payments. You can book today's visit at any time.
          </p>
        )}
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
                <p className="muted">Arrival times use Sri Lanka time.</p>
                <button
                  className="primary"
                  disabled={busy || !token || !selectedTier}
                >
                  {busy ? "Creating booking…" : "Create booking"}
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
                  Review your final total before paying. Your booking keeps this
                  price even if ticket prices change later.
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
                      Demo payment only. No money is charged.
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
                            if (current !== epoch.current) return;
                            if (result.provider === "local") {
                              await api(
                                `/api/booking/bookings/${reference}/sandbox-pay`,
                                token,
                                { method: "POST" },
                              );
                              if (current === epoch.current)
                                navigate("ticket", reference);
                            } else {
                              setCheckout(result);
                            }
                          })
                        }
                      >
                        {busy ? "Processing…" : "Continue to payment"}
                      </button>
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
                  Valid on the visit date in Asia/Colombo. Present this QR
                  ticket at the gate.
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
          <>
            <nav className="admin-tabs" aria-label="My account">
              <button
                className={page === "profile" ? "primary" : "secondary"}
                onClick={() => navigate("profile")}
              >
                Profile
              </button>
              <button
                className={page === "visits" ? "primary" : "secondary"}
                onClick={() => navigate("visits")}
              >
                Visit history
              </button>
            </nav>
            <AccountPanel key={identity + page} token={token} view={page} />
          </>
        )}
      </main>
      <footer>Wonderland Theme Park · Plan a day of wonder</footer>
    </>
  );
}
