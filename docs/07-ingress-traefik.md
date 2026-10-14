# Chapter 7: The front door (Traefik + Ingress, with Terraform and Helm)

Code: [`terraform/02-platform/`](../terraform/02-platform/), [`k8s/base/api-ingress.yaml`](../k8s/base/api-ingress.yaml)

Goal: replace the `port-forward` tunnel with a permanent address, **`http://localhost/api/...`**.
(Kafka comes in the next part, separately.)

## The three pieces

| Piece | What it is | Who made it |
|---|---|---|
| **Service** `api` | a stable *internal* address for the API pods (chapter 2) | us (chapter 6) |
| **Ingress** `api` | a **rule**: "requests whose path starts with `/api` → Service `api`" | us (this chapter) |
| **Traefik** | a program (an *ingress controller*) that receives HTTP traffic and **applies** the Ingress rules | someone else; we install it with **Helm** |

An Ingress alone does nothing; it's an entry in an address book. Traefik reads the book.

```
browser: http://localhost/api/stats
  → port 80 on your Mac
  → kind port mapping (chapter 1, extra_port_mappings) → control-plane node, port 80
  → Traefik pod (hostPort 80)        reads Ingress rules: "/api → Service api"
  → Service api → API pod            FastAPI serves /api/stats
```
The path is passed through unchanged, so all API routes now start with `/api`
(API image `0.1.2`; `/api/docs` for the interactive page).

## Helm, in one paragraph
A **chart** is a package of Kubernetes YAML templates with blanks, made by someone else
(here: the Traefik team). **Values** are your answers to the blanks. Helm fills them in,
sends plain YAML to the cluster, and remembers what it installed as a **release**
(`helm list -A`). Like Homebrew, for a cluster.

## The second Terraform stack
`terraform/02-platform/` is a **second stack on the same cluster**, with its own state.

| File | What it does |
|---|---|
| `versions.tf` | the `helm` provider, plus a `terraform_remote_state` **data source** that reads stack 01's outputs to find the kubeconfig |
| `traefik.tf` | one `helm_release`: chart `traefik` version `41.7.1`, with our **values** |
| `outputs.tf` | the URL to try |

The values in `traefik.tf`, line by line:
- `nodeSelector` + `tolerations`: run on the **control-plane** node (that's where port 80 is mapped), despite its taint.
- `ports.web.hostPort = 80`: bind directly on the node's port 80.
- `service.spec.type = ClusterIP`: no cloud load balancer in kind (see the first pitfall below).
- `updateStrategy` `maxSurge 0`: stop the old pod before starting a new one, since two pods can't share a hostPort.
- `ingressClass`: make Traefik the default handler for Ingress objects.

## Run it
```sh
make platform                    # terraform init + apply in terraform/02-platform (type yes)
kubectl get pods -n traefik -o wide        # on toyscale-control-plane
helm list -A                               # the release Terraform created
kubectl get ingress -n toyscale            # our rule (deployed by make up in chapter 6/7)
curl localhost/api/stats
curl -X POST 'localhost/api/analyses?count=3'
open http://localhost/api/docs             # in your browser
curl -i localhost/                         # 404: no rule for "/" yet (the UI, chapter 9)
```

## Two real pitfalls we hit while building this
Both are worth knowing because they happen in real jobs.

**1. A wrong value name is silently ignored.** The first attempt said `service = { type = "ClusterIP" }`.
This chart wants `service.spec.type`. Helm didn't complain; it just used the default, `LoadBalancer`.
On kind, a LoadBalancer Service waits forever for an external IP (`EXTERNAL-IP <pending>`); Terraform's
Helm install waits for everything to be ready, gave up after 5 min, and marked the release `failed`.
→ Always check the chart's real keys: `helm show values traefik/traefik --version 41.7.1`.

**2. A failed apply can leave reality and state out of sync.** That failed install left a Helm release
in the cluster but **not** in Terraform's state. The next apply tried to create it again:
`cannot re-use a name that is still in use`. The fix was to remove the orphan (`helm uninstall traefik -n traefik`)
and apply again. (Alternative: `terraform import`, which adopts an existing object into the state.)

## Experiments
1. **Break the rule:** in `api-ingress.yaml`, change `path: /api` to `/backend`, `kubectl apply -k k8s/base`.
   `curl -i localhost/api/stats` → 404 from Traefik. Put it back.
2. **No controller, no routing:** `terraform -chdir=terraform/02-platform destroy`. The Ingress object still exists
   (`kubectl get ingress -A`) but nothing reads it: `curl localhost/api/stats` → connection refused. `make platform` again.
3. **Look at what Helm generated:** `helm get manifest traefik -n traefik | less`. That's the plain YAML
   you didn't have to write.

## Checkpoint
- `curl localhost/api/stats` answers without any port-forward.
- Self-check: what's the difference between an Ingress and Traefik? Why does Traefik run on the
  control-plane node? How does stack 02 know which cluster to talk to?
