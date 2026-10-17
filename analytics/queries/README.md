# Stored-event reporting SQL

These seven queries read aggregate views in the owned `reporting` schema. `analytics/dashboard.json` provisions the five mandatory metrics plus daily zero-filled hours and outside-hours arrivals into Metabase. Run `scripts/provision-metabase.py` against the local Metabase instance; it verifies every question through the real API. Charts contain persisted purchase/arrival/ride facts, including labelled local simulator scenarios, rather than hardcoded values.

Asia/Colombo applies to actual event instants; provisional hours are 09:00–18:00. Tickets count confirmed bookings, arrivals/popularity count guests, revenue is integer USD cents. Equal hourly totals share ranks; zeros are retained. Latest event snapshot labels are grouped by stable IDs. Reports currently use all stored history. See [reporting and resilience](../../docs/assignment/report.md#4-reporting-and-resilience).
