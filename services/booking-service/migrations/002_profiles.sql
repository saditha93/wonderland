CREATE TABLE booking.visitor_profiles (
 owner_id varchar(160) PRIMARY KEY,
 display_name varchar(80) NOT NULL,
 preferred_language varchar(2) NOT NULL DEFAULT 'en' CHECK (preferred_language IN ('en','si','ta')),
 updated_at timestamptz NOT NULL DEFAULT now()
);
