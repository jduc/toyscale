# The build → load → deploy loop, so you don't retype it every time.
# Usage: make build load deploy     (or just: make up)

CLUSTER    := toyscale
WORKER_TAG := 0.1.0
API_TAG    := 0.1.1

.PHONY: build load deploy up logs undeploy

build: ## build both images
	docker build -t toyscale-worker:$(WORKER_TAG) services/worker
	docker build -t toyscale-api:$(API_TAG) services/api

load: ## copy the images into every kind node
	kind load docker-image toyscale-worker:$(WORKER_TAG) toyscale-api:$(API_TAG) --name $(CLUSTER)

deploy: ## set the image tag, apply the manifests, restart the API so it picks up a reloaded image
	cd k8s/base && kustomize edit set image toyscale-api=toyscale-api:$(API_TAG)
	kubectl apply -k k8s/base
	kubectl rollout restart deployment/api -n toyscale
	kubectl rollout status deployment/api -n toyscale

up: build load deploy

logs: ## follow the API logs
	kubectl logs -f deployment/api -n toyscale

undeploy: ## delete everything from k8s/base (both namespaces!)
	kubectl delete -k k8s/base
