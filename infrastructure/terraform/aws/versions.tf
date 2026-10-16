terraform {
  backend "local" { path = "../../../secrets/simple-cloud/terraform.tfstate" }
  required_version = "= 1.16.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
}
