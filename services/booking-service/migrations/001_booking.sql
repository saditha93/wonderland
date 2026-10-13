CREATE TABLE booking.ticket_tiers (
 id uuid PRIMARY KEY,
 name varchar(80) NOT NULL UNIQUE,
 min_guests integer NOT NULL CHECK (min_guests >= 1),
 max_guests integer NOT NULL CHECK (max_guests >= min_guests AND max_guests <= 5),
 price_cents integer NOT NULL CHECK (price_cents > 0),
 currency varchar(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
 active boolean NOT NULL DEFAULT true,
 revision integer NOT NULL DEFAULT 1,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE booking.bookings (
 reference varchar(40) PRIMARY KEY,
 owner_id varchar(160) NOT NULL,
 tier_id uuid NOT NULL REFERENCES booking.ticket_tiers(id),
 tier_name varchar(80) NOT NULL,
 tier_revision integer NOT NULL,
 guest_count integer NOT NULL CHECK (guest_count BETWEEN 1 AND 5),
 visit_date date NOT NULL,
 time_slot varchar(5) NOT NULL CHECK (time_slot IN ('09:00','12:00','15:00')),
 amount_cents integer NOT NULL CHECK (amount_cents > 0),
 currency varchar(3) NOT NULL CHECK (currency = 'USD'),
 status varchar(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed')),
 payment_status varchar(20) NOT NULL DEFAULT 'unpaid' CHECK (payment_status IN ('unpaid','paid')),
 payment_provider varchar(10),
 payment_session_id varchar(200) UNIQUE,
 checkout_url text,
 idempotency_key varchar(80) NOT NULL,
 request_hash varchar(64) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 confirmed_at timestamptz,
 UNIQUE(owner_id,idempotency_key),
 CHECK ((status = 'confirmed') = (payment_status = 'paid'))
);
CREATE INDEX bookings_owner_history_idx ON booking.bookings(owner_id,created_at DESC);
CREATE TABLE booking.payment_events (
 provider varchar(10) NOT NULL,
 event_id varchar(200) NOT NULL,
 booking_reference varchar(40) NOT NULL REFERENCES booking.bookings(reference),
 payload_hash varchar(64) NOT NULL,
 processed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(provider,event_id)
);
CREATE TABLE booking.outbox (
 event_id varchar(100) PRIMARY KEY,
 event_type varchar(80) NOT NULL,
 booking_reference varchar(40) NOT NULL REFERENCES booking.bookings(reference),
 occurred_at timestamptz NOT NULL DEFAULT now(),
 payload jsonb NOT NULL,
 published_at timestamptz
);
