# The build → load → deploy loop, so you don't retype it every time.
# Usage: make build load deploy     (or just: make up)

CLUSTER    := toyscale
WORKER_TAG := 0.2.0
API_TAG    := 0.1.3

.PHONY: build load deploy up logs undeploy platform kafka kafka-down

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

platform: ## install the platform (Traefik...) with Terraform stack 02
	terraform -chdir=terraform/02-platform init -input=false
	terraform -chdir=terraform/02-platform apply

kafka: ## ask Strimzi for our Kafka cluster + topic, and wait until it's ready
	kubectl apply -k k8s/platform/kafka
	kubectl wait kafka/toyscale -n kafka --for=condition=Ready --timeout=600s
	kubectl get pods,pvc -n kafka

kafka-down: ## delete Kafka in the right order: topics first (their operator must still be alive), then the cluster
	kubectl delete -f k8s/platform/kafka/kafka-topic.yaml --ignore-not-found --wait=true
	kubectl delete -f k8s/platform/kafka/kafka-cluster.yaml --ignore-not-found --wait=true
