variable "cluster_name" {
  description = "Name of the kind cluster (kubectl context becomes kind-<name>)"
  type        = string
  default     = "toyscale"
}

variable "worker_count" {
  description = "Number of worker nodes. Change it and re-apply to see Terraform replace the cluster."
  type        = number
  default     = 2
}
