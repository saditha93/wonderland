CREATE TABLE attractions.attractions (
 id uuid PRIMARY KEY,
 name varchar(120) NOT NULL,
 description varchar(2000) NOT NULL,
 category varchar(80) NOT NULL,
 thrill_level varchar(20) NOT NULL CHECK (thrill_level IN ('gentle','moderate','high')),
 minimum_age integer NOT NULL CHECK (minimum_age BETWEEN 0 AND 120),
 minimum_height_cm integer NOT NULL CHECK (minimum_height_cm BETWEEN 0 AND 250),
 operational_status varchar(20) NOT NULL CHECK (operational_status IN ('open','maintenance','retired')),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX attractions_status_idx ON attractions.attractions(operational_status);
