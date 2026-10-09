# Which Terraform and which providers this stack needs.
# `terraform init` reads this, downloads the providers into .terraform/
# and pins the exact versions in .terraform.lock.hcl (commit that file!).
terraform {
  required_version = ">= 1.6"

  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = "~> 0.11"
    }
  }
}

provider "kind" {}
