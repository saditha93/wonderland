"""Dependency-injected SQS adapter. No SDK/session/network is created on import.

Future cloud runtime must supply an IAM-scoped client and queues with a redrive
policy. Default local runtime uses transactional PostgreSQL instead.
"""

import json
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from .pipeline import Envelope
from sqlalchemy import text
from .pipeline import project


class SqsTransport:
    def __init__(self, client, queue_url):
        self.client, self.queue_url = client, queue_url

    def send(self, envelope):
        body = json.dumps(envelope, separators=(",", ":"))
        if len(body.encode()) > 256_000:
            raise ValueError("Event exceeds conservative SQS payload limit")
        self.client.send_message(QueueUrl=self.queue_url, MessageBody=body)

    def consume(self, engine):
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=1,
            VisibilityTimeout=60,
        )
        completed = 0
        for message in response.get("Messages", []):
            # Database commit precedes delete. A lost delete or process crash replays safely.
            try:
                raw = json.loads(message["Body"])
                Envelope.model_validate(raw)
                with engine.begin() as conn:
                    project(conn, raw)
            except (ValueError, ValidationError, IntegrityError):
                # Leave poison messages unacknowledged for configured visibility retry/DLQ.
                # Continue the batch so one poison message cannot starve valid messages.
                continue
            self.client.delete_message(
                QueueUrl=self.queue_url, ReceiptHandle=message["ReceiptHandle"]
            )
            completed += 1
        return completed

    def publish(self, engine, limit=100):
        sent = 0
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
                    self.send(
                        {
                            "version": 1,
                            "event_id": row["event_id"],
                            "event_type": row["event_type"],
                            "occurred_at": row["occurred_at"].isoformat(),
                            "payload": row["payload"],
                        }
                    )
                    # Remote send may succeed before this transaction commits. Replay is expected.
                    conn.execute(
                        text(
                            f"UPDATE {schema}.outbox SET published_at=now() WHERE event_id=:id"
                        ),
                        {"id": row["event_id"]},
                    )
                    sent += 1
        return sent
