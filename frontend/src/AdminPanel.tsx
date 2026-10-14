import { useEffect, useRef, useState } from "react";
import { api, money, type Attraction, type Tier } from "./api";

type Tab = "overview" | "attractions" | "pricing" | "gate" | "rides";
type TierRow = Tier & { active: boolean };
type EditAttraction = Omit<Attraction, "id">;
type EditTier = {
  name: string;
  min_guests: number;
  max_guests: number;
  price_cents: number;
  active: boolean;
};
type Sales = {
  tier_name: string;
  tickets: number;
  guests: number;
  revenue_cents: number;
  currency: string;
}[];
type Activity = {
  arriving_guests: number;
  arrival_bookings: number;
  arrivals: {
    booking_reference: string;
    guest_count: number;
    checked_in_at: string;
  }[];
  rides: { attraction_name: string; riders: number; ride_events: number }[];
};
type Preview = {
  reference: string;
  guest_count: number;
  visit_date: string;
  already_checked_in: boolean;
};
const emptyAttraction: EditAttraction = {
  name: "",
  description: "",
  category: "Family ride",
  thrill_level: "gentle",
  minimum_age: 0,
  minimum_height_cm: 0,
  operational_status: "open",
};
const emptyTier: EditTier = {
  name: "",
  min_guests: 1,
  max_guests: 1,
  price_cents: 4000,
  active: true,
};
export function AdminPanel({
  token,
  onDataChanged,
}: {
  token: string;
  onDataChanged: () => void;
}) {
  const [tab, setTab] = useState<Tab>("overview");
  const [attractions, setAttractions] = useState<Attraction[]>([]);
  const [tiers, setTiers] = useState<TierRow[]>([]);
  const [sales, setSales] = useState<Sales>([]);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [editId, setEditId] = useState("");
  const [a, setA] = useState<EditAttraction>(emptyAttraction);
  const [tierId, setTierId] = useState("");
  const [t, setT] = useState<EditTier>(emptyTier);
  const [scan, setScan] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [guests, setGuests] = useState(1);
  const [rideRef, setRideRef] = useState("");
  const [rideAttraction, setRideAttraction] = useState("");
  const [riders, setRiders] = useState(1);
  const rideId = useRef(crypto.randomUUID());
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    setError("");
    setBusy(true);
    void Promise.allSettled([
      api<Attraction[]>("/api/attractions/admin/attractions", token),
      api<TierRow[]>("/api/booking/admin/ticket-tiers", token),
      api<Sales>("/api/booking/admin/sales", token),
      api<Activity>("/api/gate/admin/activity", token),
    ])
      .then(([a, t, s, v]) => {
        if (!active) return;
        if (a.status === "fulfilled") setAttractions(a.value);
        if (t.status === "fulfilled") setTiers(t.value);
        if (s.status === "fulfilled") setSales(s.value);
        if (v.status === "fulfilled") setActivity(v.value);
        const failures = [a, t, s, v].filter((r) => r.status === "rejected");
        if (failures.length)
          setError(
            "Some services are unavailable or access was denied. Available sections remain usable.",
          );
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [token, refresh]);
  async function action(operation: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await operation();
      if (alive.current) {
        setMessage(success);
        onDataChanged();
        setRefresh((v) => v + 1);
      }
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  function pickAttraction(row: Attraction) {
    setEditId(row.id);
    setA({
      name: row.name,
      description: row.description,
      category: row.category,
      thrill_level: row.thrill_level,
      minimum_age: row.minimum_age,
      minimum_height_cm: row.minimum_height_cm,
      operational_status: row.operational_status,
    });
  }
  async function saveAttraction(e: React.FormEvent) {
    e.preventDefault();
    await action(async () => {
      await api(
        `/api/attractions/attractions${editId ? "/" + editId : ""}`,
        token,
        { method: editId ? "PUT" : "POST", body: JSON.stringify(a) },
      );
      if (alive.current) {
        setEditId("");
        setA(emptyAttraction);
      }
    }, "Attraction saved.");
  }
  async function saveTier(e: React.FormEvent) {
    e.preventDefault();
    await action(async () => {
      await api(
        `/api/booking/admin/ticket-tiers${tierId ? "/" + tierId : ""}`,
        token,
        { method: tierId ? "PUT" : "POST", body: JSON.stringify(t) },
      );
      if (alive.current) {
        setTierId("");
        setT(emptyTier);
      }
    }, "Ticket tier saved. Existing booking snapshots are preserved.");
  }
  return (
    <section className="section">
      <p className="eyebrow">Park operations</p>
      <h1 className="page-title">Administrator dashboard</h1>
      <nav className="admin-tabs" aria-label="Administrator sections">
        {(["overview", "attractions", "pricing", "gate", "rides"] as Tab[]).map(
          (id) => (
            <button
              className={tab === id ? "primary" : "secondary"}
              key={id}
              onClick={() => {
                setTab(id);
                setMessage("");
                setError("");
              }}
            >
              {id === "gate"
                ? "Gate check-in"
                : id === "rides"
                  ? "Ride usage"
                  : id}
            </button>
          ),
        )}
        <button
          className="text-button"
          onClick={() => setRefresh((v) => v + 1)}
          disabled={busy}
        >
          Refresh data
        </button>
      </nav>
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      {message && (
        <div role="status" className="notice">
          {message}
        </div>
      )}
      {tab === "overview" && (
        <>
          <div className="tier-grid">
            <article className="tier-card">
              <h3>Guests arriving today</h3>
              <strong>{activity?.arriving_guests ?? "—"}</strong>
              <p>{activity?.arrival_bookings ?? 0} checked-in bookings</p>
            </article>
            <article className="tier-card">
              <h3>Tickets sold</h3>
              <strong>
                {sales.reduce((sum, row) => sum + Number(row.tickets), 0)}
              </strong>
              <p>Confirmed bookings · all time</p>
            </article>
            <article className="tier-card">
              <h3>Revenue</h3>
              <strong>
                {money(
                  sales.reduce(
                    (sum, row) => sum + Number(row.revenue_cents),
                    0,
                  ),
                )}
              </strong>
              <p>Confirmed payments · all time</p>
            </article>
          </div>
          <h2 className="section">Sales by ticket tier</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tier</th>
                  <th>Tickets</th>
                  <th>Guests</th>
                  <th>Revenue</th>
                </tr>
              </thead>
              <tbody>
                {sales.map((s, i) => (
                  <tr key={i}>
                    <td>{s.tier_name}</td>
                    <td>{s.tickets}</td>
                    <td>{s.guests}</td>
                    <td>{money(s.revenue_cents, s.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h2 className="section">Ride usage today</h2>
          <div className="history-list">
            {activity?.rides.map((r, i) => (
              <article className="panel" key={i}>
                <h3>{r.attraction_name}</h3>
                <p>
                  {r.riders} riders · {r.ride_events} recorded events
                </p>
              </article>
            ))}
          </div>
          <p className="muted">
            These are operational totals. Metabase reporting dashboards will be
            added in the analytics phase.
          </p>
        </>
      )}
      {tab === "attractions" && (
        <div className="booking-layout">
          <form className="panel booking-form" onSubmit={saveAttraction}>
            <h2>{editId ? "Edit attraction" : "Create attraction"}</h2>
            <label>
              Name
              <input
                required
                minLength={2}
                maxLength={120}
                value={a.name}
                onChange={(e) => setA({ ...a, name: e.target.value })}
              />
            </label>
            <label>
              Description
              <textarea
                required
                minLength={10}
                maxLength={2000}
                value={a.description}
                onChange={(e) => setA({ ...a, description: e.target.value })}
              />
            </label>
            <label>
              Category
              <input
                required
                value={a.category}
                onChange={(e) => setA({ ...a, category: e.target.value })}
              />
            </label>
            <label>
              Thrill level
              <select
                value={a.thrill_level}
                onChange={(e) =>
                  setA({
                    ...a,
                    thrill_level: e.target
                      .value as EditAttraction["thrill_level"],
                  })
                }
              >
                {["gentle", "moderate", "high"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Minimum age guidance
              <input
                type="number"
                min={0}
                max={120}
                value={a.minimum_age}
                onChange={(e) =>
                  setA({ ...a, minimum_age: Number(e.target.value) })
                }
              />
            </label>
            <label>
              Minimum height guidance (cm)
              <input
                type="number"
                min={0}
                max={250}
                value={a.minimum_height_cm}
                onChange={(e) =>
                  setA({ ...a, minimum_height_cm: Number(e.target.value) })
                }
              />
            </label>
            <label>
              Status
              <select
                value={a.operational_status}
                onChange={(e) =>
                  setA({
                    ...a,
                    operational_status: e.target
                      .value as EditAttraction["operational_status"],
                  })
                }
              >
                {["open", "maintenance", "retired"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <button className="primary" disabled={busy}>
              Save attraction
            </button>
            <button
              type="button"
              className="text-button"
              onClick={() => {
                setEditId("");
                setA(emptyAttraction);
              }}
            >
              Clear form
            </button>
          </form>
          <div className="history-list">
            {attractions.map((row) => (
              <article className="panel" key={row.id}>
                <h3>{row.name}</h3>
                <p>
                  {row.operational_status} · {row.category}
                </p>
                <div className="button-row">
                  <button
                    className="secondary"
                    onClick={() => pickAttraction(row)}
                  >
                    Edit
                  </button>
                  {row.operational_status !== "retired" && (
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() =>
                        void action(
                          () =>
                            api(
                              "/api/attractions/attractions/" + row.id,
                              token,
                              { method: "DELETE" },
                            ),
                          "Attraction retired; history preserved.",
                        )
                      }
                    >
                      Retire
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </div>
      )}
      {tab === "pricing" && (
        <div className="booking-layout">
          <form className="panel booking-form" onSubmit={saveTier}>
            <h2>{tierId ? "Edit ticket tier" : "Create ticket tier"}</h2>
            <label>
              Tier name
              <input
                required
                minLength={2}
                maxLength={80}
                value={t.name}
                onChange={(e) => setT({ ...t, name: e.target.value })}
              />
            </label>
            <label>
              Minimum guests
              <input
                type="number"
                min={1}
                max={5}
                required
                value={t.min_guests}
                onChange={(e) =>
                  setT({ ...t, min_guests: Number(e.target.value) })
                }
              />
            </label>
            <label>
              Maximum guests
              <input
                type="number"
                min={t.min_guests}
                max={5}
                required
                value={t.max_guests}
                onChange={(e) =>
                  setT({ ...t, max_guests: Number(e.target.value) })
                }
              />
            </label>
            <label>
              Price (USD)
              <input
                type="number"
                min={0.01}
                max={100000}
                step={0.01}
                required
                value={t.price_cents / 100}
                onChange={(e) =>
                  setT({
                    ...t,
                    price_cents: Math.round(Number(e.target.value) * 100),
                  })
                }
              />
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={t.active}
                onChange={(e) => setT({ ...t, active: e.target.checked })}
              />
              Available for new bookings
            </label>
            <button className="primary" disabled={busy}>
              Save ticket tier
            </button>
            <button
              type="button"
              className="text-button"
              onClick={() => {
                setTierId("");
                setT(emptyTier);
              }}
            >
              Clear form
            </button>
          </form>
          <div className="history-list">
            {tiers.map((row) => (
              <article className="panel" key={row.id}>
                <h3>
                  {row.name} · {money(row.price_cents)}
                </h3>
                <p>
                  {row.min_guests}–{row.max_guests} guests ·{" "}
                  {row.active ? "Available" : "Inactive"}
                </p>
                <button
                  className="secondary"
                  onClick={() => {
                    setTierId(row.id);
                    setT({
                      name: row.name,
                      min_guests: row.min_guests,
                      max_guests: row.max_guests,
                      price_cents: row.price_cents,
                      active: row.active,
                    });
                  }}
                >
                  Edit tier
                </button>
              </article>
            ))}
          </div>
        </div>
      )}
      {tab === "gate" && (
        <>
          <form
            className="panel booking-form narrow"
            onSubmit={(e) => {
              e.preventDefault();
              void action(async () => {
                const p = await api<Preview>(
                  "/api/gate/admin/tickets/validate",
                  token,
                  {
                    method: "POST",
                    body: JSON.stringify({ ticket_token: scan }),
                  },
                );
                if (alive.current) {
                  setPreview(p);
                  setGuests(p.guest_count);
                }
              }, "Ticket verified. Review the party before admitting.");
            }}
          >
            <label>
              Scanned QR ticket content
              <textarea
                value={scan}
                onChange={(e) => {
                  setScan(e.target.value);
                  setPreview(null);
                }}
                required
                maxLength={8192}
                autoComplete="off"
              />
            </label>
            <button className="secondary" disabled={busy}>
              Validate ticket
            </button>
            {preview && (
              <div className="notice">
                {preview.reference} · {preview.visit_date} ·{" "}
                {preview.guest_count} guests ·{" "}
                {preview.already_checked_in
                  ? "Already checked in"
                  : "Ready for check-in"}
              </div>
            )}
            <label>
              Guests arriving
              <input
                type="number"
                min={1}
                max={5}
                value={guests}
                onChange={(e) => setGuests(Number(e.target.value))}
              />
            </label>
            <p className="muted">
              Admit the full booked party together. Tickets are valid only on
              the visit date.
            </p>
            <button
              type="button"
              className="primary"
              disabled={busy || !preview || preview.already_checked_in}
              onClick={() =>
                void action(async () => {
                  await api("/api/gate/admin/check-ins", token, {
                    method: "POST",
                    body: JSON.stringify({
                      ticket_token: scan,
                      guest_count: guests,
                    }),
                  });
                  if (alive.current) {
                    setScan("");
                    setPreview(null);
                  }
                }, "Arrival recorded. Repeat scans will be rejected.")
              }
            >
              Register arrival
            </button>
          </form>
          <h2>Today's arrivals</h2>
          <div className="history-list">
            {activity?.arrivals.map((v) => (
              <article className="panel" key={v.booking_reference}>
                <code>{v.booking_reference}</code>
                <p>
                  {v.guest_count} guests ·{" "}
                  {new Date(v.checked_in_at).toLocaleTimeString("en-GB", {
                    timeZone: "Asia/Colombo",
                  })}
                </p>
              </article>
            ))}
          </div>
        </>
      )}
      {tab === "rides" && (
        <form
          className="panel booking-form narrow"
          onSubmit={(e) => {
            e.preventDefault();
            void action(async () => {
              await api("/api/gate/admin/ride-events", token, {
                method: "POST",
                body: JSON.stringify({
                  event_id: rideId.current,
                  booking_reference: rideRef,
                  attraction_id: rideAttraction,
                  guest_count: riders,
                }),
              });
              if (alive.current) {
                rideId.current = crypto.randomUUID();
                setRideRef("");
              }
            }, "Ride usage recorded.");
          }}
        >
          <label>
            Checked-in booking reference
            <input
              value={rideRef}
              onChange={(e) => {
                setRideRef(e.target.value.trim());
                rideId.current = crypto.randomUUID();
              }}
              pattern="WL-[A-F0-9]{32}"
              required
            />
          </label>
          <label>
            Attraction
            <select
              required
              value={rideAttraction}
              onChange={(e) => {
                setRideAttraction(e.target.value);
                rideId.current = crypto.randomUUID();
              }}
            >
              <option value="">Choose an open attraction</option>
              {attractions
                .filter((a) => a.operational_status === "open")
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Guests riding
            <input
              type="number"
              min={1}
              max={5}
              required
              value={riders}
              onChange={(e) => {
                setRiders(Number(e.target.value));
                rideId.current = crypto.randomUUID();
              }}
            />
          </label>
          <p className="muted">
            The booking must be checked in today. Attraction status is verified
            before recording.
          </p>
          <button className="primary" disabled={busy}>
            Record ride usage
          </button>
        </form>
      )}
    </section>
  );
}
