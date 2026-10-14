terraform {
  required_version = ">= 1.6"

  required_providers {
    # Installs Helm charts, like running `helm install` / `helm upgrade` for us.
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.3"
    }
  }
}

# Read the OUTPUTS of the other stack (terraform/01-cluster) from its state file.
# This is how stacks talk to each other: one writes outputs, the next one reads them.
data "terraform_remote_state" "cluster" {
  backend = "local"
  config = {
    path = "${path.module}/../01-cluster/terraform.tfstate"
  }
}

# The helm provider needs to know WHICH cluster to install into:
# the kubeconfig file that stack 01 created. The cluster already exists by the time
# this stack runs, so this value is known at plan time (no chicken-and-egg problem).
provider "helm" {
  kubernetes = {
    config_path = data.terraform_remote_state.cluster.outputs.kubeconfig_path
  }
}
