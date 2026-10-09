# Chapter 1 — A Kubernetes cluster with Terraform

Code: [`terraform/01-cluster/`](../terraform/01-cluster/)

## What we build

A 3-node Kubernetes cluster running as Docker containers on your Mac:

```
 your Mac ─ localhost:80/443 ─┐
                              ▼
 ┌─ docker ──────────────────────────────────────────────────────┐
 │ toyscale-control-plane   toyscale-worker   toyscale-worker2   │
 │  API server, etcd,        kubelet +          kubelet +         │
 │  scheduler, controllers   containerd         containerd        │
 └───────────────────────────────────────────────────────────────┘
```

## Terraform concepts

| File | Concept |
|------|---------|
| `versions.tf` | **Providers** are plugins that teach Terraform an API (here: kind; later helm, kubernetes). `init` downloads them; `.terraform.lock.hcl` pins exact versions. |
| `variables.tf` | **Inputs** with defaults. Override with `-var worker_count=3` or a `terraform.tfvars` file. |
| `main.tf` | A **resource** = something Terraform creates and owns. `dynamic "node"` generates repeated blocks from a list. |
| `outputs.tf` | **Outputs** = values other stacks/humans read (`terraform output`). |
| `terraform.tfstate` (generated) | The **state**: Terraform's memory of what it created. Never edit, never commit (it can hold secrets). |

The workflow is always: **write → `plan` (diff of desired vs. actual) → `apply` → `destroy`**.

## Kubernetes concepts

- **Control plane**: the *brain*. `kube-apiserver` (the only thing anyone talks to, incl. kubectl),
  `etcd` (the database of desired state), `kube-scheduler` (picks a node for each pod),
  `kube-controller-manager` (loops that make reality match the desired state).
- **Worker node**: the *muscle*. `kubelet` (agent: "run these pods") + container runtime.
- **kubeconfig / context**: `~/.kube/config` holds clusters + credentials; the *context*
  `kind-toyscale` says which one kubectl talks to.

## Run it

```sh
cd terraform/01-cluster
terraform init        # already done once; downloads the kind provider
terraform plan        # read it! "1 to add"
terraform apply       # type "yes" — takes ~1 min
terraform output
```

## Explore

```sh
kubectl config current-context          # kind-toyscale
kubectl get nodes -o wide               # 3 nodes, Ready
docker ps --format '{{.Names}}'         # ...the nodes are just containers!
kubectl get pods -n kube-system -o wide # the control-plane components, running as pods
kubectl get node toyscale-control-plane --show-labels | tr ',' '\n' | grep ingress
k9s                                     # ':nodes', ':pods', '0' = all namespaces, ctrl-c to quit
```

## Experiments

1. **Drift:** `docker stop toyscale-worker2`. Then `kubectl get nodes` → NotReady after ~40s.
   `docker start toyscale-worker2` → Ready again. Kubernetes noticed; Terraform didn't (it only checks on `plan`).
2. **Change = replace:** `terraform plan -var worker_count=3`. Note `-/+ must be replaced`:
   kind can't add nodes to a live cluster, so Terraform destroys and recreates. Not every change is in-place!
3. **Destroy & recreate:** `terraform destroy` then `terraform apply`. Infrastructure as code means
   the cluster is *disposable*: you can always get the same one back.

## Checkpoint

`kubectl get nodes` shows `toyscale-control-plane`, `toyscale-worker`, `toyscale-worker2`, all `Ready`.
