provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = [var.account_id]
  default_tags { tags = { Project = "wonderland", Stack = "wonderland-demo", ManagedBy = "terraform" } }
}
# Stage creation checks the parent API tags. Avoid a second implicit TagResource
# authorization call; ownership remains on the already tagged API itself.

provider "aws" {
  alias               = "api_stage"
  region              = "us-east-1"
  allowed_account_ids = [var.account_id]
}

locals {
  name   = "wonderland-demo"
  bucket = "${local.name}-${var.account_id}-artifacts"
  images = toset(["attractions-service", "booking-service", "gate-ride-service", "analytics-worker", "migrate", "frontend"])
}
