from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

MQTT_CONNECTED = Gauge(
    "sensor_hub_mqtt_connected",
    "MQTT ingress connection state (1 connected, 0 disconnected).",
)
MQTT_RECONNECTS_TOTAL = Counter(
    "sensor_hub_mqtt_reconnects_total",
    "Total MQTT reconnect attempts after connection loss.",
)

PIPELINE_MESSAGES_PROCESSED_TOTAL = Counter(
    "sensor_hub_pipeline_messages_processed_total",
    "Total messages successfully processed end-to-end.",
)
PIPELINE_MESSAGES_DROPPED_TOTAL = Counter(
    "sensor_hub_pipeline_messages_dropped_total",
    "Total messages dropped by pipeline with categorized reason.",
    labelnames=("reason",),
)
PIPELINE_PROCESSING_SECONDS = Histogram(
    "sensor_hub_pipeline_processing_seconds",
    "End-to-end pipeline processing duration in seconds.",
)

REDIS_CACHE_LOOKUPS_TOTAL = Counter(
    "sensor_hub_redis_cache_lookups_total",
    "Total Redis cache lookups performed by the pipeline.",
)
REDIS_CACHE_HITS_TOTAL = Counter(
    "sensor_hub_redis_cache_hits_total",
    "Total Redis cache lookups that returned a usable value.",
)

BACKEND_ENRICH_REQUESTS_TOTAL = Counter(
    "sensor_hub_backend_enrich_requests_total",
    "Total backend enrich requests by result and status class.",
    labelnames=("result", "status_class"),
)
BACKEND_STORE_REQUESTS_TOTAL = Counter(
    "sensor_hub_backend_store_requests_total",
    "Total backend store requests by result and status class.",
    labelnames=("result", "status_class"),
)


def status_class_from_code(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "2xx"
    if 400 <= status_code < 500:
        return "4xx"
    if 500 <= status_code < 600:
        return "5xx"
    return "exception"


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
