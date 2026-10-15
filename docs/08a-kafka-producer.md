# Chapter 8a: Workers send their events to Kafka (the producer)

Code: [`services/worker/worker.py`](../services/worker/worker.py) (`make_producer`, `emit`, `flush_events`),
[`services/api/app/k8s.py`](../services/api/app/k8s.py) (`worker_env`), [`k8s/base/api-deployment.yaml`](../k8s/base/api-deployment.yaml)

Until now, `emit()` only **printed** each event: stdout → a log file on the node → `kubectl logs`.
Nobody read it. Now each event is **also** sent to the Kafka topic `analysis-events`.
In 8b, the API will read them.

```
 worker pod (namespace analyses)                                 Kafka (namespace kafka)
 emit("step.progress", percent=60)
   ├─ print(...)            → pod logs (as before)
   └─ producer.produce(...) → local buffer → background thread ──► toyscale-kafka-bootstrap:9092
                                                                   topic analysis-events
                                                                   ├─ partition 0
                                                                   ├─ partition 1   ← key "an-0c91c7" always lands here
                                                                   └─ partition 2
```

## What changed, file by file

### 1. The worker (image `0.2.0`)
- **`requirements.txt`**: `confluent-kafka`, the Python wrapper around **librdkafka** (the reference C client).
  The Dockerfile installs it in its own layer, *before* copying `worker.py` (layer caching, chapter 3).
- **`make_producer()`**: creates a **Producer**, the client object that sends messages. Settings:
  - `bootstrap.servers`: the first address to contact. Kafka then tells the client where every broker is.
  - `message.timeout.ms: 10000`: give up on a message after 10 s rather than hang forever.
  - It returns `None` if `KAFKA_BOOTSTRAP` isn't set, so the worker still runs without Kafka (like `docker run` in chapter 3).
- **`emit()`**: after printing, calls `producer.produce(topic, key=ANALYSIS_ID, value=line)`.
- **`flush_events()`**, called just before the process exits. See "produce() doesn't send" below.

### 2. The API (image `0.1.3`)
The worker learns Kafka's address from an **env var**, the same way it learns `STEP`. The orchestrator
adds `KAFKA_BOOTSTRAP` and `KAFKA_TOPIC` to every Job it creates (`worker_env()` in `k8s.py`), but only if
the API itself has `KAFKA_BOOTSTRAP` set. The API Deployment now sets it:
```yaml
- name: KAFKA_BOOTSTRAP
  value: toyscale-kafka-bootstrap.kafka.svc:9092   # the Service Strimzi created (chapter 7b)
```
`<service>.<namespace>.svc` is the DNS name CoreDNS answers for. The worker pods are in `analyses`,
Kafka is in `kafka`: different namespaces can talk to each other by default (namespaces organize,
they don't isolate the network, as you saw in chapter 2).

## Three Kafka ideas this chapter uses

### The key decides the partition
A topic is split into **partitions** (ours has 3: literally 3 folders on Kafka's disk, as you saw in 7b).
When a message has a **key**, Kafka hashes it to choose the partition, so **the same key always goes to
the same partition**. We use the analysis id as the key, so:
- all events of one analysis are in **one** partition;
- inside a partition, messages are **strictly ordered** (each gets an increasing **offset**: 0, 1, 2...);
- so each analysis' events are read back **in order**: started → 20% → ... → completed.
Different analyses spread over the 3 partitions. (There is **no** order guarantee *between* partitions,
and we don't need one.)

### produce() doesn't send
`produce()` only puts the message in a **local buffer** and returns immediately; a background thread
sends batches to Kafka. That's what makes producers fast. The catch: if the program exits right after
its last `emit()`, the last messages may still be in the buffer, and are **lost**. That's usually
`step.completed`, the most important one. **`producer.flush(15)`** waits until the buffer is empty
(max 15 s). Every short-lived producer (scripts, Jobs, Lambdas) needs this.

### Delivery reports
Kafka confirms each message; the producer then calls `on_delivery(err, msg)`. We print undelivered
messages to stderr. (`producer.poll(0)` in `emit()` gives the producer a chance to run those callbacks.)

## Design choice: Kafka is telemetry, not the source of truth
What if Kafka is down? We tested it: deleting the broker pod in the middle of an analysis lost 3 of its
14 events (align's 80%, 100% and `step.completed`, which exceeded the 10 s timeout while the broker
restarted). Yet the analysis **succeeded**, and its call step started on time. That's on purpose:
- the **orchestrator** decides from the **Kubernetes Job status** (chapter 5), which doesn't depend on Kafka;
- the **events** are for the dashboard (8b) and must be allowed to have gaps.
The worker's exit code never depends on Kafka.

## Run it
```sh
make up                                     # builds worker 0.2.0 + API 0.1.3, loads, deploys
curl -X POST 'localhost/api/analyses?count=3'
```
Then watch the events arrive:
- **Kafka UI**: http://localhost/kafka-ui/ → Topics → `analysis-events` → Messages. Click a message: see its
  **key**, **partition**, **offset**, and the JSON value. Sort by offset, filter by key.
- **Command line**, with key, partition and offset:
```sh
kubectl exec -n kafka toyscale-dual-0 -- /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic analysis-events --from-beginning \
  --property print.key=true --property print.partition=true --property print.offset=true
```
👀 Check: one analysis id → always the same partition; within it, offsets increase; 7 events per step.

## Experiments
1. **Same key, same partition.** Run 6 analyses. In Kafka UI, group the messages by partition: each analysis
   stays in one; the 6 spread over the 3 partitions (not necessarily evenly: it's a hash).
2. **Kafka down mid-run** (what we tested). Start one analysis; while it's aligning, `kubectl delete pod toyscale-dual-0 -n kafka`.
   The analysis still succeeds (`curl localhost/api/analyses`), but some of its events are missing in Kafka UI.
   Why does the orchestrator not care? (Hint: what does it watch?)
3. **✍️ Why flush matters.** In `worker.py`, comment out `flush_events()` in the `__main__` block, set `WORKER_TAG := 0.2.1`
   in the Makefile and the `WORKER_IMAGE` env in `api-deployment.yaml` to `0.2.1`, `make up`, run an analysis.
   Count its events in Kafka UI: often `step.completed` is missing. Put it back afterwards (and back to `0.2.0`, or keep `0.2.1`).

## Checkpoint
- Messages appear in `analysis-events` for every analysis, keyed by analysis id.
- Self-check: how does the worker know where Kafka is? Why use the analysis id as the key? What does
  `flush()` protect against? If Kafka is down, why does the analysis still succeed?
