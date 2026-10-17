# Wonderland assignment summary

**SE6020 Cloud Computing · Semester 3**

**T.M.S.U Tennakoon · MS21930386**

Repository: [github.com/saditha93/wonderland](https://github.com/saditha93/wonderland).

The Word submission report is maintained separately. It includes the cover, architecture and booking diagrams, eight implementation screenshots, test results, references and assistance acknowledgement. This Markdown summary travels with the source ZIP.

## Requirements and implementation

| Assignment area | Implementation |
|---|---|
| Architecture and report | [System diagram](../diagrams/system.mmd), Word report and design explanations |
| Microservices | Four FastAPI services for attractions, booking/payment, gate/rides and analytics |
| Web and identity | Separate React apps on Amplify; Cognito identity and backend admin/owner checks |
| Analytics | Purchase, arrival and ride outboxes; SQS; reporting facts; seven Metabase SQL cards |
| Containers | Service Dockerfiles and release images in ECR |
| Kubernetes and gateway | EC2 Minikube, kubectl, built-in Ingress, probes, replicas, HPA and API Gateway |
| Database | Service-owned PostgreSQL schemas on encrypted EC2 storage; self-managed, not RDS |
| Infrastructure as Code | Main Terraform stack plus separate reusable permissions root |
| GitHub | Repository and CI workflow; successful remote run and examiner access require confirmation |

## Business rules

Visitors discover attractions, authenticate, choose one ticket tier and valid visit slot, pay and view owned bookings/tickets/history. Initial booking prices are Individual USD40 for one guest, Couple USD75 for two, Family USD140 for up to four and Group USD165 for up to five. Administrators can change prices; existing bookings retain their stored amount.

Only a matching signed Stripe sandbox webhook confirms payment. Signed RS256 tickets permit independent gate verification. Admission is once per booked party on the visit date. Ride records require prior admission and an open attraction. Event identifiers prevent retries from duplicating bookings, admissions or reporting facts.

## Evidence and limitations

See [recorded AWS results](../results/aws-rehearsal.md) for the 17 October 2026 Minikube run: 212 tests, 45 resources, sandbox payment, concurrency, service isolation, recovery, SQL reporting, backup and teardown. The measured 2724 successful requests at 18 requests/second stayed below the HPA threshold. Separate backup restoration, new email signup and a complete HPA scaling cycle were not repeated.

One host and one database are shared failure domains. Built-in ingress-nginx is retired and retained for the requested lab demonstration. Optional EKS/RDS remains separate. Automatic GitHub cloud deployment is not implemented; server builds and private S3 artifacts remain in use.

## Demonstration and submission

Use [demo.md](../demo.md) for the walkthrough, [deployment.md](../deployment.md) for setup and [viva.md](../viva.md) for the architecture/code explanation. `./demo.sh package` produces the source-only handover ZIP. Verify repository access, a successful remote CI run, report details and chart results before submission. Credentials, Terraform state and private backups must remain excluded.

## Reference and acknowledgement

Primary requirements: supplied SLIIT SE6020 Cloud Computing 2026 Semester 03 assignment, pages 1–4. Official technical references and the implementation screenshots are included in the Word report.

OpenAI Codex assisted with development, tests, troubleshooting and report drafting. The student is responsible for reviewing the work, understanding and explaining the implementation, and acknowledging any other assistance according to the assignment rules.
