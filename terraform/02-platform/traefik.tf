# Traefik: the ingress controller. It receives all HTTP traffic coming into the
# cluster and forwards each request to a Service, following the Ingress rules.
#
# A helm_release = one installed copy of a chart (what `helm list` shows).
resource "helm_release" "traefik" {
  name             = "traefik"                          # the release name
  repository       = "https://traefik.github.io/charts" # where the chart is published
  chart            = "traefik"                          # which chart in that repository
  version          = "41.7.1"                           # pinned chart version
  namespace        = "traefik"
  create_namespace = true

  # The "values": our answers to the chart's blanks. Everything not set here keeps
  # the chart's default (see them with: helm show values traefik/traefik --version 41.7.1).
  # yamlencode() turns this HCL object into the YAML text Helm expects.
  values = [yamlencode({

    # Run Traefik on the control-plane node: that's the node where chapter 1
    # forwarded your Mac's localhost:80 and :443 (extra_port_mappings).
    nodeSelector = { "ingress-ready" = "true" }
    tolerations = [{ # allow it despite the control-plane taint (chapter 2)
      key      = "node-role.kubernetes.io/control-plane"
      operator = "Exists"
      effect   = "NoSchedule"
    }]

    # Bind Traefik's ports directly on that node: node port 80 → Traefik.
    ports = {
      web       = { hostPort = 80 }
      websecure = { hostPort = 443 }
    }

    # On a cloud this would be a LoadBalancer (a public IP). kind has none:
    # the hostPorts above are our way in, so an internal Service is enough.
    service = { spec = { type = "ClusterIP" } }

    # A hostPort can only be used by one pod per node, so during an upgrade the
    # old pod must stop BEFORE the new one starts (like `Recreate` for our API).
    updateStrategy = {
      type          = "RollingUpdate"
      rollingUpdate = { maxUnavailable = 1, maxSurge = 0 }
    }

    # Make Traefik the default handler for Ingress objects in the cluster.
    ingressClass = { enabled = true, isDefaultClass = true }
  })]
}
