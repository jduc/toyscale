"""ToyScale worker: pretends to run one step of a biology analysis.

One container run = one step. Which step is chosen by environment variables,
because that's how Kubernetes passes configuration to a container:

    STEP          "align" (step 1) or "call" (step 2)
    ANALYSIS_ID   which analysis this run belongs to
    DATA_DIR      shared folder between the two steps (default /data)
    DURATION_MIN  / DURATION_MAX   fake work duration in seconds (default 5 / 15)
    FAIL_RATE     probability of a simulated crash, 0.0–1.0 (default 0; used in chapter 11)
    KAFKA_BOOTSTRAP  Kafka address; if set, every event is also sent to Kafka (chapter 8)
    KAFKA_TOPIC      topic for the events (default "analysis-events")

Step 1 "align" writes  DATA_DIR/aligned.json
Step 2 "call"  reads   DATA_DIR/aligned.json  and writes  DATA_DIR/variants.json

The exit code is what Kubernetes looks at: 0 = step succeeded, anything else = failed.
"""

import json
import os
import random
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STEP = os.environ.get("STEP", "")
ANALYSIS_ID = os.environ.get("ANALYSIS_ID", "local-test")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DURATION_MIN = float(os.environ.get("DURATION_MIN", "5"))
DURATION_MAX = float(os.environ.get("DURATION_MAX", "15"))
FAIL_RATE = float(os.environ.get("FAIL_RATE", "0"))

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "analysis-events")

ALIGNED_FILE = DATA_DIR / "aligned.json"
VARIANTS_FILE = DATA_DIR / "variants.json"


def make_producer():
    """A Kafka PRODUCER: the client object that sends messages to Kafka.

    None when KAFKA_BOOTSTRAP isn't set, so the worker still runs without Kafka
    (e.g. `docker run` on your Mac, like in chapter 3).
    """
    if not KAFKA_BOOTSTRAP:
        return None
    from confluent_kafka import Producer

    return Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,  # where to connect first
        "client.id": socket.gethostname(),     # shows up in Kafka's logs/metrics
        "message.timeout.ms": 10_000,          # give up on a message after 10 s (don't hang if Kafka is down)
    })


producer = make_producer()


def on_delivery(err, msg) -> None:
    """Called by the producer once Kafka confirmed (or refused) a message."""
    if err is not None:
        print(f"kafka: event NOT delivered: {err}", file=sys.stderr, flush=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(event: str, **fields) -> None:
    """Report what is happening: one JSON line on stdout AND one message in Kafka."""
    record = {
        "ts": now(),
        "event": event,
        "analysis_id": ANALYSIS_ID,
        "step": STEP,
        "host": socket.gethostname(),  # in Kubernetes: the pod name
        **fields,
    }
    line = json.dumps(record)
    print(line, flush=True)  # still goes to the pod logs, as before

    if producer is not None:
        # produce() does NOT send right away: it puts the message in a local buffer
        # and a background thread sends it. The KEY decides the partition: same
        # analysis id -> same partition -> this analysis' events stay in order.
        producer.produce(KAFKA_TOPIC, key=ANALYSIS_ID, value=line, on_delivery=on_delivery)
        producer.poll(0)  # let the producer run delivery callbacks for earlier messages


def fake_work(label: str) -> float:
    """Sleep for a random duration, reporting progress every ~20%."""
    duration = random.uniform(DURATION_MIN, DURATION_MAX)
    for pct in (20, 40, 60, 80, 100):
        time.sleep(duration / 5)
        emit("step.progress", percent=pct, doing=label)
        if pct == 60 and random.random() < FAIL_RATE:
            raise RuntimeError("simulated crash (FAIL_RATE)")
    return round(duration, 2)


def align() -> dict:
    """Step 1: 'align sequencing reads to a reference genome'."""
    rng = random.Random(ANALYSIS_ID)  # same analysis id -> same fake numbers
    reads = rng.randint(1_000_000, 5_000_000)
    duration = fake_work("aligning reads")
    result = {
        "analysis_id": ANALYSIS_ID,
        "reads_total": reads,
        "reads_mapped": int(reads * rng.uniform(0.90, 0.99)),
        "aligned_by": socket.gethostname(),
        "aligned_at": now(),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ALIGNED_FILE.write_text(json.dumps(result, indent=2))
    return {"output": str(ALIGNED_FILE), "duration_s": duration}


def call() -> dict:
    """Step 2: 'call variants' from step 1's output. Cannot run without it."""
    if not ALIGNED_FILE.exists():
        raise FileNotFoundError(f"{ALIGNED_FILE} not found: did step 1 (align) run?")
    aligned = json.loads(ALIGNED_FILE.read_text())

    duration = fake_work("calling variants")
    rng = random.Random(ANALYSIS_ID + "-call")
    variants = [
        {"chrom": f"chr{rng.randint(1, 22)}", "pos": rng.randint(10_000, 50_000_000),
         "ref": rng.choice("ACGT"), "alt": rng.choice("ACGT")}
        for _ in range(rng.randint(3, 8))
    ]
    result = {
        "analysis_id": ANALYSIS_ID,
        "input_reads_mapped": aligned["reads_mapped"],  # proof we used step 1's output
        "input_aligned_by": aligned["aligned_by"],
        "variants": variants,
        "called_by": socket.gethostname(),
        "called_at": now(),
    }
    VARIANTS_FILE.write_text(json.dumps(result, indent=2))
    return {"output": str(VARIANTS_FILE), "duration_s": duration,
            "input_from": aligned["aligned_by"], "variant_count": len(variants)}


STEPS = {"align": align, "call": call}


def main() -> int:
    if STEP not in STEPS:
        print(f"STEP must be one of {list(STEPS)}, got {STEP!r}", file=sys.stderr)
        return 2

    emit("step.started")
    try:
        summary = STEPS[STEP]()
    except Exception as exc:
        emit("step.failed", error=str(exc))
        return 1
    emit("step.completed", **summary)
    return 0


def flush_events() -> None:
    """Wait until every buffered message reached Kafka (max 15 s) before exiting.

    Without this, the last events (often `step.completed`!) could still be in the
    local buffer when the container stops, and be lost.
    Events are telemetry: if Kafka is unreachable we warn, but the step's result
    (and exit code) doesn't change.
    """
    if producer is None:
        return
    left = producer.flush(15)
    if left:
        print(f"kafka: {left} event(s) could not be delivered", file=sys.stderr, flush=True)


if __name__ == "__main__":
    exit_code = main()
    flush_events()
    sys.exit(exit_code)
