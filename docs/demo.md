# Run and demonstrate Wonderland

Use the AWS path below for the assignment. The server now uses Minikube, kubectl and the built-in Ingress add-on. Optional laptop commands are included at the end of this guide.

For server-side viva commands and the Ingress route example, see [Minikube and Ingress](deployment.md#minikube-and-ingress-on-the-server). The previous live rehearsal used K3s; repeat `up` and `check` to validate the new runtime.

## 1. Prepare without spending AWS credits

From the project root:

```bash
./demo.sh help
./demo.sh test
./demo.sh terraform-check
```

Expected results: Python tests pass, visitor/admin production builds succeed, and all six Terraform roots validate with mocked plans. The main deployment is `infrastructure/terraform/aws/`; the other roots include permissions and the optional EKS/RDS design. Mocked plans do not prove a live deployment.

If setup is missing, follow the README and [deployment setup](deployment.md). The original project's deployment IAM policies are retained. Do not reinstall or broaden permissions just to run tests.

## 2. Create the live demo

```bash
./demo.sh audit
./demo.sh up
```

`up` prints the account, plan and cost, then provisions and releases automatically. For a preview first, run `./demo.sh plan`. Keep Terminal open until all stages finish:

1. Terraform creates the infrastructure.
2. The server builds/publishes six container images.
3. The installer applies Kubernetes workloads and database migrations.
4. The server builds/publishes both Amplify websites.
5. Cognito demo accounts and the Stripe sandbox webhook are prepared.
6. Base hosting/API/authorization/Metabase checks run.

```bash
./demo.sh status
./demo.sh check
```

The EC2 console displays **Wonderland Demo Server**. `status` also prints the laptop SSH command; port 22 permits only the configured IPv4 `/32`. See [SSH setup](deployment.md#laptop-ssh-and-server-name).

Open the actual visitor and admin URLs. Private demo accounts are saved in `secrets/simple-cloud/accounts.json`; do not show that file while projecting. `check` verifies the platform and SQL cards. The business acceptance walkthrough is the next step.

## 3. Visitor → purchase → ticket

1. On the visitor website, show attractions and four ticket tiers.
2. Sign in. For a registration demonstration, use an inbox you control and enter its Cognito verification code.
3. Select one tier and a valid visit date/time slot. For today's gate demonstration, choose today and a slot that has not elapsed.
4. Create the booking. Show its reference and pending payment state.
5. Open Stripe Checkout. Confirm the page says **Sandbox**, then use test card `4242 4242 4242 4242`, any future expiry and three-digit CVC. Use fictional billing details and leave saving information unchecked.
6. After Stripe returns, sign in again if prompted, then open My bookings. The booking must be confirmed/paid before a ticket is issued. A browser redirect alone does not confirm payment.
7. Open the signed QR ticket and save the booking reference for the administrator.

For a negative payment test, create a separate booking and use `4000 0000 0000 0002`. Stripe should decline it and the booking must remain pending/unpaid. These are [Stripe's documented test cards](https://docs.stripe.com/testing); use no real card details.

## 4. Administrator → gate → ride

1. Sign in at the separate admin URL. A visitor account must not gain admin access.
2. Show attraction management and ticket pricing. Explain that existing bookings retain the price/revision they were created with.
3. Open Gate and present the paid reference or signed ticket. Admit the booked party.
4. Try the same check-in again: it must be rejected as already admitted.
5. Open Rides, select the checked-in booking, an open attraction and an allowed guest count, then record the ride.
6. Show the visitor's own visit history and the administrator's reports.

The gate accepts tickets only on their visit date. AWS does not enable the local after-hours simulator. For an ordinary viva flow, demonstrate during valid booking hours; do not change the clock or booking rules. The previous after-hours test fixture is explicitly described in [the results](results/aws-rehearsal.md), not a required user step.

## 5. Show real monitoring results

Open a second terminal:

```bash
./demo.sh monitor
```

Keep it open and visit http://127.0.0.1:3001. This is a private tunnel to AWS Metabase. Its private login is in `secrets/metabase-ec2.json`. Open the Wonderland dashboard and refresh all seven cards.

For one paid Family booking with four guests and one recorded four-guest ride, expect the new records to contribute:

| Metric | Contribution |
|---|---:|
| Purchased bookings | 1 |
| Revenue | The booking's stored price, initially USD 140 |
| Admitted guests | 4 |
| Ride events / riders | 1 / 4 |

Other test records can increase totals. Pending/declined bookings contribute no revenue. The analytics worker processes events asynchronously, so refresh after the outbox drains. Explain the difference between booking count, guest count and ride count. Hourly activity uses Asia/Colombo time; an empty hour stays zero.

## 6. Remove hosted resources

Close the monitoring tunnel with Ctrl+C, then:

```bash
./demo.sh down
./demo.sh audit
```

`down` plans and deletes automatically; keep Terminal open. Use `./demo.sh plan-down` first if you want a preview. A fresh database backup is verified before destruction. The final inventory must report **no active demo resources**. A failed backup or cleanup error is not a successful teardown.

Deployment IAM policies, local `.env`, source, Terraform state and backups remain. The server/database, public IP, hosted apps, registries, artifacts, queues, logs and runtime secret are removed; the matching Stripe test webhook is also removed. `up` creates a fresh seeded demo with new URLs/accounts; it does not automatically restore the old database.

Do not manually terminate EC2 before `down`, because doing so prevents a fresh database backup. For a stale detached-IP error, the cleanup helper attempts one tightly scoped Terraform retry; inspect any remaining error and rerun `down` with a fresh plan if necessary.

## Results and handover

[The recorded AWS results](results/aws-rehearsal.md) cover the reorganized release, its browser preflight correction and the documented after-hours gate fixture. User chart review, a normal-hours walkthrough, GitHub publication/remote CI and final submission remain open.

```bash
./demo.sh package
```

Submit the generated source ZIP and report after review. The archive excludes private data, installed dependencies, Terraform state and provider caches.

## Optional laptop demonstration

```bash
./demo.sh local
```

Keep Terminal open. Visitor: http://localhost:5173; administrator: http://localhost:5174. Use the private passwords printed in an interactive terminal or saved in `secrets/local.accounts.json`. Book a Family visit, use the local payment simulator, copy the booking reference, admit the party in admin, record a ride and refresh Reports. This mode permits today's elapsed slots for demonstration; cloud booking rules remain strict. Ctrl-C stops the apps and preserves local data.

For local Metabase, install Java 21 and place the official pinned `v0.58.35` JAR at `tmp/metabase/metabase.jar`, then run `./start.sh monitoring` in a second terminal. It prints the private dashboard URL/login and checks seven SQL cards. Port 3000 must be free. Obtain the JAR from `https://downloads.metabase.com/v0.58.35/metabase.jar`. The recorded SHA-256 is `922f061ef009ccb131f06022a1b8a2d03ff64ddc5eb1b9880126924b4ab0005f` (recorded bytes, not a vendor signature). AWS Metabase uses port 3001 through its SSM tunnel.

Optional Minikube rehearsal requires Colima, Docker/Buildx, Minikube and kubectl. The scripts use the named `wonderland` VM/profile and private kubeconfig rather than the default cluster. Install the tools, then:

```bash
./start.sh infra-test  # Build, deploy, business/recovery/HPA checks
./start.sh infra       # Visitor :5180 and admin :5181; Ctrl-C closes forwarding
./start.sh infra-stop  # Stop the cluster/VM; preserve its data
```

The local cluster is independent from native PostgreSQL and AWS. Its simulator records are demonstration data. The test writes its result to `docs/results/evidence/local-infrastructure.json`; a failed test is not successful evidence. Local HPA/pod recovery does not establish AWS or production capacity.
