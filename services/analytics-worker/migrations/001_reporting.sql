CREATE TABLE reporting.queue (
 event_id varchar(100) PRIMARY KEY, envelope jsonb NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done','dead')),
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 enqueued_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
 failure_code text
);
CREATE INDEX queue_pending ON reporting.queue(available_at,enqueued_at) WHERE status='pending';
CREATE TABLE reporting.processed_events(event_id varchar(100) PRIMARY KEY, payload_hash char(64) NOT NULL, processed_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE reporting.purchases(event_id varchar(100) PRIMARY KEY REFERENCES reporting.processed_events,
 booking_reference varchar(40) UNIQUE NOT NULL, occurred_at timestamptz NOT NULL,
 tier_id uuid NOT NULL,tier_name text NOT NULL,guest_count integer NOT NULL CHECK(guest_count BETWEEN 1 AND 5),
 amount_cents integer NOT NULL CHECK(amount_cents>0),currency char(3) NOT NULL CHECK(currency='USD'));
CREATE TABLE reporting.arrivals(event_id varchar(100) PRIMARY KEY REFERENCES reporting.processed_events,
 booking_reference varchar(40) UNIQUE NOT NULL, occurred_at timestamptz NOT NULL,
 guest_count integer NOT NULL CHECK(guest_count BETWEEN 1 AND 5),visit_date date NOT NULL);
CREATE TABLE reporting.rides(event_id varchar(100) PRIMARY KEY REFERENCES reporting.processed_events,
 booking_reference varchar(40) NOT NULL,occurred_at timestamptz NOT NULL,
 attraction_id uuid NOT NULL,guest_count integer NOT NULL CHECK(guest_count BETWEEN 1 AND 5));
CREATE INDEX purchases_time ON reporting.purchases(occurred_at);
CREATE INDEX arrivals_time ON reporting.arrivals(occurred_at);
CREATE INDEX rides_time ON reporting.rides(occurred_at);
-- All dates/hours use park time. Purchases are bookings, not individual guests.
CREATE VIEW reporting.daily_arrivals AS
 SELECT (occurred_at AT TIME ZONE 'Asia/Colombo')::date AS day,sum(guest_count)::bigint AS arriving_guests,count(*) AS arrival_bookings FROM reporting.arrivals GROUP BY 1;
CREATE VIEW reporting.tickets_by_tier AS
 SELECT tier_id,(array_agg(tier_name ORDER BY occurred_at DESC,event_id DESC))[1] AS tier_name,count(*) AS purchased_tickets,sum(guest_count)::bigint AS booked_guests FROM reporting.purchases GROUP BY tier_id;
CREATE VIEW reporting.revenue_by_tier AS
 SELECT tier_id,(array_agg(tier_name ORDER BY occurred_at DESC,event_id DESC))[1] AS tier_name,currency,sum(amount_cents)::bigint AS revenue_cents FROM reporting.purchases GROUP BY tier_id,currency;
CREATE VIEW reporting.popular_attractions AS
 SELECT attraction_id,sum(guest_count)::bigint AS riders,count(*) AS ride_events FROM reporting.rides GROUP BY attraction_id;
-- Provisional park hours 09:00 inclusive to 18:00 exclusive; every calendar date between first arrival and today.
CREATE VIEW reporting.arrival_hours AS
 WITH days AS (SELECT generate_series(COALESCE((SELECT min(day) FROM reporting.daily_arrivals),(now() AT TIME ZONE 'Asia/Colombo')::date)::timestamp,
 GREATEST(COALESCE((SELECT max(day) FROM reporting.daily_arrivals),(now() AT TIME ZONE 'Asia/Colombo')::date),(now() AT TIME ZONE 'Asia/Colombo')::date)::timestamp, interval '1 day')::date AS day),
 counts AS (SELECT (occurred_at AT TIME ZONE 'Asia/Colombo')::date AS day,extract(hour FROM occurred_at AT TIME ZONE 'Asia/Colombo')::integer AS hour,sum(guest_count)::bigint AS guests FROM reporting.arrivals GROUP BY 1,2)
 SELECT days.day,h.hour,coalesce(c.guests,0)::bigint AS arriving_guests FROM days CROSS JOIN generate_series(9,17) h(hour) LEFT JOIN counts c ON c.day=days.day AND c.hour=h.hour;
CREATE VIEW reporting.busiest_quiet_hours AS
 WITH totals AS (SELECT hour,sum(arriving_guests)::bigint AS arriving_guests FROM reporting.arrival_hours GROUP BY hour)
 SELECT *,dense_rank() OVER(ORDER BY arriving_guests DESC) AS busiest_rank,dense_rank() OVER(ORDER BY arriving_guests ASC) AS quietest_rank FROM totals;
CREATE VIEW reporting.outside_hours_arrivals AS
 SELECT (occurred_at AT TIME ZONE 'Asia/Colombo')::date AS day,sum(guest_count)::bigint AS arriving_guests FROM reporting.arrivals WHERE extract(hour FROM occurred_at AT TIME ZONE 'Asia/Colombo') NOT BETWEEN 9 AND 17 GROUP BY 1;
