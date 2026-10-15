# Metabase: assignment demonstration

The assignment requires stored, timestamped purchases, arrivals and ride activity connected to a visualization platform. This project uses Metabase with a read-only PostgreSQL reporting connection. You do not need to enter SQL or configure the database manually: the launcher provisions and verifies the dashboard.

## 1. Run the app

In Terminal 1, from the project folder:

```bash
./start.sh
```

If the visitor/admin apps are already running, keep their existing terminal open.

## 2. Start Metabase

Open Terminal 2 in the same project folder:

```bash
./start.sh monitoring
```

Keep it open. The command starts Metabase, waits for readiness, creates/reuses the dashboard and runs all seven saved SQL queries against real reporting data. It prints your dashboard URL and private Metabase login details in an interactive terminal. Existing metadata, dashboard IDs and credentials are preserved.

This Mac already has Java 21 and the pinned Metabase JAR. On a fresh machine, use the Java/JAR preparation in [the detailed guide](phase-4-outcome.md).

## 3. Open the dashboard

Open the URL printed by the command, normally http://localhost:3000/dashboard/2 on this existing installation.

Sign in using the email/password from the monitoring terminal, or private `secrets/metabase.json`. Metabase has its own account: visitor/admin app passwords do not log into it. Do not show passwords in screenshots.

The dashboard is named **Wonderland — stored event analytics**. It contains:

| Chart | What to explain |
|---|---|
| Daily visitor arrivals | Actual guests admitted each day, counted from check-in events |
| Purchased tickets by tier | Confirmed booking/ticket counts grouped by tier |
| Revenue by tier | Confirmed revenue, labelled in USD cents; divide by 100 for dollars |
| Most popular attractions | Actual riders recorded for each attraction |
| Busiest and quietest hours | Arriving guests grouped into the operating-hour buckets |
| Daily arrivals by opening hour | Supporting table with zero-activity hours included |
| Arrivals outside opening hours | Supporting table explaining admissions made outside the hourly window |

These charts use stored reporting facts; they are not hard-coded sample graphs. All local activity is demo/test data, not real park statistics.

## 4. Demonstrate a live change

1. In the visitor app on **5173**, sign in, book **Family / 4 guests / today** and confirm the demo payment.
2. In the admin app on **5174**, check in that booking for **4 guests**.
3. Record **2 riders** at an open attraction.
4. Wait a few seconds for processing, then refresh the **Metabase dashboard**.
5. Show the changes: purchased bookings **+1**, revenue **+the booking's stored total**, daily arrivals **+4**, and attraction riders **+2**.
6. Repeat check-in for the same reference. It should be rejected; arrivals must not increase again.
7. Compare the figures with admin **Reports**. Remember that Metabase revenue is in cents while the app formats dollars.

Arrival timestamps use Sri Lanka time. The hourly report covers **09:00–18:00**. A demonstration before 09:00 or after 18:00 increases daily arrivals and the outside-hours table, while operating-hour bars can remain zero. Explain this accurately; do not invent arrivals at another time to make a chart look busy.

## 5. Check the data automatically

While the app is running, this optional command reconciles operational records and reporting totals:

```bash
.venv/bin/python scripts/smoke-phase4.py
```

The monitoring launcher itself has already verified that all seven saved Metabase queries execute successfully. This reconciliation additionally checks that reporting totals match their source purchases, arrivals and rides.

## 6. Evidence for the report/viva

Capture the dashboard title, database connection name **Wonderland reporting** (hide connection secrets), the five main charts, and a before/after dashboard comparison for the same new booking. Note the time, tier, booking total and number of guests/riders in your private demonstration notes. Keep readable ticket payloads and passwords out of submitted screenshots.

Explain the data path:

**Booking/check-in/ride → stored event → analytics worker → reporting views → Metabase charts.**

This is business activity monitoring. Pod health and CPU autoscaling are shown by the separate local infrastructure tests; Metabase is not being used as a Kubernetes infrastructure monitor.

## 7. Stop

Press Ctrl-C in Terminal 2 to stop Metabase. Its dashboard/login metadata stays saved. The visitor/admin apps continue running until you stop Terminal 1.

This native dashboard reads the native database used by ports 5173/5174. Kubernetes activity on ports 5180/5181 uses a separate database and does not appear here automatically.
