# cardio-trace-sensor-hub

**MQTT ingress service** for the Cardio Trace platform: subscribes to device telemetry over MQTT, bridges it toward the core backend API, and exposes **FastAPI health/readiness** for orchestration. Part of the **Cardio Trace** polyrepo ([platform overview](https://github.com/KrystianTelizyn/cardio-trace-platform)), alongside sibling trees such as [`cardio-trace-backend-api`](../cardio-trace-backend-api), [`cardio-trace-gateway`](../cardio-trace-gateway), and [`cardio-trace-iot-simulation`](../cardio-trace-iot-simulation).

## Role

- **Telemetry edge** — Long-lived subscription to configured MQTT topics; normalizes incoming frames and forwards them to the Django REST backend (integration is incremental; wire-up follows platform contracts).
- **Operational surface** — `GET /healthz` (liveness) and `GET /readyz` (dependency checks) for load balancers and Compose health wiring.
- **Platform integration** — Trusted internal caller pattern matches the backend API expectation (network segmentation; same patterns as gateway header trust for browser traffic).

Upstream publishers (for example **cardio-trace-iot-simulation**) and a Mosquitto-style broker fit the local Compose profile in [`docker-compose.dev.yml`](docker-compose.dev.yml).

## Tech stack

- Python 3.13
- FastAPI + Uvicorn
- [aiomqtt](https://pypi.org/project/aiomqtt/) (MQTT client)
- Redis async client (shared state / buffering as the pipeline evolves)
- [uv](https://docs.astral.sh/uv/) (environments and lockfile)

## Project structure

```
src/app/
  main.py              # FastAPI app factory and lifespan (hub startup/shutdown)
  sensor_hub.py        # Coordinates MQTT ingress, Redis, backend HTTP client
  mqtt_ingress.py      # Subscribes and dispatches payloads to hub logic
  backend_api_client.py
  routes.py            # Health endpoints
  config.py            # Environment-backed settings
  ...
docker-compose.dev.yml # Local Redis, MQTT broker, backend API, simulation, hub
Makefile               # sync, dev, compose, test, image build/tag/push
```

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose (for the bundled dev stack or image builds)

## Development

From this directory:

```bash
cp .env.example .env   # edit MQTT, Redis, backend URL as needed
uv sync --group dev
```

Run the API locally (reload):

```bash
make dev
```

Or:

```bash
uv run fastapi dev src/app/main.py
```

## Environment

Required / commonly set variables (see [`AppSettings`](src/app/config.py) and [`.env.example`](.env.example)):

| Variable | Purpose |
|----------|---------|
| `REDIS_URL` | Redis connection string |
| `BACKEND_API_BASE_URL` | Base URL for the cardio-trace-backend-api |
| `MQTT_HOST` | MQTT broker hostname |
| `MQTT_PORT` | MQTT broker port |
| `MQTT_SUBSCRIBE_PATTERN` | Topic filter (wildcard supported) |
| `HOST`, `PORT` | Bind address/port for Uvicorn (optional; defaults suit containers) |

Compose-only keys in `.env.example` (ports, DB) align with **cardio-trace-backend-api** when using `docker-compose.dev.yml`.

## Docker

Build:

```bash
docker build -t cardio-trace-sensor-hub .
```

Run (pass environment; defaults inside the image listen on `8000`):

```bash
docker run --rm -p 8002:8000 --env-file .env cardio-trace-sensor-hub
```

The image entrypoint starts Uvicorn with `app.main:app`. Extra Uvicorn flags can be appended to the container command.

Local full stack (broker, Redis, Postgres, backend API, simulation, sensor hub):

```bash
docker compose -f docker-compose.dev.yml up
```

Hub HTTP is mapped to **`8002:8000`** in that compose file (override via `.env` if you customize host ports).

## Testing

```bash
make test
```

equivalent to:

```bash
uv run pytest
```

`asyncio_mode` is **auto** in [`pyproject.toml`](pyproject.toml).

## Makefile reference

| Target | Description |
|--------|--------------|
| `sync` | `uv sync --group dev` |
| `dev` | FastAPI dev server with reload |
| `compose-up` / `compose-down` / `compose-logs` | Docker Compose helpers (`COMPOSE_FILE` defaults to `docker-compose.dev.yml`) |
| `test` | Pytest |
| `build-image` / `tag-image` / `push-image` | ECR-oriented image workflow |
| `login` | ECR Docker login |

## License

Proprietary — all rights reserved.
