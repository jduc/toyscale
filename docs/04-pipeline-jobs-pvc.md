# Chapter 4: The 2-step pipeline by hand (Jobs + PVC)

Hands-on: [playground/pipeline-by-hand/](../playground/pipeline-by-hand/README.md)

Chapter 3's Docker pipeline, rebuilt with Kubernetes objects:

| Chapter 3 (Docker) | Chapter 4 (Kubernetes) |
|---|---|
| `docker run -e STEP=align ...` | **Job** `demo-1-align` |
| `docker run -e STEP=call ...` | **Job** `demo-1-call` |
| `-v $PWD/data:/data` | **PersistentVolumeClaim** `data-demo-1`, mounted at `/data` |
| you run them in the right order | you still do: `kubectl wait`, then create step 2 |

```
 analysis demo-1          namespace "analyses"
 ┌────────────────────────────────────────────────────────────────────┐
 │ Job demo-1-align ─► Pod ─┐                    ┌─ Pod ◄─ Job demo-1-call
 │                          ▼                    ▼                      │
 │              PVC data-demo-1  ══bound══  PV pvc-1234  (a folder on ONE node) │
 └────────────────────────────────────────────────────────────────────┘
```

## Jobs: pods for work that finishes

| | Deployment (chapter 2) | Job |
|---|---|---|
| For | servers: should run **forever** | tasks: should run **once, to success** |
| Pod exits with 0 | restarts it ("why did my server stop?") | **done**: Job = `Complete` |
| Pod exits with ≠ 0 | restarts it | creates a **new pod**, up to `backoffLimit` times, then Job = `Failed` |
| `restartPolicy` | `Always` | `Never` (or `OnFailure`) |

Useful Job fields (all in `job-align.yaml`):
- `backoffLimit: 2`: how many retries before giving up.
- `activeDeadlineSeconds: 300`: a hard timeout for the whole Job.
- `ttlSecondsAfterFinished: 3600`: auto-cleanup, so finished Jobs don't pile up forever.

**Jobs are mostly immutable.** You can't `apply` a changed pod template onto an existing Job.
To re-run, delete it and create it again (or give it a new name, as the API will).

## Storage: StorageClass → PVC → PV

| Object | Who creates it | Means |
|---|---|---|
| **StorageClass** `standard` | the cluster admin (kind ships one) | "*how* to make disks": here a folder on the node (`local-path`); on AWS, an EBS volume |
| **PersistentVolumeClaim** (PVC) | **you**, in a namespace | "I need 100Mi, read-write": a *request* |
| **PersistentVolume** (PV) | **automatically**, by the StorageClass's provisioner | the actual disk that satisfies the claim (*dynamic provisioning*) |

The pod only names the claim (`claimName: data-demo-1`). It never cares where the disk really is.
Delete the PVC and, with `reclaimPolicy: Delete`, the PV and its data go too.

**Access modes:** `ReadWriteOnce` = mounted by pods **on one node at a time**. That's enough for us
because our steps run one after the other. (`ReadWriteMany`, shared across nodes at once,
needs network storage such as NFS or AWS EFS.)

## The key lesson: storage pins scheduling

kind's `standard` class has `volumeBindingMode: WaitForFirstConsumer`:
1. When you create the PVC, it stays **`Pending`**: no disk is made yet.
2. The first pod that uses it gets scheduled normally (say on `toyscale-worker`).
3. *Then* the disk is created **on that node**, and the PV records `nodeAffinity: toyscale-worker`.
4. Every later pod using this claim **must** run on `toyscale-worker`, where the folder physically
   lives. The scheduler's filter (chapter 2) now has a new rule.

So step 2 automatically follows step 1 to the same node. On AWS with EBS volumes the same thing
happens at the level of **availability zones**: a disk lives in one zone, so its pods must too.
It's a classic source of `Pending` pods in production.

## Resources: requests and limits (preview)
```yaml
resources:
  requests: { cpu: 100m, memory: 64Mi }  # reserved on the node; the scheduler only places the pod where this fits
  limits:   { memory: 128Mi }            # hard cap: exceeding the memory limit = the container is killed (OOMKilled)
```
`100m` = 100 millicores = 0.1 CPU. We'll play with these in chapter 11 to fill the nodes up.

## What Kubernetes does NOT do for us
Nothing in Kubernetes says "start `demo-1-call` after `demo-1-align` succeeds". There's no built-in
"Job B depends on Job A". Today **you** are the orchestrator (`kubectl wait`, then `apply`). In
chapter 5 we write a program that does exactly what you did by hand.
