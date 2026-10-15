# First AWS deployment

The visitor/admin hosting wiring is fixed. Both apps build; the cloud helper publishes them to separate Amplify apps and configures API Gateway for both origins. Cloud builds explicitly disable demo mode. Live verification checks the two URLs and their CORS preflights. These checks do not replace signed-in role tests.

## Updated deployment preferences

The user requested no purchased domain or Route 53 setup, the lowest practical demo cost, AWS Free Tier/credits, and private local AWS/Stripe keys. Treat out-of-pocket spending, domain purchases and Paid-plan upgrades as unapproved. The existing EKS runbook remains an advanced alternative, not the selected launch plan.

The existing private ALB HTTPS design still requires a domain/certificate; it must not be deployed unchanged for this request. The lower-cost candidate is one EC2 instance running a single-node Kubernetes distribution, PostgreSQL and the application services, with separate Amplify websites and Cognito. Keep Metabase private. This removes the EKS control-plane and separate managed database/load-balancer baseline, but does not establish zero cost or multi-node availability. Confirm the instance has sufficient memory for the actual workloads rather than assuming a tiny eligible instance can run everything.

AWS-provided Amplify/API Gateway URLs avoid buying a domain. A direct server IP still needs valid HTTPS for secure authenticated/payment traffic. Let's Encrypt now offers short-lived IP certificates, with automated renewal required; Certbot 5.4+ supports IP webroot issuance. Validate the API Gateway-to-IP TLS integration before selecting that design. Do not use plaintext public login/payment traffic or disable certificate verification to simplify setup. See [official IP certificate instructions](https://letsencrypt.org/2026/03/11/shorter-certs-certbot).

The smaller EC2 topology is a candidate design, **not yet implemented or deployed**. Before its Terraform implementation, establish the account plan/credit eligibility and which services are available. EKS standard control-plane pricing alone is $0.10/hour, plus workers/storage/networking; it cannot be described as inherently free. Newer AWS Free plans have selected-service and time/credit restrictions. See [EKS pricing](https://aws.amazon.com/eks/pricing/) and [AWS Free Tier](https://aws.amazon.com/free/).

The prerequisite list below describes the original EKS path. Its domain/hosted-zone items do not apply to the user's requested no-domain alternative; do not buy a domain or fill that original target merely to satisfy it.

## What is needed now

No named AWS CLI profile or private deployment target was found during the 15 October 2026 readiness check. Before deploying, supply:

- Your AWS account and a named CLI profile using a non-root operator role.
- Your chosen AWS region and maximum demo budget/runtime.
- An owned domain with an existing public Route 53 hosted zone for the internal ALB TLS certificate.
- Your operator public IPv4 /32 and your alert email.

No account was contacted, cloud resource created or billing setting changed by this update. Existing local app/data remain available.

## Private .env option

The project root `.env` is now the preferred place for the user's AWS and Stripe test keys. It is ignored by Git/Docker and has mode 0600. The cloud helper reads only the relevant credential fields; it does not import unrelated application settings from this file. Existing values were preserved.

```dotenv
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
AWS_REGION=us-east-1
APP_STRIPE_SECRET_KEY=
APP_STRIPE_WEBHOOK_SECRET=
```

Use the AWS key ID and matching secret from a non-root identity. Leave session token blank for long-term IAM credentials; include it for temporary role credentials. AWS region must match the reviewed target. A root-file credential pair takes precedence over shell credentials, including clearing any stale shell session token. Without an environment credential pair, the existing named profile path remains supported. Current deployment identity/account/operator-role checks remain enforced; keys alone do not select a deployment target or authorize resource creation.

Use only Stripe `sk_test_` keys. Leave the webhook signing secret blank until the endpoint is registered, then supply its `whsec_` value. Cloud payment deployment requires both. Existing `secrets/stripe.env` remains a fallback when neither Stripe field is filled in the root `.env`; incomplete pairs are rejected rather than mixed across files. Payment action review hashes change when either Stripe value changes. No credential contents are printed. Frontend builds exclude AWS and Stripe environment credentials.

Read-only browser inspection on 15 October 2026 confirmed the Free plan, $139.96 credit balance and 131 days remaining at the time of inspection, with N. Virginia selected. No cloud resources or account settings were changed. Command-line credentials were subsequently verified as the non-root wonderland user; Stripe test authentication also passed. ReadOnlyAccess was confirmed attached, and EC2/Free Tier reads passed. The plan is ACTIVE/FREE. Deployment grants are [prepared and validated](../infrastructure/iam/README.md), pending explicit attachment confirmation. No compute resources have been created.

## Configure authentication

If you already have IAM Identity Center access, use its start URL and SSO region in the AWS CLI wizard:

```bash
aws configure sso --profile wonderland-demo
aws sso login --profile wonderland-demo
```

Choose your intended account and role. The SSO directory region can differ from your deployment region. For an existing assume-role profile, keep that profile instead. Do not use root credentials or paste access keys/passwords into chat. If you have no AWS account/role or SSO access yet, complete that setup first; the application does not create its own initial operator identity. See [AWS CLI authentication instructions](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html).

## Original EKS path: create the private target

From the project root, copy the example only if your private target does not already exist:

```bash
mkdir -p secrets
cp -n infrastructure/terraform/cloud-target.example.json secrets/cloud-target.json
chmod 600 secrets/cloud-target.json
```

Edit the private file. Replace every illustrative value; do not run against its sample account or domain. The account ID must match the profile, and `operator_role_arn` must be the exact role that profile assumes. Region/AZs, supported EKS version and PostgreSQL patch need live availability checks. The state bucket name must be globally unique. Keep protection/retention defaults until cleanup choices are reviewed. State/config/credentials are excluded from Git.

## Original EKS path: deployment sequence together

Once your target and budget are selected, run the read-only preflight and generate the real bootstrap plan. Review its account, resources and expected cost before applying. Then proceed through state migration, persistent hosting/auth, temporary EKS/RDS/queue infrastructure, images/controller/workloads, edge and both website deployments. Saved-plan/action hashes bind execution to reviewed inputs; do not replace them with sample hashes.

Exact commands and cleanup order are in the [cloud runbook](cloud-runbook.md). Live Cognito registration, Stripe test delivery, role/ownership denial, Metabase data reconciliation and infrastructure recovery remain required after deployment. Stripe test keys belong only in the private file described there.

The runbook's broad historical cost allowances are not a quote for your selected region or a hard spending cap. Refresh the estimate for the actual target and retention before creating paid resources.

Implementation references: [Amplify manual deployments](https://docs.aws.amazon.com/amplify/latest/userguide/manual-deploys.html), [API Gateway CORS](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-cors.html).
