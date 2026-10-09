# One resource = one kind cluster. Each node is a Docker container.
resource "kind_cluster" "this" {
  name           = var.cluster_name
  wait_for_ready = true # don't finish `apply` until the nodes report Ready

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    # Control-plane node: runs the API server, scheduler, etcd...
    node {
      role = "control-plane"

      # Label used later (chapter 7) so the ingress controller lands on this node.
      kubeadm_config_patches = [
        <<-EOT
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
        EOT
      ]

      # Forward localhost:80/443 on your Mac into this node container,
      # so http://localhost reaches the ingress controller.
      extra_port_mappings {
        container_port = 80
        host_port      = 80
      }
      extra_port_mappings {
        container_port = 443
        host_port      = 443
      }
    }

    # Worker nodes: where our analysis pods will actually run.
    dynamic "node" {
      for_each = range(var.worker_count)
      content {
        role = "worker"
      }
    }
  }
}
