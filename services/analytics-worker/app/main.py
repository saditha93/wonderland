"""Protected reporting API plus independently pausable local pipeline."""

from contextlib import asynccontextmanager
from threading import Event, Thread
from time import monotonic
from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from botocore.exceptions import BotoCoreError, ClientError
from .sqs_transport import SqsTransport
from wonderland_common.web import create_app, SAFE_REQUEST_ID
from wonderland_common.auth import administrator
from .pipeline import tick

app = create_app("analytics-worker", "reporting", revision=2)
settings = app.state.settings
logger = app.state.logger


@asynccontextmanager
async def lifespan(app):
    stop = Event()
    transport = None
    if settings.analytics_enabled and settings.analytics_transport == "sqs":
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "sqs",
            region_name=settings.aws_region,
            config=Config(
                connect_timeout=3,
                read_timeout=5,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )
        app.state.sqs_client = client
        transport = SqsTransport(client, settings.sqs_queue_url)

    def run():
        while not stop.is_set():
            try:
                if transport:
                    transport.publish(app.state.engine, limit=25)
                    for _ in range(5):
                        if transport.consume(app.state.engine) == 0:
                            break
                else:
                    tick(app.state.engine)
                app.state.pipeline_last_success = monotonic()
            except (SQLAlchemyError, BotoCoreError, ClientError):
                logger.warning(
                    '{"event":"pipeline_retry","reason":"dependency_unavailable"}'
                )
            stop.wait(1)

    worker = None
    if settings.analytics_enabled and app.state.engine is not None:
        worker = Thread(target=run, daemon=True, name="analytics-pipeline")
        app.state.pipeline_thread = worker
        worker.start()
    yield
    stop.set()
    if worker:
        worker.join(timeout=10)


app.router.lifespan_context = lifespan


def check_pipeline():
    if settings.analytics_enabled and not getattr(app.state, "pipeline_thread", None):
        raise ValueError("Pipeline not started")
    thread = getattr(app.state, "pipeline_thread", None)
    if settings.analytics_enabled and not thread.is_alive():
        raise ValueError("Pipeline thread stopped")
    if (
        settings.analytics_enabled
        and settings.analytics_transport == "sqs"
        and monotonic() - getattr(app.state, "pipeline_last_success", 0) > 30
    ):
        raise ValueError("Queue pipeline has not completed a recent successful cycle")
    with app.state.engine.connect() as conn:
        conn.execute(text("SELECT event_id FROM reporting.queue LIMIT 0"))
        for schema in ("booking", "visits"):
            conn.execute(text(f"SELECT event_id FROM {schema}.outbox LIMIT 0"))


app.state.readiness_check = check_pipeline


@app.get("/admin/analytics", dependencies=[Depends(administrator)])
def metrics():
    if app.state.engine is None:
        raise HTTPException(503, "Analytics database unavailable")
    with app.state.engine.connect() as conn:
        conn.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        )
        result = {
            name: [dict(row) for row in conn.execute(text(query)).mappings()]
            for name, query in {
                "daily_arrivals": "SELECT * FROM reporting.daily_arrivals ORDER BY day DESC LIMIT 366",
                "tickets_by_tier": "SELECT * FROM reporting.tickets_by_tier ORDER BY purchased_tickets DESC,tier_id",
                "revenue_by_tier": "SELECT * FROM reporting.revenue_by_tier ORDER BY revenue_cents DESC,tier_id",
                "popular_attractions": "SELECT * FROM reporting.popular_attractions ORDER BY riders DESC,attraction_id",
                "busiest_quiet_hours": "SELECT * FROM reporting.busiest_quiet_hours ORDER BY hour",
                "outside_hours_arrivals": "SELECT * FROM reporting.outside_hours_arrivals ORDER BY day DESC LIMIT 366",
                "pipeline": "SELECT status,count(*) AS events,min(enqueued_at) FILTER(WHERE status='pending') AS oldest_pending_at,max(completed_at) AS last_completed_at FROM reporting.queue GROUP BY status ORDER BY status",
            }.items()
        }
        unpublished = conn.execute(
            text(
                "SELECT (SELECT count(*) FROM booking.outbox WHERE published_at IS NULL)+(SELECT count(*) FROM visits.outbox WHERE published_at IS NULL)"
            )
        ).scalar()
    remote = None
    if settings.analytics_transport == "sqs":
        client = getattr(app.state, "sqs_client", None)
        if client is None:
            remote = {"status": "unavailable"}
        else:
            try:
                attrs = client.get_queue_attributes(
                    QueueUrl=settings.sqs_queue_url,
                    AttributeNames=[
                        "ApproximateNumberOfMessages",
                        "ApproximateNumberOfMessagesNotVisible",
                    ],
                )["Attributes"]
                dead = (
                    client.get_queue_attributes(
                        QueueUrl=settings.sqs_dead_queue_url,
                        AttributeNames=["ApproximateNumberOfMessages"],
                    )["Attributes"]
                    if settings.sqs_dead_queue_url
                    else {}
                )
                remote = {
                    "status": "approximate",
                    "visible": int(attrs["ApproximateNumberOfMessages"]),
                    "in_flight": int(attrs["ApproximateNumberOfMessagesNotVisible"]),
                    "dead_letters": int(dead.get("ApproximateNumberOfMessages", 0)),
                }
            except (BotoCoreError, ClientError):
                remote = {"status": "unavailable"}
    return {
        **result,
        "remote_queue": remote,
        "unpublished_events": unpublished,
        "processing_enabled": settings.analytics_enabled,
        "transport": settings.analytics_transport,
        "timezone": "Asia/Colombo",
        "open_hour": 9,
        "close_hour": 18,
        "consistency": "eventual",
    }


@app.post("/admin/analytics/redrive/{event_id}", dependencies=[Depends(administrator)])
def redrive(event_id: str):
    if settings.analytics_transport == "sqs":
        raise HTTPException(409, "Use the separately authorized SQS DLQ workflow")
    if app.state.engine is None:
        raise HTTPException(503, "Analytics database unavailable")
    with app.state.engine.begin() as conn:
        changed = conn.execute(
            text(
                "UPDATE reporting.queue SET status='pending',attempts=0,available_at=now(),failure_code=NULL WHERE event_id=:id AND status='dead' RETURNING event_id"
            ),
            {"id": event_id},
        ).scalar()
    if not changed:
        raise HTTPException(404, "Dead-letter event not found")
    return {"event_id": changed, "status": "pending"}


@app.get("/admin/analytics/dead-letters", dependencies=[Depends(administrator)])
def dead_letters():
    if settings.analytics_transport == "sqs":
        raise HTTPException(
            409,
            "SQS dead letters are in the AWS DLQ; local queue controls are disabled",
        )
    if app.state.engine is None:
        raise HTTPException(503, "Analytics database unavailable")
    with app.state.engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    "SELECT event_id,attempts,failure_code,enqueued_at FROM reporting.queue WHERE status='dead' ORDER BY enqueued_at LIMIT 100"
                )
            ).mappings()
        ]
