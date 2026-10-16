# Simple viva rehearsal

Use this as a speaking guide, and explain the code in your own words. The report and screenshots require your personal review before submission.

## Before presenting

Run `./start.sh test` and `./start.sh infra-test`. Read the recorded pass/fail results. Do not present passwords, readable QR payloads or private terminal logs. Keep the source archive from `./start.sh package` ready. Confirm the lecturer's provisioning/submission rules; a local rehearsal does not satisfy live AWS requirements by itself.

## App: about five minutes

1. Open the visitor app. Explain: “Visitors can browse rides and choose a ticket tier.”
2. Sign in, book four guests for today and confirm the demo payment. Explain that the backend stores the price and verifies confirmation; the simulator does not charge money.
3. Show the reference/QR and My bookings.
4. Open the separate admin app. Check in that reference for four guests. Repeat it to demonstrate duplicate prevention.
5. Choose that arrival and record two riders at an open attraction.
6. Open Reports. Show the five required metrics and explain that reports update after processing. Mention Sri Lanka time and the 09:00–18:00 hourly window.
7. If asked, show price/attraction management and the visitor profile/history.

## Infrastructure: allow several minutes

Run `./start.sh infra-test` from a clean gateway state. Explain each displayed step while it runs:

- Terraform mock checks validate the prepared definitions without provisioning AWS.
- Each API has its own container and Kubernetes Service. Gate looks up attractions through internal service DNS.
- Deleting a catalog pod causes Kubernetes to replace it; the second replica continues serving traffic.
- Blue/green deployments demonstrate service switching and rollback. This demo uses the same domain code with different version metadata.
- Pausing analytics preserves queued work while purchases/arrivals/rides continue; processing catches up afterward.
- Database failure leaves processes alive but unready; restoration verifies persistent records.
- Real catalog requests cause the HPA to grow from two to three replicas, then return to two.

Show `docs/results/evidence/local-infrastructure.json` afterward. Do not call nginx “AWS API Gateway”, local password login “Cognito”, mocked plans “applied infrastructure”, or simulated payments “Stripe delivery”.

## Six questions to practise

| Question | Answer to explain |
|---|---|
| Why separate services? | Catalog, booking, gate and reports have different responsibilities; deployment/failure isolation costs extra coordination. |
| How are duplicates prevented? | User-bound booking command keys, signed payment event handling, unique arrivals and ride event IDs, and transactional reporting deduplication. |
| Why can reports lag? | Operational writes commit first; an outbox/queue feeds reporting facts asynchronously. |
| What is ready versus live? | A process can be running while database/schema access fails; unready pods should not receive service traffic. |
| Why PostgreSQL? | Bookings, payment state and reporting need transactions, uniqueness and SQL aggregation. The shared instance is still a failure domain. |
| What is still unverified? | Actual AWS resources/auth/hosting/queues/gateway, external Stripe delivery, remote CI and the live cloud cleanup audit. |

End by showing `./start.sh infra-stop` and explaining that it stops local resources while preserving data. Actual cloud cleanup is separately guarded and must be audited.
