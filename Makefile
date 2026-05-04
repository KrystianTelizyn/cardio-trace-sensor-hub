# Override at invoke time, e.g. `make build IMAGE=my-registry/gateway:0.2.0`.

IMAGE_NAME := cardio-trace-sensor-hub
IMAGE_TAG := $(or $(IMAGE_TAG),dev)

COMPOSE_FILE ?= docker-compose.dev.yml
AWS_ACCOUNT_ID := 719030484884
AWS_REGION := eu-north-1
.DEFAULT_GOAL := help

.PHONY: help sync dev build compose-up compose-down compose-logs test login build-image tag-image push-image

help: ## Show available targets
	@echo "Targets:"
	@grep -E '^[a-zA-Z0-9_.-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  %-22s %s\n", $$1, $$2}'
	@echo ""
	@echo "Variables: IMAGE=$(IMAGE) COMPOSE_FILE=$(COMPOSE_FILE)"

login: ## Login to ECR for Docker image push/pull
	@echo "Initiating ECR login..."
	aws ecr get-login-password --region $(AWS_REGION) \
		| docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com


sync: ## Install/sync Python dependencies (including dev group)
	uv sync --group dev

dev: ## Start FastAPI in development mode (reload, local only)
	uv run fastapi dev src/app/main.py

compose-up: ## Run Docker Compose (default file: docker-compose.yml; override with COMPOSE_FILE=)
	docker compose -f $(COMPOSE_FILE) up

compose-down: ## Stop and remove Docker Compose containers
	docker compose -f $(COMPOSE_FILE) down

compose-logs: ## Follow Docker Compose service logs
	docker compose -f $(COMPOSE_FILE) logs -f

test: ## Run unit/contract tests
	uv run pytest 

build-image: ## Build sensor hub Docker image
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

tag-image: ## Tag sensor hub Docker image for ECR
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(IMAGE_NAME):$(IMAGE_TAG)

push-image: ## Push sensor hub Docker image to ECR
	docker push $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(IMAGE_NAME):$(IMAGE_TAG)