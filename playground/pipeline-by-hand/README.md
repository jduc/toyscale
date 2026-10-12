# The pipeline by hand: a playground

Concepts: [docs/04-pipeline-jobs-pvc.md](../../docs/04-pipeline-jobs-pvc.md).
Prerequisite: `toyscale-worker:0.1.0` is loaded into kind (chapter 3, step 5).

```sh
cd playground/pipeline-by-hand
```
💡 Keep `k9s -n analyses` open. Useful views: `:jobs`, `:pods`, `:pvc`, `:pv`.

---

### Step 1: a namespace and a disk claim
```sh
kubectl apply -f namespace.yaml -f pvc.yaml
kubectl get pvc -n analyses                 # STATUS: Pending
kubectl describe pvc data-demo-1 -n analyses | tail -3
```
👀 `waiting for first consumer to be created before binding`. No disk exists yet:
`kubectl get pv` → `No resources found`. Kubernetes waits until it knows **which node** will use it.

### Step 2: the wrong order
What if step 2 starts before step 1?
```sh
kubectl apply -f job-call.yaml
kubectl get pods -n analyses -w             # watch for ~40s, then ctrl-c
```
👀 A pod goes `Error`, then **a new pod** appears and fails, then a third: `backoffLimit: 2` = 1 try + 2 retries,
waiting a bit longer each time (10s, 20s...).
```sh
kubectl get job demo-1-call -n analyses     # STATUS: Failed
kubectl logs -n analyses -l step=call --tail=1 --prefix   # "aligned.json not found: did step 1 (align) run?"
```
Notice too: `kubectl get pvc,pv -n analyses`. The claim is now **Bound**: the failed pod was the
"first consumer", so the disk was created on *its* node.

Clean up the failed Job (Jobs can't just be re-applied):
```sh
kubectl delete job demo-1-call -n analyses
```

### Step 3: step 1
```sh
kubectl apply -f job-align.yaml
kubectl wait --for=condition=complete job/demo-1-align -n analyses --timeout=120s
kubectl logs job/demo-1-align -n analyses
```
👀 `kubectl wait` blocks until the Job's status says `Complete`. That's a human-sized version of
what the orchestrator will do in code: **watch the status, then act**.

### Step 4: step 2, in the right order
```sh
kubectl apply -f job-call.yaml
kubectl wait --for=condition=complete job/demo-1-call -n analyses --timeout=120s
kubectl logs job/demo-1-call -n analyses | tail -1
```
👀 In the last line, `"input_from": "demo-1-align-xxxxx"`: step 2 read the file written by step 1's **pod**.
Two pods, sharing data only through the volume.

### Step 5: why the same node?
```sh
kubectl get pods -n analyses -o wide        # look at the NODE column: all the same!
kubectl get pv -o yaml | grep -A6 nodeAffinity
```
👀 The PV says `values: [toyscale-worker…]`. The disk is a folder on that node, so every pod using
it **must** be scheduled there. You never asked for that; storage decided it.

Prove it's just a folder on the node (the same trick as `crictl` in chapter 3):
```sh
NODE=$(kubectl get pods -n analyses -l step=call -o jsonpath='{.items[0].spec.nodeName}')
docker exec $NODE sh -c 'ls /var/local-path-provisioner/*/ && cat /var/local-path-provisioner/*/variants.json'
```

### Step 6: ✍️ now run analysis "demo-2"
Try running a second analysis. You need a new PVC and two new Jobs, all named `demo-2`:
```sh
sed 's/demo-1/demo-2/g' pvc.yaml job-align.yaml | kubectl apply -f -
kubectl wait --for=condition=complete job/demo-2-align -n analyses --timeout=120s
sed 's/demo-1/demo-2/g' job-call.yaml | kubectl apply -f -
```
👀 It works, but imagine doing that for 50 clicks, with max 5 at a time, retries, and cleanup.
Did `demo-2` land on the same node as `demo-1`? (`kubectl get pods -n analyses -o wide`) That's chapter 5's job:
**a program that generates these objects and does the waiting for you.**

### Step 7: clean up
```sh
kubectl delete namespace analyses
kubectl get pv                              # the PVs are gone too (reclaimPolicy: Delete)
```

---

### 🧠 Self-check
1. Why is a Job, not a Deployment, the right object for an analysis step?
2. Why was the PVC `Pending` in step 1, and what made it `Bound`?
3. Why did both steps of demo-1 run on the same node?
4. What happens when the worker exits with code 1? How many times?
5. Which part of the pipeline did Kubernetes **not** handle for you?
