# analytics-worker

Durable local PostgreSQL transport and reporting projection, with administrator-only analytics/DLQ endpoints. `/health/live` checks the process; `/health/ready` checks reporting migration revision 2, queue/outbox access and the enabled worker thread. Configure `APP_DATABASE_URL` with the reporting role and `APP_ANALYTICS_ENABLED=true` to process events. Default processing is off so imports/tests do not mutate data. Native/Compose launchers explicitly enable it. Auth uses the shared local/test or Cognito verifier; disabled auth fails closed.

The worker commits outbox publication with local queue insertion and commits facts/dedupe with completion acknowledgment. Row locks and rollback provide crash recovery; three malformed-event attempts lead to a durable dead-letter state. Database errors retry without acknowledging. Logs include request metadata and sanitized database retry reasons, not event bodies or credentials. The read model owns purchase, arrival and ride facts; the BI login can select only aggregate views.

The injected SQS adapter is offline-tested and does not connect to AWS by default. Actual queue/IAM/redrive deployment remains future approved work. See [Phase 4 outcome](../../docs/phase-4-outcome.md) for commands, evidence and limitations.
