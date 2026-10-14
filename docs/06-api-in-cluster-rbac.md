# Chapter 6: The API inside the cluster (RBAC, quotas, probes)

Code: [`services/api/Dockerfile`](../services/api/Dockerfile), [`k8s/base/`](../k8s/base/), [`Makefile`](../Makefile)

In chapter 5 the API ran on your Mac with **your** admin credentials. Now it runs as a pod,
with **its own identity** and only the permissions it needs.

```
 namespace "toyscale"                         namespace "analyses"
 ┌──────────────────────────────┐            ┌──────────────────────────────────────────┐
 │ Deployment api (1 replica)   │  creates   │ PVCs, Jobs, Pods                          │
 │   pod runs as ServiceAccount ├──────────► │                                          │
 │   "api"                      │  allowed   │ Role "orchestrator" + RoleBinding → api  │
 │ Service api :80 → pod :8000  │  by RBAC   │ ResourceQuota: max 5 pods, 10 PVCs       │
 └──────────────────────────────┘            └──────────────────────────────────────────┘
```

Two namespaces on purpose: **the app** (`toyscale`) and **the work it creates** (`analyses`).
That way the work gets its own permissions and its own quota.

## 1. Identity: ServiceAccount
People authenticate with a kubeconfig; **pods authenticate with a ServiceAccount**.
`serviceAccountName: api` in the Deployment makes Kubernetes mount a token into the pod at
`/var/run/secrets/kubernetes.io/serviceaccount/`. The Python client's `load_incluster_config()`
(in `k8s.py`) reads it. Same code as chapter 5, different credentials: that's why `connect()`
tries in-cluster first, then `~/.kube/config`.

## 2. Permissions: RBAC
Read [`api-rbac.yaml`](../k8s/base/api-rbac.yaml). Three objects:

| Object | Answers | Here |
|---|---|---|
| **ServiceAccount** | WHO | `api` in `toyscale` |
| **Role** | WHAT, and WHERE (its namespace) | create/list/delete Jobs; create/delete PVCs; list pods; read pod logs, in `analyses` only |
| **RoleBinding** | gives the Role to the subject | `api` → `orchestrator` |

- Everything not listed is **denied** (HTTP 403 Forbidden). There's no "deny" rule; you only grant.
- `apiGroups`: the part before `/` in `apiVersion`. `batch/v1` → `"batch"`; plain `v1` → `""` (core).
- `pods/log` is a **sub-resource**: reading logs is a separate permission from reading pods.
- **Role vs ClusterRole:** a Role is valid in one namespace; a ClusterRole (with a ClusterRoleBinding)
  is cluster-wide. Our API never needs cluster-wide power, so it doesn't get it.
- **Least privilege:** the rules are *exactly* the calls in `k8s.py`. When a feature needs a new call,
  the Role grows (this chapter added `delete` on Jobs, see the bug story below).

Ask Kubernetes what an identity may do, impersonating it with `--as`:
```sh
kubectl auth can-i create jobs -n analyses --as=system:serviceaccount:toyscale:api    # yes
kubectl auth can-i create jobs -n default  --as=system:serviceaccount:toyscale:api    # no
kubectl auth can-i list secrets -n analyses --as=system:serviceaccount:toyscale:api   # no
kubectl auth can-i get pods --subresource=log -n analyses --as=system:serviceaccount:toyscale:api   # yes
kubectl auth can-i --list -n analyses --as=system:serviceaccount:toyscale:api          # everything at once
```

## 3. Guardrail: ResourceQuota
[`analyses-quota.yaml`](../k8s/base/analyses-quota.yaml) caps the `analyses` namespace at **5 live pods**
(plus CPU, memory and 10 PVCs), whoever asks. Two layers enforce "max 5":

| Layer | Where | If exceeded |
|---|---|---|
| App | `MAX_RUNNING` in the orchestrator | the analysis waits in the queue (nice: the user sees "queued") |
| Cluster | ResourceQuota | creating the pod is **refused** (`exceeded quota`); the Job controller keeps retrying |

The app layer gives a good user experience; the cluster layer protects the cluster from bugs and
misconfiguration. You'll see the cluster layer catch a misconfigured app in exercise 5.

Side effect: once a namespace has a quota on `requests.cpu`/`requests.memory`, **every pod in it must
declare requests**, or it is refused. Ours do (`resources:` in `job_manifest()`).

## 4. Health: probes
The Deployment calls `GET /api/healthz`:
- **readinessProbe** failing → the pod is removed from the Service (no traffic), but not restarted.
- **livenessProbe** failing → the container is **restarted**.
You saw them in chapter 5's logs as `GET /api/healthz 200` every few seconds.

## 5. Why exactly one replica, and `strategy: Recreate`
The orchestrator keeps its queue **in memory**. With 2 replicas, each pod would have its own queue,
the Service would spread requests between them, and each would allow 5 running: 10 total, and
`GET /analyses` would show different lists depending on which pod answers.
`Recreate` stops the old pod before starting the new one during an update, so two orchestrators
never overlap. (Real controllers solve this with **leader election**; we get there in chapter 11.)

## 6. Packaging: Kustomize and the Makefile
- `kubectl apply -k k8s/base` applies everything listed in `kustomization.yaml`, and its `images:` section
  sets the API's tag in one place.
- `make up` = `build` (both images) → `load` (into kind) → `deploy` (set the tag, apply, restart the API).
- **Bumping the tag** (`API_TAG` in the Makefile) is how you ship a new version. `0.1.0` → `0.1.1` happened
  in this chapter because of…

## 🐛 The bug we hit: finalizers
The first in-cluster test left every PVC stuck in `Terminating`. Cause:
```sh
kubectl get pvc <name> -n analyses -o jsonpath='{.metadata.finalizers}'   # ["kubernetes.io/pvc-protection"]
```
A **finalizer** is a "don't delete me yet" flag. `pvc-protection` keeps a PVC alive while **any pod object
uses it, even a Completed one**. Our Completed pods lived until their Job's `ttlSecondsAfterFinished` (10 min),
so disks piled up, hit the quota's 10 PVCs, and then *every* `create_pvc` failed with 403, which crashed the
whole tick, freezing all analyses.

Fix (API `0.1.1`):
1. On success, delete the analysis' **Jobs** first (with their pods), then the PVC: it disappears in seconds.
2. Handle each analysis in its own `try`: a failure only delays that analysis.

Finalizers are behind most "why is my object stuck in Terminating?" questions. Remember `-o jsonpath='{.metadata.finalizers}'`.

## Run it

### Deploy
```sh
make up                                    # build, load, deploy
kubectl get all -n toyscale                # deployment, replicaset, pod, service
make logs                                  # API logs (ctrl-c)
```

### Exercise 1: who is the API?
Run the `kubectl auth can-i` commands above. Then look at the token mounted in the pod:
```sh
kubectl exec -n toyscale deploy/api -- ls /var/run/secrets/kubernetes.io/serviceaccount/
```

### Exercise 2: use it
```sh
kubectl port-forward -n toyscale svc/api 8080:80     # terminal A (leave running)
curl -s -X POST 'localhost:8080/api/analyses?count=8'    # terminal B
curl -s localhost:8080/api/stats
```
Watch with `k9s -n analyses`. Note: a port-forward is attached to **one pod**; after a redeploy,
restart it.

### Exercise 3: take away a permission
✍️ In `k8s/base/api-rbac.yaml`, remove `"create"` from the `jobs` verbs. Then:
```sh
kubectl apply -k k8s/base
curl -s -X POST localhost:8080/api/analyses
make logs                                  # "...: Forbidden, will retry" every second
```
👀 The PVC was created (still allowed), the Job wasn't; the analysis stays `queued`. Put `"create"` back,
`kubectl apply -k k8s/base`, and it starts on the next tick, without restarting the API: RBAC is checked on every call.

### Exercise 4: the quota catches a misconfigured app
```sh
kubectl set env deployment/api -n toyscale MAX_RUNNING=8     # oops, a "bad config" (restarts the pod)
# restart the port-forward, then:
curl -s -X POST 'localhost:8080/api/analyses?count=8'; sleep 10
curl -s localhost:8080/api/stats                                   # the app thinks 8 are aligning...
kubectl get pods -n analyses                                   # ...but only 5 pods exist
kubectl get events -n analyses --field-selector reason=FailedCreate | head -3   # "exceeded quota"
kubectl describe resourcequota -n analyses                     # used vs hard
```
👀 All 8 still finish: the Job controller retries until quota frees up. Undo the bad config the declarative way:
`kubectl apply -k k8s/base` (the file says 5).

### Exercise 5: the "bug" by hand
Run one analysis, and once it's `aligning`, delete its PVC: `kubectl delete pvc <name> -n analyses --wait=false`.
`kubectl get pvc -n analyses` → `Terminating`, until the pod using it is gone. That's pvc-protection.
This analysis will end up `failed` (its call pod can't mount a disk being deleted, and hits the Job's 5-minute deadline): expected.

## Checkpoint
- `make up` deploys; 8 analyses through the in-cluster API all succeed; at the end
  `kubectl get pvc,jobs -n analyses` is empty.
- Self-check: how does the API pod authenticate? Which object says *where* a permission applies? What
  happens when the app asks for more pods than the quota allows? Why not 2 replicas? What is a finalizer?

Leave it deployed: chapter 7 builds the platform around it.
