# Chapter 2: First workloads by hand

Hands-on: [playground/k8s-basics/](../playground/k8s-basics/README.md)

Goal: understand the 4 objects everything else is built on: **Namespace, Pod, Deployment, Service**.
This is a throwaway warm-up; ToyScale itself starts in chapter 3.

## The format: YAML manifests

Kubernetes objects are described in **YAML** (where Terraform uses HCL). Every object,
of every kind, has the same 4-part skeleton:

```yaml
apiVersion: apps/v1        # which API group/version defines this kind
kind: Deployment           # WHAT it is            (like Terraform's resource TYPE)
metadata:                  # WHO it is
  name: web                #   unique name per kind + namespace (like Terraform's NAME)
  namespace: playground
  labels: { app: web }     #   free-form tags, used for selection
spec:                      # WHAT YOU WANT (desired state). You write this.
  replicas: 3
status:                    # WHAT IS (actual state). Kubernetes writes this; you never do.
  readyReplicas: 3
```

YAML in 20 seconds: `key: value` for maps, **indentation (spaces, never tabs) = nesting**,
`- item` for lists, and `{ a: b }` / `[x, y]` are inline shortcuts for the same thing.

## Same idea as Terraform, with one key difference

|  | Terraform | Kubernetes |
|--|-----------|------------|
| You write | desired state (`.tf`) | desired state (`spec`) |
| Applied with | `terraform apply` | `kubectl apply -f` |
| Memory of reality | `terraform.tfstate` | `etcd` (+ `status` on each object) |
| Fixes drift | **only when you run it** | **continuously**: controllers loop forever |

That last row is the heart of Kubernetes: **controllers** watch objects and keep acting
until `status` matches `spec`. Delete a pod owned by a Deployment and a new one appears in
about a second, with nobody running a command.

## The four objects

| Object | What it is | Lives on its own? |
|--------|-----------|-------------------|
| **Namespace** | A folder for objects. Names are unique per namespace; `kubectl delete ns X` deletes everything inside. | n/a |
| **Pod** | The smallest unit: 1+ containers sharing an IP and volumes, placed on **one node**. Mortal: if it dies, it's gone. | ✅ but nobody brings it back |
| **Deployment** | "Keep N identical pods running." It creates a **ReplicaSet**, which creates the pods. It handles self-healing, scaling, and rolling updates. | ✅ |
| **Service** | A stable **name + virtual IP** in front of a set of pods (pods come and go, IPs change). Load-balances between them. | ✅ |

```
            Service "web"  (stable DNS name: web, virtual IP 10.96.x.x)
                 │ selector: app=web
     ┌───────────┼───────────┐
   Pod         Pod         Pod      ◄── labels: app=web
   (worker)    (worker2)   (worker)
     ▲───────────┴───────────▲
        ReplicaSet ◄── Deployment "web" (replicas: 3, template: {labels: app=web, ...})
```

## Labels & selectors: the glue

Objects don't point to each other by name. They **select by label**:
- A Deployment's `selector` finds "its" pods via labels from its own `template`.
- A Service's `selector` sends traffic to *any* ready pod with matching labels.

Change a pod's label and it silently leaves the Service, and the Deployment creates a
replacement. You'll do exactly that in the exercises.

## Imperative vs. declarative

| Imperative ("do this") | Declarative ("this should exist") |
|---|---|
| `kubectl run`, `kubectl scale`, `kubectl delete pod` | `kubectl apply -f file.yaml` |
| quick experiments, debugging | the real way: files in git, re-appliable, reviewable |

## Commands cheat sheet
```sh
kubectl get pods -n NS -o wide        # list (+ node, IP)
kubectl get all -n NS                 # pods, deployments, replicasets, services
kubectl describe pod X -n NS          # details + EVENTS at the bottom (read these when stuck!)
kubectl logs X -n NS [-f]             # container stdout
kubectl exec -it X -n NS -- sh        # shell inside the container
kubectl apply -f file.yaml            # create or update to match the file
kubectl delete -f file.yaml           # delete what the file describes
kubectl port-forward svc/X 8080:80    # tunnel localhost:8080 → service port 80
kubectl explain deployment.spec       # built-in docs for any field (like the Terraform registry)
```
