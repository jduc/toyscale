# Chapter 5: The API and its orchestrator

Code: [`services/api/`](../services/api/)

In chapter 4 **you** were the orchestrator. Now a program does it: a small web API that
accepts "run an analysis" requests and drives each one through the cluster.

In this chapter the API runs **on your Mac** and talks to the cluster from outside, exactly
like `kubectl` does. Chapter 6 moves it inside.

```
 curl / browser                      your Mac                          kind cluster
 ─────────────►  FastAPI (main.py)                                   namespace "analyses"
 POST /analyses        │ submit()
                       ▼
                 Orchestrator ──── every second ───►  Kubernetes API ──► PVC, Jobs, Pods
                 (orchestrator.py)   observe / act     (via k8s.py,
                  in-memory list                        using ~/.kube/config)
```

## The files

| File | Role | Chapter 4 equivalent |
|------|------|----------------------|
| `app/main.py` | HTTP endpoints: `POST /analyses`, `GET /analyses`, `GET /stats` | you deciding to run something |
| `app/orchestrator.py` | the loop that moves each analysis forward | you typing `kubectl wait`, then `apply` |
| `app/k8s.py` | builds the PVC/Job objects and calls the Kubernetes API | the YAML files + `kubectl` |
| `app/models.py` | what an analysis is, and its possible statuses | (in your head) |
| `app/config.py` | settings from env vars (`MAX_RUNNING=5`...) | |

Open `k8s.py` next to `playground/pipeline-by-hand/job-align.yaml`: **`job_manifest()` is the
same object**, as a Python dict with the analysis id filled in. `kubectl` and this code call
the same Kubernetes API; kubectl is just another client.

## The life of an analysis (a state machine)

```
                 slot free?            align Job complete        call Job complete
   QUEUED ────────────────► ALIGNING ───────────────────► CALLING ─────────────────► SUCCEEDED
  (waiting)  create PVC    (step 1 running)  create call  (step 2 running)  read result,
             + align Job         │           Job               │            delete Jobs+PVC
                                 └──── Job failed ─────────────┴──────────► FAILED (delete PVC)
```
"Slot free" = fewer than `MAX_RUNNING` (5) analyses are in ALIGNING or CALLING.
That one `if` in `_maybe_start()` is the whole "max 5" rule.

## The reconcile loop

`Orchestrator.tick()` runs every second and always does the same three things:

1. **Observe**: list all our Jobs and pods (two API calls, filtered by the label `app=toyscale`).
2. **Compare**: for each analysis, what does its current Job say? `active`, `complete`, `failed`?
3. **Act**: create the next object if it's time; otherwise do nothing.

Why this shape, rather than "create Job, then block until done, then create the next"?
- It handles **any number of analyses** with one loop.
- It never trusts its memory of what it did: it **looks at the cluster again** each tick. If a call
  fails or the API was slow, the next tick simply tries again.
- Actions are **idempotent**: creating something that already exists (HTTP 409) is treated as fine.

This is exactly how Kubernetes' own controllers work (the ReplicaSet controller from chapter 2:
"want 3, see 2, create 1"). You're writing a mini controller.

## Run it

Three terminals. All commands from the repo root.

### Setup (once)
```sh
uv venv services/api/.venv
uv pip install --python services/api/.venv/bin/python -r services/api/requirements.txt
kubectl apply -f k8s/base/namespace.yaml
```

### Terminal 1: the API
```sh
WORKER_DURATION_MIN=3 WORKER_DURATION_MAX=8 \
  services/api/.venv/bin/uvicorn app.main:app --app-dir services/api --port 8000
```
(Short durations so you don't wait; remove them for the default 5–15 s.)

### Terminal 2: watch the cluster
```sh
k9s -n analyses          # :jobs  :pods  :pvc
```

### Terminal 3: be the user

**1. One analysis**
```sh
curl -s -X POST localhost:8000/api/analyses | python3 -m json.tool
curl -s localhost:8000/api/analyses | python3 -m json.tool      # repeat: queued → aligning → calling → succeeded
```
👀 In terminal 1 the log tells the story: `queued` → `started: created PVC + align Job` →
`align complete: created call Job` → `succeeded`. In k9s: a PVC, then one pod, then another.
Final JSON: `align.node` == `call.node`, and `result.input_from` is the align pod.

Also open **http://localhost:8000/api/docs** in your browser: FastAPI generates an interactive page
where you can click "Try it out" on every endpoint.

**2. The max-5 rule**
```sh
curl -s -X POST 'localhost:8000/api/analyses?count=8' > /dev/null
while true; do curl -s localhost:8000/api/stats; echo; sleep 1; done    # ctrl-c to stop
```
👀 `aligning + calling` never exceeds 5; `queued` drains as slots free up. In k9s, never more than 5 running pods.

**3. Layers: kill a pod**
Start one analysis, and while it's `aligning`, delete its pod (`ctrl-d` in k9s, or `kubectl delete pod ... -n analyses`).
👀 The **Job controller** makes a new pod; the analysis still succeeds. Our orchestrator did
nothing: it only looks at the *Job*. Each layer handles its own failures.

**4. A different limit**
Stop the API (ctrl-c) and restart it with `MAX_RUNNING=2` in front. Submit 6. Watch `/stats`.

**5. The weakness: kill the API mid-run**
Submit 3, and while they run, stop the API with ctrl-c. Then:
```sh
kubectl get jobs,pvc -n analyses      # still there! running pods finish their step
```
Restart the API, then `curl -s localhost:8000/api/analyses` → `[]`. It **forgot everything**: the queue
was in memory. The align Jobs finish, but nobody creates the call Jobs, and the PVCs are orphaned.
Clean up by label:
```sh
kubectl delete jobs,pvc -n analyses -l app=toyscale
```
👀 Kubernetes kept its state (it lives in etcd); our app didn't. We fix this in chapter 8 by
rebuilding state from Kafka. This is also why real controllers store their state *in the cluster*.

## A question to carry into chapter 6
The API created Jobs and deleted PVCs. **Who allowed it to?** Right now it uses your
`~/.kube/config`, which is cluster-admin: it could delete every namespace. Inside the
cluster it will get its own identity with only the permissions it needs.

## Checkpoint
- 8 submitted → never more than 5 running → all `succeeded`.
- Self-check: which function enforces max 5? What does the orchestrator do when a Job is still
  `active`? Why is creating a Job that already exists not an error for us? What is lost when
  the API restarts, and what isn't?

Stop the API with ctrl-c when you're done. You can leave the `analyses` namespace: chapter 6 uses it.
