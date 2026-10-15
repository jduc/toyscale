# Strimzi: the Kafka OPERATOR.
#
# This does NOT install Kafka itself. It installs:
#   1. new object kinds (CRDs): Kafka, KafkaNodePool, KafkaTopic, KafkaUser...
#   2. a controller pod (the "operator") that watches those objects and creates
#      the real Kafka pods, disks, Services and config for them, then keeps them right.
#
# Like the orchestrator you wrote in chapter 5, but for Kafka, written by Kafka experts.
# We then ASK for a Kafka cluster with YAML in k8s/platform/kafka/ (see docs/07b).
resource "helm_release" "strimzi" {
  name             = "strimzi"
  repository       = "https://strimzi.io/charts/"
  chart            = "strimzi-kafka-operator"
  version          = "1.3.0"
  namespace        = "kafka"
  create_namespace = true

  values = [yamlencode({
    # Which namespaces the operator watches for Kafka objects.
    # Empty = only its own namespace ("kafka"): that's where we'll put our Kafka cluster.
    watchNamespaces = []

    # The operator itself is a small Java program; keep it modest on a laptop.
    resources = {
      requests = { cpu = "100m", memory = "384Mi" }
      limits   = { memory = "384Mi" }
    }
  })]
}

# Kafka UI (kafbat): a web page to browse topics and read messages.
# A normal app with a normal chart, no operator involved.
resource "helm_release" "kafka_ui" {
  name       = "kafka-ui"
  repository = "https://kafbat.github.io/helm-charts"
  chart      = "kafka-ui"
  version    = "1.6.5"
  namespace  = "kafka"

  # Install after Strimzi, which creates the "kafka" namespace.
  depends_on = [helm_release.strimzi]

  values = [yamlencode({
    # Where Kafka is: the "bootstrap" Service Strimzi creates for our cluster
    # (<cluster name>-kafka-bootstrap). Kafka UI keeps retrying until it exists.
    yamlApplicationConfig = {
      kafka = {
        clusters = [{ name = "toyscale", bootstrapServers = "toyscale-kafka-bootstrap.kafka.svc:9092" }]
      }
      auth = { type = "DISABLED" } # no login: it's only reachable from your Mac
    }

    # Serve the app under /kafka-ui instead of /, so it can share localhost with
    # the API (/api) and later the UI (/). The chart also moves its probes there.
    envs = { config = { SERVER_SERVLET_CONTEXT_PATH = "/kafka-ui" } }

    # The chart can create its own Ingress rule: /kafka-ui -> this app, via Traefik.
    ingress = {
      enabled          = true
      ingressClassName = "traefik"
      path             = "/kafka-ui"
    }

    resources = {
      requests = { cpu = "100m", memory = "384Mi" }
      limits   = { memory = "512Mi" }
    }
  })]
}
