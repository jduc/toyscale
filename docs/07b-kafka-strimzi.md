# Chapter 7b: Kafka, with the Strimzi operator

Code: [`terraform/02-platform/kafka.tf`](../terraform/02-platform/kafka.tf), [`k8s/platform/kafka/`](../k8s/platform/kafka/)

## What Kafka is (reminder)
A system for **passing messages between programs**, which also **keeps** them.

```
 producers (write)                    Kafka                         consumers (read)
 worker pods ──"an-42 align 60%"──►  topic "analysis-events"  ──►  API → dashboard (chapter 8)
                                      msg msg msg msg ... (kept 7 days)
```
- **Topic**: a named channel of messages (`analysis-events`).
- **Producer**: a program that writes to a topic (our workers, chapter 8).
- **Consumer**: a program that reads from a topic (our API, chapter 8).
- **Broker**: a Kafka server, the process that stores the messages and serves producers and consumers.
- Messages are **kept** (here 7 days), so a consumer can re-read from the beginning ("replay").

For ToyScale's small volume it's honestly overkill; we use it to learn it.
It shines with huge volumes, many independent readers, and replay.

## What an operator is
Running Kafka well needs ongoing care: stable names, a disk per broker, config that depends
on other brokers, careful one-by-one upgrades, creating topics. A Helm chart only creates
YAML once. An **operator** is a program that runs in the cluster and keeps doing that care,
forever. It's the same **watch → compare → act** loop as your chapter 5 orchestrator, written
by Kafka experts. Ours is **Strimzi**.

You talk to an operator through **new object kinds** it adds to Kubernetes, defined by
**CRDs** (Custom Resource Definitions). After installing Strimzi, `kubectl get kafka` works
like `kubectl get pods`.

## Who does what

| Step | Tool | What you write | What gets created |
|---|---|---|---|
| 1 | Terraform + Helm (`kafka.tf`) | `helm_release "strimzi"` | 10 CRDs (`Kafka`, `KafkaTopic`...) + the operator pod |
| 2 | kubectl (`k8s/platform/kafka/`) | a `KafkaNodePool`, a `Kafka`, a `KafkaTopic` | **Strimzi** creates the broker pod, its disk, Services, config, certificates, a helper pod... |
| 3 | Terraform + Helm (`kafka.tf`) | `helm_release "kafka_ui"` | a normal web app + its Ingress at `/kafka-ui` |

Why are step 2's objects plain YAML and not Terraform? Terraform's Kubernetes provider must
know an object's kind **while planning**, but the `Kafka` kind only exists **after** Strimzi is
installed: the chicken-and-egg problem again. Keeping them as YAML applied after the operator
avoids it. (Many teams use the same split: Terraform for the platform, YAML or GitOps for what runs on it.)

## Step by step: do it and watch

Open a second terminal with **`k9s -n kafka`** (or `kubectl get pods -n kafka -w`) and keep it visible.

### Step 1: install the operator
```sh
make platform        # plan shows 2 to add: strimzi + kafka_ui. Type yes.
```
What happened:
- Helm installed the **CRDs**: `kubectl get crd | grep strimzi` → `kafkas`, `kafkanodepools`, `kafkatopics`...
- It started **one pod**: `strimzi-cluster-operator-...`. This is the operator; it now watches the `kafka` namespace.
- Kafka UI started too, but shows the cluster **offline**: there's no Kafka yet. Open
  http://localhost/kafka-ui/ to see it.
- There's still **no Kafka**: `kubectl get kafka -n kafka` → `No resources found`.

Ask the cluster what the new kinds look like, exactly like for built-in kinds:
```sh
kubectl explain kafka.spec.kafka          # version, listeners, config...
kubectl explain kafkanodepool.spec        # replicas, roles, storage...
```

### Step 2: ask for a Kafka cluster
Read [`kafka-cluster.yaml`](../k8s/platform/kafka/kafka-cluster.yaml) first; every field is commented. In short:
- **`KafkaNodePool` "dual"**: 1 node, doing both jobs (*controller*: keeps the cluster's metadata;
  *broker*: stores messages), with a 1Gi disk and 512 MB of Java heap.
- **`Kafka` "toyscale"**: Kafka 4.3.1, one *listener* (how clients connect: plain, port 9092, inside
  the cluster only), and settings saying "keep 1 copy" (Kafka's default of 3 is impossible with 1 node).
- **`KafkaTopic` "analysis-events"**: 3 partitions, 1 replica, messages kept 7 days.

```sh
make kafka           # kubectl apply -k k8s/platform/kafka, then waits until Kafka is Ready (~1 min)
```
Watch k9s. In order, Strimzi:
1. reads your `Kafka` + `KafkaNodePool` objects,
2. creates certificates and config (`kubectl get secrets,configmaps -n kafka`),
3. creates a **disk claim** `data-toyscale-dual-0` (chapter 4's PVCs, pinned to one node),
4. starts the **broker pod `toyscale-dual-0`**. Note the stable name with `-0`, not a random suffix:
   other brokers and clients must always find "node 0" at the same name. (Strimzi manages these pods
   with its own `StrimziPodSet` kind, its version of Kubernetes' StatefulSet.)
5. creates two **Services**: `toyscale-kafka-bootstrap` (the address clients use:
   `toyscale-kafka-bootstrap.kafka.svc:9092`) and `toyscale-kafka-brokers` (one DNS name per broker),
6. starts the **entity operator** pod; its *Topic Operator* sees your `KafkaTopic` and creates the topic inside Kafka.

Check the result:
```sh
kubectl get kafka,kafkanodepool,kafkatopic -n kafka     # READY True everywhere
kubectl get pods,pvc,svc -n kafka
kubectl describe kafka toyscale -n kafka | tail -20     # status written BY Strimzi: conditions, listener addresses
```
That's the same split as everywhere in Kubernetes: you wrote `spec`, the operator writes `status`.

### Step 3: send and read messages by hand
The Kafka image ships command-line tools. Run them **inside** the broker pod:
```sh
# producer: every line you type becomes a message (ctrl-d to finish)
kubectl exec -it -n kafka toyscale-dual-0 -- /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 --topic analysis-events
# consumer: read everything from the beginning (ctrl-c to stop)
kubectl exec -it -n kafka toyscale-dual-0 -- /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic analysis-events --from-beginning
```
Run the consumer in one terminal and the producer in another: lines appear live. Stop the consumer,
start it again with `--from-beginning`: **all old messages come back**. That's retention + replay.

### Step 4: Kafka UI
Open **http://localhost/kafka-ui/** (routed by Traefik, like `/api`).
*Topics → analysis-events → Messages*: your messages, with their **partition** and **offset**
(position in the partition). You can also produce a message from the UI.

## Experiments
1. **The operator heals.** `kubectl delete pod toyscale-dual-0 -n kafka`. Strimzi recreates it with the
   **same name** and the **same disk**. Re-run the consumer with `--from-beginning`: messages survived.
2. **Change the request, the operator follows.** In `kafka-topic.yaml` set `partitions: 4`,
   `kubectl apply -k k8s/platform/kafka`. Kafka UI shows 4 partitions. Now try `partitions: 2`:
   `kubectl describe kafkatopic analysis-events -n kafka` → the status shows an **error**, because Kafka can't
   reduce partitions. The operator refuses and tells you why, in `status`. Put it back to 4 (or 3 after a re-create).
3. **Kafka lives in the operator's hands, not yours.** `kubectl delete svc toyscale-kafka-bootstrap -n kafka`,
   then `kubectl get svc -n kafka` again a few seconds later: it's back. Same reconcile loop as chapter 5.

## Pitfalls we hit while building this
- **Delete order matters (finalizers again).** Deleting the cluster and the topic together got stuck:
  the `KafkaTopic` has a finalizer `strimzi.io/topic-operator` ("wait until the Topic Operator deleted the real topic"),
  but deleting the `Kafka` cluster had already removed that helper. Nobody could clear the flag.
  Fix: delete **topics first, then the cluster**; that's what `make kafka-down` does.
  If it happens anyway: `kubectl patch kafkatopic <name> -n kafka --type=merge -p '{"metadata":{"finalizers":[]}}'`
  (only when you're sure nothing else will clean up).
- **Helm never deletes CRDs.** After uninstalling Strimzi, `kubectl get crd | grep strimzi` still lists them.
  That's deliberate: deleting a CRD deletes every object of that kind, cluster-wide.

## Memory check
Kafka is the heaviest thing so far. See what's reserved and used:
```sh
kubectl describe node toyscale-worker | grep -A8 'Allocated resources'
docker stats --no-stream | grep toyscale
```
When we built this, the three nodes used about 2.5 GB in total.

## Checkpoint
- `kubectl get kafka -n kafka` → READY True; you produced and consumed messages; Kafka UI shows them.
- Self-check: what's the difference between installing Strimzi and creating a `Kafka` object? Who creates
  the broker pod? Why does the broker pod have a stable name and its own disk? What happens to messages
  when the broker pod is deleted, and why? Why must topics be deleted before the cluster?
