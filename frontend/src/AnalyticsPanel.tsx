import { useEffect, useState } from "react";
import { api, money } from "./api";
type Analytics = {
  daily_arrivals: {
    day: string;
    arriving_guests: number;
    arrival_bookings: number;
  }[];
  tickets_by_tier: {
    tier_id: string;
    tier_name: string;
    purchased_tickets: number;
    booked_guests: number;
  }[];
  revenue_by_tier: {
    tier_id: string;
    tier_name: string;
    revenue_cents: number;
    currency: string;
  }[];
  popular_attractions: {
    attraction_id: string;
    attraction_name: string;
    riders: number;
    ride_events: number;
  }[];
  busiest_quiet_hours: {
    hour: number;
    arriving_guests: number;
    busiest_rank: number;
    quietest_rank: number;
  }[];
  outside_hours_arrivals: { day: string; arriving_guests: number }[];

};
export function AnalyticsPanel({ token }: { token: string }) {
  const metabaseUrl =
    import.meta.env.VITE_METABASE_URL || "";
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<Analytics>("/api/analytics/admin/analytics", token)
      .then((value) => {
        if (active) setData(value);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, refresh]);
  return (
    <section aria-label="Park reports">
      <h2>Visitor and sales reports</h2>
      <p className="muted">
        Reports update shortly after each payment, check-in or ride.
        Dates use Sri Lanka time. Hourly reports cover 09:00–18:00.
      </p>
      <div className="button-row">
        <button
          className="secondary"
          disabled={loading}
          onClick={() => setRefresh((v) => v + 1)}
        >
          {loading ? "Loading reports…" : "Refresh reports"}
        </button>
        {metabaseUrl && (
          <a
            className="text-button"
            href={metabaseUrl}
            target="_blank"
            rel="noreferrer"
          >
            Open Metabase
          </a>
        )}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {data && (
        <>
          <h3>Daily visitor arrivals</h3>
          {data.daily_arrivals.length === 0 && (
            <p>No visitors have checked in yet.</p>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Guests</th>
                  <th>Bookings arriving</th>
                </tr>
              </thead>
              <tbody>
                {data.daily_arrivals.map((r) => (
                  <tr key={r.day}>
                    <td>{r.day}</td>
                    <td>{r.arriving_guests}</td>
                    <td>{r.arrival_bookings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Purchased tickets by tier</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tier</th>
                  <th>Tickets (bookings)</th>
                  <th>Booked guests</th>
                </tr>
              </thead>
              <tbody>
                {data.tickets_by_tier.map((r) => (
                  <tr key={r.tier_id}>
                    <td>{r.tier_name}</td>
                    <td>{r.purchased_tickets}</td>
                    <td>{r.booked_guests}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Revenue by tier</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tier</th>
                  <th>Confirmed revenue</th>
                </tr>
              </thead>
              <tbody>
                {data.revenue_by_tier.map((r) => (
                  <tr key={r.tier_id + r.currency}>
                    <td>{r.tier_name}</td>
                    <td>{money(r.revenue_cents, r.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Most popular attractions</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Attraction</th>
                  <th>Riders</th>
                  <th>Rides recorded</th>
                </tr>
              </thead>
              <tbody>
                {data.popular_attractions.map((r) => (
                  <tr key={r.attraction_id}>
                    <td>{r.attraction_name}</td>
                    <td>{r.riders}</td>
                    <td>{r.ride_events}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Busiest and quietest opening hours</h3>
          <p className="muted">
            Guest arrivals across the reporting period, with zero-activity hours
            included. Equal counts share ranks.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Hour</th>
                  <th>Guests</th>
                  <th>Activity</th>
                </tr>
              </thead>
              <tbody>
                {data.busiest_quiet_hours.map((r) => (
                  <tr key={r.hour}>
                    <td>{String(r.hour).padStart(2, "0")}:00</td>
                    <td>{r.arriving_guests}</td>
                    <td>
                      {[
                        r.busiest_rank === 1 && "Busiest",
                        r.quietest_rank === 1 && "Quietest",
                      ]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.outside_hours_arrivals.length > 0 && (
            <p className="notice">
              {data.outside_hours_arrivals.reduce(
                (sum, r) => sum + Number(r.arriving_guests),
                0,
              )}{" "}
              arrivals occurred outside opening hours. They are
              included in daily totals.
            </p>
          )}
        </>
      )}
    </section>
  );
}
