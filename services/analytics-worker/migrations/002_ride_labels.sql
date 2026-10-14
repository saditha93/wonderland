ALTER TABLE reporting.rides ADD COLUMN attraction_name text;
CREATE OR REPLACE VIEW reporting.popular_attractions AS
 SELECT attraction_id,sum(guest_count)::bigint AS riders,count(*) AS ride_events,
 coalesce((array_agg(attraction_name ORDER BY occurred_at DESC,event_id DESC) FILTER(WHERE attraction_name IS NOT NULL))[1],attraction_id::text) AS attraction_name
 FROM reporting.rides GROUP BY attraction_id;
