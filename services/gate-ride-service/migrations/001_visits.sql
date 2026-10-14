CREATE TABLE visits.check_ins (
 booking_reference varchar(40) PRIMARY KEY,
 owner_tag char(64) NOT NULL,
 guest_count integer NOT NULL CHECK (guest_count BETWEEN 1 AND 5),
 visit_date date NOT NULL,
 checked_in_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX visits_owner_idx ON visits.check_ins(owner_tag,checked_in_at DESC);
CREATE TABLE visits.ride_events (
 event_id uuid PRIMARY KEY,
 booking_reference varchar(40) NOT NULL REFERENCES visits.check_ins(booking_reference),
 attraction_id uuid NOT NULL,
 attraction_name varchar(120) NOT NULL,
 guest_count integer NOT NULL CHECK (guest_count BETWEEN 1 AND 5),
 request_hash char(64) NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ride_activity_idx ON visits.ride_events(occurred_at,attraction_id);
CREATE TABLE visits.outbox (
 event_id varchar(100) PRIMARY KEY,
 event_type varchar(80) NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now(),
 payload jsonb NOT NULL,
 published_at timestamptz
);
