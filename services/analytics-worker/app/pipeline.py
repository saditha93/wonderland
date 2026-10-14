"""Transactional PostgreSQL local transport, at-least-once delivery and fact dedupe.

Queue row locks are the visibility lease: process death rolls the transaction back.
No guest identities or ticket/payment credentials belong in the event envelope.
"""

import hashlib
import json
from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    AwareDatetime,
    StrictInt,
    ValidationError,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_reference: str = Field(pattern=r"^WL-[A-F0-9]{32}$")
    guest_count: StrictInt = Field(ge=1, le=5)


class Purchase(Payload):
    tier_id: UUID
    tier_name: str = Field(min_length=1, max_length=120)
    amount_cents: StrictInt = Field(gt=0, le=2147483647)
    currency: Literal["USD"]


class Arrival(Payload):
    visit_date: date


class Ride(Payload):
    attraction_id: UUID
    attraction_name: str | None = Field(default=None, min_length=1, max_length=120)


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    event_id: str = Field(min_length=1, max_length=100)
    event_type: Literal["ticket.purchased", "visitor.arrived", "ride.used"]
    occurred_at: AwareDatetime
    payload: dict


MODELS = {"ticket.purchased": Purchase, "visitor.arrived": Arrival, "ride.used": Ride}
TABLES = {
    "ticket.purchased": "purchases",
    "visitor.arrived": "arrivals",
    "ride.used": "rides",
}


def publish(engine, limit=100):
    """Local queue send and outbox acknowledgment share a single DB transaction.

    Fixed schema allowlist; SKIP LOCKED allows multiple publisher processes.
    """
    published = 0
    for schema in ("booking", "visits"):
        with engine.begin() as conn:
            rows = (
                conn.execute(
                    text(
                        f"SELECT event_id,event_type,occurred_at,payload FROM {schema}.outbox WHERE published_at IS NULL ORDER BY occurred_at,event_id LIMIT :limit FOR UPDATE SKIP LOCKED"
                    ),
                    {"limit": limit},
                )
                .mappings()
                .all()
            )
            for row in rows:
                envelope = {
                    "version": 1,
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "occurred_at": row["occurred_at"].isoformat(),
                    "payload": row["payload"],
                }
                conn.execute(
                    text(
                        "INSERT INTO reporting.queue(event_id,envelope) VALUES (:id,CAST(:body AS jsonb)) ON CONFLICT DO NOTHING"
                    ),
                    {"id": row["event_id"], "body": json.dumps(envelope)},
                )
                conn.execute(
                    text(
                        f"UPDATE {schema}.outbox SET published_at=now() WHERE event_id=:id"
                    ),
                    {"id": row["event_id"]},
                )
                published += 1
    return published


def project(conn, raw):
    event = Envelope.model_validate(raw)
    payload = MODELS[event.event_type].model_validate(event.payload)
    normalized = event.model_dump(mode="json")
    normalized["payload"] = payload.model_dump(mode="json")
    fingerprint = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    inserted = conn.execute(
        text(
            "INSERT INTO reporting.processed_events(event_id,payload_hash) VALUES (:id,:hash) ON CONFLICT DO NOTHING RETURNING event_id"
        ),
        {"id": event.event_id, "hash": fingerprint},
    ).scalar()
    if not inserted:
        previous = conn.execute(
            text(
                "SELECT payload_hash FROM reporting.processed_events WHERE event_id=:id"
            ),
            {"id": event.event_id},
        ).scalar()
        if previous != fingerprint:
            raise ValueError("event_id_conflict")
        return False
    values = payload.model_dump()
    values.update(event_id=event.event_id, occurred_at=event.occurred_at)
    table = TABLES[event.event_type]
    columns = ",".join(values)
    placeholders = ",".join(":" + k for k in values)
    conn.execute(
        text(f"INSERT INTO reporting.{table}({columns}) VALUES ({placeholders})"),
        values,
    )
    return True


def consume_one(engine, max_attempts=3):
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT event_id,envelope,attempts FROM reporting.queue WHERE status='pending' AND available_at<=now() ORDER BY enqueued_at,event_id LIMIT 1 FOR UPDATE SKIP LOCKED"
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return False
        attempts = row["attempts"] + 1
        try:
            # Savepoint removes partial dedupe/fact writes while preserving retry bookkeeping.
            with conn.begin_nested():
                event = Envelope.model_validate(row["envelope"])
                if event.event_id != row["event_id"]:
                    raise ValueError("envelope_id_mismatch")
                project(conn, row["envelope"])
        except (ValidationError, ValueError, IntegrityError) as exc:
            code = (
                "invalid_event"
                if isinstance(exc, ValidationError)
                else ("fact_conflict" if isinstance(exc, IntegrityError) else str(exc))
            )
            if code not in {
                "invalid_event",
                "fact_conflict",
                "event_id_conflict",
                "envelope_id_mismatch",
            }:
                code = "invalid_event"
            conn.execute(
                text(
                    "UPDATE reporting.queue SET attempts=:attempts,status=:status,failure_code=:code,available_at=now()+(:delay * interval '1 second') WHERE event_id=:id"
                ),
                {
                    "id": row["event_id"],
                    "attempts": attempts,
                    "status": "dead" if attempts >= max_attempts else "pending",
                    "code": code,
                    "delay": min(300, 2**attempts),
                },
            )
        else:
            conn.execute(
                text(
                    "UPDATE reporting.queue SET status='done',attempts=:attempts,completed_at=now(),failure_code=NULL WHERE event_id=:id"
                ),
                {"id": row["event_id"], "attempts": attempts},
            )
    return True


def tick(engine):
    count = publish(engine)
    consumed = 0
    for _ in range(100):
        if not consume_one(engine):
            break
        consumed += 1
    return count, consumed
