# Outputs are the "return values" of a stack. Stack 02-platform will read
# these to know how to connect to the cluster.
output "cluster_name" {
  value = kind_cluster.this.name
}

output "kubeconfig_path" {
  value = kind_cluster.this.kubeconfig_path
}

output "endpoint" {
  value = kind_cluster.this.endpoint
}

output "kubectl_context" {
  value = "kind-${kind_cluster.this.name}"
}
