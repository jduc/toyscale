# Kubernetes basics: a playground

Concepts: [docs/02-first-workload.md](../../docs/02-first-workload.md). Read it first (5 min).

The app we run is `traefik/whoami`: a tiny web server that replies with **its own pod
name and IP**. That makes it perfect for seeing *which* pod answered.

```sh
cd playground/k8s-basics
```
💡 Keep **k9s** open in a second terminal the whole time (`k9s -n playground`), so you
watch things appear and disappear live.

---

### Step 1: a namespace
```sh
kubectl apply -f namespace.yaml
kubectl get namespaces            # yours, plus kube-system, local-path-storage...
```

### Step 2: a pod, the imperative way
```sh
kubectl run quick --image=traefik/whoami:v1.11 -n playground
kubectl get pods -n playground -o wide      # STATUS Running, and which NODE?
kubectl describe pod quick -n playground    # scroll to Events at the bottom
```
👀 The Events tell the whole life story: `Scheduled` (the scheduler picked a node) →
`Pulling` the image → `Created` → `Started`. When something breaks later,
**`describe` + Events is the first place to look.**

```sh
kubectl delete pod quick -n playground
kubectl get pods -n playground              # gone. Forever. Nobody recreates it.
```

### Step 3: a pod, the declarative way (YAML)
Open `pod.yaml` and find the 4 parts: `apiVersion`, `kind`, `metadata`, `spec`.
```sh
kubectl apply -f pod.yaml
kubectl get pod lonely -n playground -o yaml | less
```
👀 Kubernetes added a lot: a `uid`, a `nodeName` (filled in by the scheduler), and a whole
`status:` section with the pod IP. **You write `spec`; Kubernetes writes `status`.**

Talk to it through a tunnel from your Mac:
```sh
kubectl port-forward pod/lonely -n playground 8080:80   # leave running, ctrl-c to stop
# in another terminal:
curl localhost:8080          # Hostname: lonely, IP: 10.244.x.x
```
Then, ✍️ **edit the YAML**: in `pod.yaml`, change the label to `app: alone`, and run
`kubectl apply -f pod.yaml` again. It says `configured`: same object, updated in place.

### Step 4: a Deployment, with self-healing
Open `deployment.yaml`. Find the **`template`**: it's a pod spec inside the Deployment.
```sh
kubectl apply -f deployment.yaml
kubectl get deploy,replicaset,pods -n playground -o wide
```
👀 There are 3 pods named `web-<replicaset-hash>-<random>`. Look at the NODE column: the
scheduler **spread them** over `toyscale-worker` and `toyscale-worker2`.

Now kill one (copy a real pod name from the list):
```sh
kubectl delete pod web-xxxxxxxxx-yyyyy -n playground
kubectl get pods -n playground              # still 3! a new one, a few seconds old (AGE)
```
👀 Compare with step 2. The **ReplicaSet controller** saw "want 3, have 2" and created one.
That's the reconcile loop: Terraform-like desired state, but enforced **continuously**.

### Step 5: scaling, imperative vs. declarative
```sh
kubectl scale deployment web --replicas=5 -n playground
kubectl get pods -n playground              # 5
kubectl apply -f deployment.yaml            # the file says 3...
kubectl get pods -n playground              # ...back to 3
```
👀 Same lesson as Terraform's step 6: **the file is the truth.** Imperative commands are
fine for experiments, but the next `apply` overrides them. ✍️ To scale "for real", change
`replicas:` in the file and apply.

### Step 6: a Service, for a stable name and load balancing
```sh
kubectl apply -f service.yaml
kubectl get svc web -n playground                    # a CLUSTER-IP, 10.96.x.x
kubectl get endpointslices -n playground             # the pod IPs behind it
```
Call it **from inside the cluster**, by name, 6 times, using a throwaway pod with curl:
```sh
kubectl run client --rm -it --restart=Never -n playground \
  --image=curlimages/curl -- sh -c 'for i in 1 2 3 4 5 6; do curl -s web | grep Hostname; done'
```
👀 Different hostnames answer: the Service **load-balances** across the 3 pods.
And `web` resolved by name: cluster DNS (the `coredns` pods you saw in chapter 1).
The full name is `web.playground.svc.cluster.local`.

Is `lonely` behind the Service? Why not? (Hint: `selector`.) ✍️ Try:
```sh
kubectl label pod lonely app=web --overwrite -n playground
kubectl get endpointslices -n playground             # one more IP!
```
Re-run the curl loop: `lonely` now answers too. The Service doesn't care who created a pod,
**only about labels**. Undo it with `kubectl delete pod lonely -n playground`.

### Step 7: a rolling update
✍️ In `deployment.yaml`, change `WHOAMI_NAME` from `"v1"` to `"v2"`, then:
```sh
kubectl apply -f deployment.yaml && kubectl rollout status deployment web -n playground
kubectl get replicasets -n playground       # 2 ReplicaSets: old one scaled to 0, new one at 3
```
👀 Kubernetes replaced pods **one by one**: start a new one, wait until it's ready, stop an
old one. The Service always had pods to send traffic to, so there was zero downtime.
Then roll back:
```sh
kubectl rollout undo deployment web -n playground
```

### Step 8: clean up
```sh
kubectl delete namespace playground         # deletes EVERYTHING inside it
kubectl get all -n playground               # No resources found
```

---

### 🧠 Self-check
1. You delete a pod. When does it come back, and when doesn't it?
2. Which object gives your app a stable address, and how does it find its pods?
3. In `kubectl get pod -o yaml`, which part did you write and which did Kubernetes write?
4. You run `kubectl scale --replicas=10` and then `kubectl apply -f deployment.yaml`. How many pods?
5. Why can't you curl the Service `web` directly from your Mac's terminal? (Hint: `ClusterIP`.)
