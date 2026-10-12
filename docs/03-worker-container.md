# Chapter 3: The worker container

Code: [`services/worker/`](../services/worker/)

This is where ToyScale itself starts. We write the program that runs **one step** of an
analysis, package it as an image, test the 2-step dependency with plain Docker, and then
copy the image into the cluster.

```
 step 1: STEP=align ──writes──► /data/aligned.json ──read by──► step 2: STEP=call ──writes──► /data/variants.json
```

## The program: `worker.py`

Read it top to bottom (~140 lines). Three design choices matter for Kubernetes:

| Choice | Why |
|--------|-----|
| **Configured by environment variables** (`STEP`, `ANALYSIS_ID`, `DATA_DIR`...) | The same image runs as step 1 *or* step 2. Kubernetes sets env vars per pod in the YAML. One image, many uses. |
| **Exit code = result** (`0` ok, `1` failed, `2` misconfigured) | This is how Kubernetes knows whether a Job succeeded. It never reads your logs; it only looks at the exit code. |
| **Logs as JSON lines on stdout** (`emit()`) | Kubernetes collects stdout as the pod's logs (`kubectl logs`). In chapter 8, `emit()` will also send each event to Kafka. |

Step 2 checks that step 1's output exists and **fails loudly** if not. That's the
output dependency we'll have to respect in Kubernetes: never start `call` before
`align` has succeeded.

## Image vs. container

| | Image | Container |
|--|-------|-----------|
| What | a **frozen package**: filesystem (Python + your code) + the command to run | a **running instance** of an image |
| Analogy | a class / a recipe | an object / the cooked dish |
| Lifetime | built once, stored, versioned with a **tag** (`toyscale-worker:0.1.0`) | started, runs, exits |
| Commands | `docker build`, `docker images` | `docker run`, `docker ps` |

A pod runs containers **from images**. Every node needs a copy of the image.

## The Dockerfile, layer by layer

Each instruction = one **layer** (a filesystem diff), stacked like transparent sheets:
```
 CMD ["python","worker.py"]   ← metadata only
 USER worker                  ← metadata only
 COPY worker.py .             ← ~5 KB, changes often        ┐ rebuilt when worker.py changes
 WORKDIR /app                 ← tiny                         │
 RUN useradd worker           ← tiny                         │ cached ("CACHED" in the build output)
 ENV PYTHONUNBUFFERED=1       ← metadata only                │
 FROM python:3.14-slim        ← ~200 MB, Debian + Python     ┘ downloaded once
```
**Rule:** put what changes rarely at the top and your code at the bottom, so rebuilds take a second.

## Run it

All commands from the repo root.

### 1. Build the image
```sh
docker build -t toyscale-worker:0.1.0 services/worker
docker images toyscale-worker          # ~200 MB, almost all of it is the python base
docker history toyscale-worker:0.1.0   # 👀 the layers, one per Dockerfile line
```
`-t name:tag` names the image. **Always use a real tag, never `:latest`** (we'll see why in step 5).

### 2. Run step 2 first, and watch it fail
```sh
mkdir -p services/worker/data
docker run --rm -e STEP=call -e ANALYSIS_ID=demo \
  -v "$PWD/services/worker/data:/data" toyscale-worker:0.1.0
echo "exit code: $?"                   # 1
```
`-v host_folder:/data` **mounts** a folder from your Mac into the container at `/data`.
Without it, anything the container writes disappears when it exits.

### 3. Run the pipeline in the right order
```sh
docker run --rm -e STEP=align -e ANALYSIS_ID=demo -v "$PWD/services/worker/data:/data" toyscale-worker:0.1.0
docker run --rm -e STEP=call  -e ANALYSIS_ID=demo -v "$PWD/services/worker/data:/data" toyscale-worker:0.1.0
cat services/worker/data/variants.json
```
👀 Two **separate containers**, with different `host` values in the logs, that share data only
through the mounted folder. `input_aligned_by` in `variants.json` proves step 2 used step 1's output.
In chapter 4, the folder becomes a Kubernetes **PersistentVolumeClaim** and each container becomes a **Job**.

### 4. See the layer cache
✍️ Change something small in `worker.py` (e.g. the text `"aligning reads"`), then:
```sh
docker build -t toyscale-worker:0.1.1 services/worker
```
👀 Every step says `CACHED` except `COPY worker.py`. The build takes about a second.

### 5. Get the image into the cluster
Your nodes are separate machines (containers). **They can't see images on your Mac.** In
chapter 2 they downloaded `traefik/whoami` from Docker Hub; our image isn't on any registry.
First, see it fail:
```sh
kubectl run nope --image=toyscale-worker:0.1.0 --restart=Never --env=STEP=align
kubectl get pod nope                     # ErrImagePull / ImagePullBackOff
kubectl describe pod nope | tail -5      # "pull access denied ... repository does not exist"
kubectl delete pod nope
```
Then copy the image into every node:
```sh
kind load docker-image toyscale-worker:0.1.0 --name toyscale
docker exec toyscale-worker crictl images | grep toyscale   # now it's on the node
```
In real life you `docker push` to a **registry** (Docker Hub, AWS ECR...) and nodes pull from there.
`kind load` is a local shortcut.

**Why not `:latest`?** With a `:latest` tag, Kubernetes defaults to `imagePullPolicy: Always`:
it ignores the copy on the node and tries to download it, which fails here. With a real tag it
uses `IfNotPresent` and finds the loaded copy. Real tags also tell you *exactly* which code is running.

### 6. Run one step as a pod
```sh
kubectl run align-test --image=toyscale-worker:0.1.0 --restart=Never \
  --env=STEP=align --env=ANALYSIS_ID=k8s-1 --env=DATA_DIR=/tmp/data
kubectl get pod align-test -w            # Running → Completed  (ctrl-c)
kubectl logs align-test                  # host = the pod name
kubectl delete pod align-test
```
👀 `--restart=Never` + `Completed`: this is **run-to-completion** work, not a server like
`whoami`. That's exactly what Kubernetes **Jobs** are for (next chapter).

(`DATA_DIR=/tmp/data` because there's no volume yet: the container's own disk, thrown away with the pod.)

## Checkpoint
- `kubectl logs align-test` showed `step.started` → `step.progress` ×5 → `step.completed`.
- Self-check: why does step 2 running alone fail? Why can't the node use an image you just built?
  What decides whether Kubernetes thinks a step succeeded?

Clean up: `rm -rf services/worker/data` (it's git-ignored anyway).
