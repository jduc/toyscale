# ToyScale — learn Kubernetes, Terraform & Kafka by building a mock biology pipeline

A React dashboard launches "analyses". Each analysis is a 2-step pipeline
(`align` → `call`), each step runs in its own Kubernetes pod, at most 5 run at
once, and everything that happens is streamed through Kafka to a live dashboard.
Prometheus/Grafana watch the cluster.

```
 Browser ──► Traefik ──► ui (React)
                     └─► api (FastAPI) ── orchestrator ──► Jobs in ns "analyses"
                               ▲                          (step1 → PVC → step2)
                               └──── Kafka "analysis-events" ◄── workers
```

## Chapters

| #  | Chapter                              | Notes                              | Status |
|----|--------------------------------------|------------------------------------|--------|
| 0  | Tooling                              | [docs/00-tooling.md](docs/00-tooling.md) | ✅ |
| 1  | Cluster with Terraform (kind)        | [docs/01-cluster-terraform.md](docs/01-cluster-terraform.md) | ✅ |
| 1b | Side step: Terraform fundamentals    | [docs/01b-terraform-basics.md](docs/01b-terraform-basics.md) · [playground](playground/terraform-basics/README.md) | ⏳ |
| 2  | First workload by hand               |                                    |        |
| 3  | The worker container                 |                                    |        |
| 4  | 2-step pipeline: Jobs + PVC by hand  |                                    |        |
| 5  | API + orchestrator                   |                                    |        |
| 6  | API in-cluster, RBAC, quotas         |                                    |        |
| 7  | Platform: Traefik, Kafka via Terraform + Helm |                           |        |
| 8  | Event streaming                      |                                    |        |
| 9  | React dashboard                      |                                    |        |
| 10 | Monitoring: Prometheus & Grafana     |                                    |        |
| 11 | Scaling & failure experiments        |                                    |        |
| 12 | Bonus: Argo, MinIO, GitOps, KEDA     |                                    |        |

Each chapter = one git commit, so `git log` / `git show` lets you replay what each step added.
