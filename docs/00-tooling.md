# Chapter 0 — Tooling

## The big picture: what is each tool for?

| Tool | Layer | Role |
|------|-------|------|
| **Docker (OrbStack)** | container runtime | Builds images and runs containers on *one* machine. |
| **kind** | cluster | "Kubernetes IN Docker": each Kubernetes *node* is a Docker container. A real multi-node cluster on your laptop, disposable in seconds. |
| **kubectl** | client | The CLI that talks to the Kubernetes API server. Everything (get, apply, logs, exec) goes through it. |
| **helm** | packaging | Package manager for Kubernetes ("apt for k8s"). A *chart* = templated YAML + default values. We'll install Kafka, Traefik, Prometheus with it. |
| **terraform** | infrastructure as code | Declares *what should exist* (cluster, helm releases) and reconciles reality to match. Keeps a *state* file of what it created. |
| **k9s** | UI | Terminal dashboard for the cluster: watch pods appear live, read logs, exec in. Your best friend in this tutorial. |
| **kustomize** | config | Patches plain YAML per environment without templates (built into `kubectl -k` too). |

**Runtime vs. orchestrator:** Docker answers "run this container here". Kubernetes
answers "keep N copies of this running *somewhere* in a fleet of machines, restart
them when they die, give them a stable network name, mount their storage". Kubernetes
doesn't run containers itself — each node has a runtime (containerd) that does.

## Install

```sh
brew install kubectl kind helm k9s kustomize
```

Start **OrbStack**, then in *Settings → System* give it **6–8 GB RAM** (Kafka + Prometheus are hungry).
Do **not** enable OrbStack's built-in Kubernetes — we use kind instead.

## Checkpoint

```sh
docker info --format '{{.NCPU}} CPUs, {{.MemTotal}} bytes RAM'
kind version
kubectl version --client
helm version
terraform version
```

All five commands print a version / info without error → ready for chapter 1.
