"""Real PostgreSQL crash, replay, concurrency, metric and authorization checks."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
from conftest import load_service


@pytest.fixture
def analytics(domain):
    module = load_service("analytics-worker")
    with TestClient(module.app) as client:
        yield domain, module, client
    module.app.state.engine.dispose()


def envelope(
    kind="visitor.arrived", n=1, guests=4, instant="2026-10-13T04:30:00+00:00"
):
    payload = {"booking_reference": "WL-" + f"{n:032X}", "guest_count": guests}
    if kind == "ticket.purchased":
        payload.update(
            tier_id=str(UUID(int=3)),
            tier_name="Family",
            amount_cents=14000,
            currency="USD",
        )
    elif kind == "ride.used":
        payload.update(
            attraction_id=str(UUID(int=101)), attraction_name="Skyline Coaster"
        )
    else:
        payload.update(visit_date="2026-10-13")
    return {
        "version": 1,
        "event_id": f"{kind}:{n}",
        "event_type": kind,
        "occurred_at": instant,
        "payload": payload,
    }


def queue(engine, event):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO reporting.queue(event_id,envelope) VALUES (:id,CAST(:body AS jsonb))"
            ),
            {"id": event["event_id"], "body": json.dumps(event)},
        )


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def test_fact_replay_and_conflicting_id(analytics):
    d, m, c = analytics
    e = d["engine"]
    event = envelope()
    with e.begin() as conn:
        from importlib import import_module

        project = import_module(m.__package__ + ".pipeline").project
        assert project(conn, event)
        assert not project(conn, event)
    changed = json.loads(json.dumps(event))
    changed["payload"]["guest_count"] = 3
    with pytest.raises(ValueError, match="event_id_conflict"), e.begin() as conn:
        project(conn, changed)
    assert scalar(e, "SELECT sum(guest_count) FROM reporting.arrivals") == 4


def test_crash_rolls_back_fact_and_queue_ack(analytics):
    d, m, c = analytics
    e = d["engine"]
    event = envelope()
    queue(e, event)
    from importlib import import_module

    p = import_module(m.__package__ + ".pipeline")
    with pytest.raises(RuntimeError), e.begin() as conn:
        conn.execute(
            text("SELECT * FROM reporting.queue WHERE status='pending' FOR UPDATE")
        )
        p.project(conn, event)
        conn.execute(text("UPDATE reporting.queue SET status='done'"))
        raise RuntimeError("simulated crash before commit")
    assert scalar(e, "SELECT count(*) FROM reporting.arrivals") == 0
    assert p.consume_one(e)
    assert scalar(e, "SELECT sum(guest_count) FROM reporting.arrivals") == 4
    assert not p.consume_one(e)


def test_concurrent_workers_count_once(analytics):
    d, m, c = analytics
    e = d["engine"]
    from importlib import import_module

    p = import_module(m.__package__ + ".pipeline")
    for n in range(1, 21):
        queue(e, envelope(n=n))

    def drain(_):
        while p.consume_one(e):
            pass

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(drain, range(6)))
    assert scalar(e, "SELECT count(*) FROM reporting.arrivals") == 20
    assert scalar(e, "SELECT sum(guest_count) FROM reporting.arrivals") == 80
    assert scalar(e, "SELECT count(*) FROM reporting.queue WHERE status='done'") == 20


def test_poison_retry_backoff_dead_letter_and_protected_redrive(analytics):
    d, m, c = analytics
    e = d["engine"]
    from importlib import import_module

    p = import_module(m.__package__ + ".pipeline")
    event = envelope()
    event["payload"]["guest_count"] = 99
    queue(e, event)
    assert p.consume_one(e)
    assert not p.consume_one(e)  # backed off
    for _ in range(2):
        with e.begin() as conn:
            conn.execute(text("UPDATE reporting.queue SET available_at=now()"))
        assert p.consume_one(e)
    assert scalar(e, "SELECT status FROM reporting.queue") == "dead"
    assert scalar(e, "SELECT count(*) FROM reporting.processed_events") == 0
    assert (
        c.post(
            "/admin/analytics/redrive/" + event["event_id"], headers=d["headers"]()
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/admin/analytics/redrive/" + event["event_id"],
            headers=d["headers"](role="admin"),
        ).status_code
        == 200
    )
    assert scalar(e, "SELECT attempts FROM reporting.queue") == 0


def test_metrics_money_timezone_zero_hours_and_ties(analytics):
    d, m, c = analytics
    e = d["engine"]
    for event in [
        envelope("ticket.purchased"),
        envelope(),
        envelope("ride.used", guests=2),
        envelope(n=2, guests=1, instant="2026-10-13T19:00:00+00:00"),
    ]:
        queue(e, event)
    m.tick(e)
    result = c.get("/admin/analytics", headers=d["headers"](role="admin"))
    assert result.status_code == 200
    data = result.json()
    arrivals = {r["day"]: r["arriving_guests"] for r in data["daily_arrivals"]}
    assert arrivals == {
        "2026-10-13": 4,
        "2026-10-14": 1,
    }  # 19:00 UTC is next day 00:30 Colombo
    assert data["tickets_by_tier"][0]["purchased_tickets"] == 1
    assert data["revenue_by_tier"][0]["revenue_cents"] == 14000
    assert data["popular_attractions"][0]["riders"] == 2
    assert data["popular_attractions"][0]["ride_events"] == 1
    hours = data["busiest_quiet_hours"]
    assert len(hours) == 9
    assert next(r for r in hours if r["hour"] == 10)["arriving_guests"] == 4
    assert len([r for r in hours if r["quietest_rank"] == 1]) == 8
    assert data["outside_hours_arrivals"][0]["arriving_guests"] == 1
    assert c.get("/admin/analytics", headers=d["headers"]()).status_code == 403
    assert c.get("/health/ready").status_code == 200


def test_local_publish_recovery_and_ack_atomicity(analytics, monkeypatch):
    d, m, c = analytics
    e = d["engine"]
    from importlib import import_module

    p = import_module(m.__package__ + ".pipeline")
    event = envelope()
    with e.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO visits.outbox(event_id,event_type,occurred_at,payload) VALUES (:id,:type,:at,CAST(:payload AS jsonb))"
            ),
            {
                "id": event["event_id"],
                "type": event["event_type"],
                "at": event["occurred_at"],
                "payload": json.dumps(event["payload"]),
            },
        )
    # Simulate a crash at transaction commit with a temporary trigger.
    with e.begin() as conn:
        conn.exec_driver_sql(
            "CREATE FUNCTION reporting.reject_publish() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'offline test'; END $$"
        )
        conn.exec_driver_sql(
            "CREATE TRIGGER test_reject_publish BEFORE UPDATE ON visits.outbox FOR EACH ROW EXECUTE FUNCTION reporting.reject_publish()"
        )
    try:
        from sqlalchemy.exc import SQLAlchemyError

        with pytest.raises(SQLAlchemyError):
            p.publish(e)
        assert scalar(e, "SELECT count(*) FROM reporting.queue") == 0
        assert (
            scalar(e, "SELECT count(*) FROM visits.outbox WHERE published_at IS NULL")
            == 1
        )
    finally:
        with e.begin() as conn:
            conn.exec_driver_sql("DROP TRIGGER test_reject_publish ON visits.outbox")
            conn.exec_driver_sql("DROP FUNCTION reporting.reject_publish()")
    assert p.publish(e) == 1
    assert p.publish(e) == 0
    assert p.consume_one(e)
    assert scalar(e, "SELECT sum(guest_count) FROM reporting.arrivals") == 4


def test_sqs_lost_delete_replays_without_double_count(analytics):
    d, m, c = analytics
    e = d["engine"]
    from importlib import import_module

    sqs = import_module(m.__package__ + ".sqs_transport")
    event = envelope()

    class Fake:
        fail = True

        def receive_message(self, **kwargs):
            return {
                "Messages": [{"Body": json.dumps(event), "ReceiptHandle": "offline"}]
            }

        def delete_message(self, **kwargs):
            if self.fail:
                raise ConnectionError("offline lost acknowledgment")

    client = Fake()
    transport = sqs.SqsTransport(client, "https://sqs.invalid/offline")
    with pytest.raises(ConnectionError):
        transport.consume(e)
    assert scalar(e, "SELECT count(*) FROM reporting.arrivals") == 1
    client.fail = False
    assert transport.consume(e) == 1
    assert scalar(e, "SELECT sum(guest_count) FROM reporting.arrivals") == 4


def test_reporting_and_bi_roles_are_isolated(analytics):
    d, m, c = analytics
    e = d["engine"]
    from scripts.db_migrate import grant_service_roles, grant_bi_login

    grant_service_roles(
        e,
        {
            schema: "a" * 48
            for schema in ("attractions", "booking", "visits", "reporting")
        },
    )
    grant_bi_login(e, "a" * 48)
    with e.begin() as conn:
        assert conn.execute(
            text(
                "SELECT has_table_privilege('wonderland_bi','reporting.daily_arrivals','SELECT')"
            )
        ).scalar()
        for role, table, privilege in [
            ("wonderland_bi", "reporting.queue", "SELECT"),
            ("wonderland_bi", "reporting.purchases", "INSERT"),
            ("wonderland_bi", "booking.bookings", "SELECT"),
            ("wonderland_reporting", "booking.bookings", "SELECT"),
            ("wonderland_booking", "reporting.queue", "INSERT"),
            ("wonderland_visits", "reporting.arrivals", "INSERT"),
        ]:
            assert not conn.execute(
                text("SELECT has_table_privilege(:role,:table,:privilege)"),
                {"role": role, "table": table, "privilege": privilege},
            ).scalar()
        assert not conn.execute(
            text(
                "SELECT has_column_privilege('wonderland_reporting','booking.outbox','payload','UPDATE')"
            )
        ).scalar()
        assert conn.execute(
            text(
                "SELECT has_column_privilege('wonderland_reporting','booking.outbox','published_at','UPDATE')"
            )
        ).scalar()
        conn.exec_driver_sql("SET LOCAL ROLE wonderland_bi")
        assert (
            conn.execute(text("SELECT count(*) FROM reporting.arrival_hours")).scalar()
            >= 9
        )


def test_sqs_publish_failure_leaves_outbox_replayable(analytics):
    d, m, c = analytics
    e = d["engine"]
    from importlib import import_module

    sqs = import_module(m.__package__ + ".sqs_transport")
    with e.begin() as conn:
        for n in (1, 2):
            event = envelope(n=n)
            conn.execute(
                text(
                    "INSERT INTO visits.outbox(event_id,event_type,occurred_at,payload) VALUES (:id,:type,:at,CAST(:body AS jsonb))"
                ),
                {
                    "id": event["event_id"],
                    "type": event["event_type"],
                    "at": event["occurred_at"],
                    "body": json.dumps(event["payload"]),
                },
            )

    class Fake:
        sent = []
        calls = 0

        def send_message(self, **kwargs):
            self.calls += 1
            if self.calls == 2:
                raise ConnectionError("offline lost send")
            self.sent.append(json.loads(kwargs["MessageBody"]))

    client = Fake()
    transport = sqs.SqsTransport(client, "https://sqs.invalid/offline")
    with pytest.raises(ConnectionError):
        transport.publish(e)
    assert (
        scalar(e, "SELECT count(*) FROM visits.outbox WHERE published_at IS NULL") == 2
    )
    assert transport.publish(e) == 2
    assert len(client.sent) == 3  # acknowledged remote send replays after DB rollback
    p = import_module(m.__package__ + ".pipeline")
    with e.begin() as conn:
        for event in client.sent:
            p.project(conn, event)
    assert scalar(e, "SELECT count(*) FROM reporting.arrivals") == 2


def test_invalid_fact_rolls_back_dedupe_and_reaches_dlq(analytics):
    d, m, c = analytics
    e = d["engine"]
    from importlib import import_module

    p = import_module(m.__package__ + ".pipeline")
    event = envelope()
    queue(e, event)
    assert p.consume_one(e)
    conflict = envelope(n=2)
    conflict["payload"]["booking_reference"] = event["payload"]["booking_reference"]
    queue(e, conflict)
    assert p.consume_one(e, max_attempts=1)
    assert scalar(e, "SELECT count(*) FROM reporting.processed_events") == 1
    assert scalar(e, "SELECT count(*) FROM reporting.queue WHERE status='dead'") == 1
    assert scalar(e, "SELECT sum(guest_count) FROM reporting.arrivals") == 4
