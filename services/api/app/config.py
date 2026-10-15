"""Settings, read from environment variables (same idea as the worker)."""

import os

NAMESPACE = os.environ.get("NAMESPACE", "analyses")
WORKER_IMAGE = os.environ.get("WORKER_IMAGE", "toyscale-worker:0.1.0")
MAX_RUNNING = int(os.environ.get("MAX_RUNNING", "5"))  # analyses running at the same time
TICK_SECONDS = float(os.environ.get("TICK_SECONDS", "1"))  # how often the orchestrator looks at the cluster

# Passed through to the worker pods, so you can make analyses short while testing.
WORKER_DURATION_MIN = os.environ.get("WORKER_DURATION_MIN", "5")
WORKER_DURATION_MAX = os.environ.get("WORKER_DURATION_MAX", "15")

# Where the worker pods send their events (chapter 8). Empty = workers don't use Kafka.
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "analysis-events")
