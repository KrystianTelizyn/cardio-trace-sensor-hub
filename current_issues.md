## Code Smells & Refactoring Opportunities

### 1. Bug: Wrong variable in error message

This is an actual bug, not just a smell. In `sensor_hub.py`, the `identify_tenant` error message references `mqtt_subscribe_pattern` but the pattern used for matching is `tenant_extraction_regex`:

```73:77:src/app/sensor_hub.py
        if match:
            context.tenant_id = match.group(1)
        else:
            raise TenantIdentificationError(
                f"Could not extract tenant_id from topic '{context.topic}' using pattern '{self.settings.mqtt_subscribe_pattern}'"
```

Should reference `self.settings.tenant_extraction_regex` instead.

---

### 2. `SensorHub` is a God Object

`SensorHub` owns MQTT ingress, Redis, the backend API client, and the parser chain, while also containing all pipeline business logic (tenant identification, device discovery, backend enrichment, record saving). It has too many responsibilities.

Consider extracting the pipeline stages into a dedicated `Pipeline` or `MessageProcessor` class that receives its dependencies via constructor injection, leaving `SensorHub` as a thin orchestrator that wires infrastructure together.

---

### 3. Pydantic payload models use untyped `dict` throughout

All three payload models (`ApplePayload`, `GarminPayload`, `EhrPayload`) declare their nested structures as `dict` and then do manual validation inside `@model_validator`:

```88:99:src/app/parsers/frame_parsers.py
class ApplePayload(BaseModel):
    deviceInfo: dict
    measurement: dict

    @model_validator(mode="after")
    def check_structure(self) -> ApplePayload:
        if "deviceId" not in self.deviceInfo:
            raise ValueError("missing deviceInfo.deviceId")
        m = self.measurement
        if "timestamp_iso" not in m or "heart_rate" not in m or "hrv" not in m:
            raise ValueError("missing required measurement fields")
```

This defeats the purpose of Pydantic. These should be properly typed nested models (e.g., `AppleDeviceInfo(BaseModel)` with a `deviceId: str` field). You'd get validation, documentation, and IDE support for free, and could eliminate all the manual `model_validator` code.

---

### 4. Double validation in the parser chain

`parsing_applicable` fully validates the payload with Pydantic, and then `parse` validates the exact same bytes again on the winning parser. Every incoming message is validated **N+1 times** (once per parser for routing, plus once more to actually parse):

```47:60:src/app/parsers/frame_parsers.py
    def parsing_applicable(self, context: CardioTraceContext) -> bool:
        try:
            self.payload_model.model_validate_json(context.raw)
            return True
        except ValidationError:
            return False

    def parse(self, context: CardioTraceContext) -> CardioTraceContext:
        try:
            payload = self.payload_model.model_validate_json(context.raw)
        except ValidationError as exc:
            raise FrameParsingError(str(exc)) from exc
```

A simple fix: have `parsing_applicable` cache the validated result (or combine detection and parsing into a single `try_parse` method that returns `Optional[CardioTraceContext]`).

---

### 5. Using exceptions for control flow

Related to the above -- `parsing_applicable` uses `try/except ValidationError` as a branching mechanism. This is an anti-pattern. A lighter discriminator approach (e.g., checking a top-level key like `"header"` vs `"deviceInfo"` vs `"meta"`) would be faster and more explicit.

---

### 6. Sentinel values are identical strings

Both sentinels resolve to the same `"NONE"` string:

```19:20:src/app/sensor_hub.py
DEVICE_NOT_FOUND_SENTINEL = "NONE"
SESSION_NOT_FOUND_SENTINEL = "NONE"
```

They're only distinguishable by which Redis key they came from, but if Redis ever returns `"NONE"` as a legitimate UID, you'd have a collision. Consider using distinct, namespaced values (e.g., `"__NOT_FOUND__DEVICE__"`) or storing a structured JSON value in Redis.

---

### 7. Missing cache write-through after backend enrichment

When `backend_identification` gets a cache miss and successfully calls `enrich`, the result is never written back to Redis. This means every message for that device will always hit the backend API, completely defeating the cache:

```107:117:src/app/sensor_hub.py
        enriched = await self.backend_api_client.enrich(
            serial_number=context.serial_number,
            brand=context.brand,
            tenant_id=context.tenant_id,
        )
        if enriched.device_uid is None:
            raise DeviceIdentityNotFoundError(
                f"Device not registered: {context.brand}/{context.serial_number}"
            )
        if enriched.session_uid is None:
            raise SessionIdentityNotFoundError(
```

After a successful enrich, the device_uid and session_uid should be written to Redis.

---

### 8. f-strings in log calls (eager evaluation)

Several log statements use f-strings, which are evaluated even when the log level is disabled:

```66:70:src/app/sensor_hub.py
        except (DeviceIdentityNotFoundError, SessionIdentityNotFoundError) as e:
            logger.warning(f"Frame dropped on topic {topic}: {e}")
        # Fallback
        except SensorHubException as e:
            logger.exception(f"Error processing message on topic {topic}: {e}")
```

Use lazy `%`-style formatting instead: `logger.warning("Frame dropped on topic %s: %s", topic, e)`.

---

### 9. Dead code: `send_message`

`BackendApiClient.send_message` is declared with an `Ellipsis` body and never called anywhere:

```36:36:src/app/backend_api_client.py
    async def send_message(self, message: str) -> None: ...
```

Remove it or implement it.

---

### 10. `BaseFrameParser._apply` should be abstract

`_apply` raises `NotImplementedError` at runtime but nothing enforces its implementation at definition time. Using `abc.ABC` + `@abstractmethod` would catch missing implementations when the class is defined, not when the code is called in production:

```62:63:src/app/parsers/frame_parsers.py
    def _apply(self, payload: BaseModel, context: CardioTraceContext) -> None:
        raise NotImplementedError
```

---

### 11. No MQTT reconnection logic

If the MQTT broker connection drops, `consume_loop` exits and the task is done. There's no backoff-and-retry loop:

```52:66:src/app/mqtt_ingress.py
    async def consume_loop(self) -> None:
        try:
            async with Client(
                hostname=self.host,
                port=self.port,
            ) as client:
                await client.subscribe(self.subscribe_pattern)
                self.connected = True
                async for message in client.messages:
                    await self.ingress_logic.on_message(
                        message.topic.value, message.payload
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("MQTT ingress loop exited with an error")
            raise
```

A production service should wrap this in a retry loop with exponential backoff.

---

### 12. Incomplete exception handling in `on_message`

The fallback catch only handles `SensorHubException`. Unexpected exceptions (e.g., `httpx.TimeoutException`, `httpx.ConnectError`) will propagate up and could crash the MQTT ingress task:

```63:70:src/app/sensor_hub.py
        except (DeviceIdentityNotFoundError, SessionIdentityNotFoundError) as e:
            logger.warning(f"Frame dropped on topic {topic}: {e}")
        # Fallback
        except SensorHubException as e:
            logger.exception(f"Error processing message on topic {topic}: {e}")
```

Consider adding a bare `except Exception` guard at the end (with appropriate logging) to keep the ingress loop alive.

---

### 13. Field naming inconsistency: `hr` vs `heart_rate`

`CardioTraceContext` uses `hr` while `CardioTraceRecord` uses `heart_rate` for the same concept:

```7:11:src/app/models.py
    measurement_session_id: str
    timestamp: datetime
    heart_rate: float | None
    sdnn: float | None
    rmssd: float | None
```

vs

```24:26:src/app/models.py
    hr: float | None
    sdnn: float | None
    rmssd: float | None
```

Pick one name and use it consistently.

---

### 14. Mixed modeling paradigms without clear reason

`CardioTraceRecord` is a Pydantic `BaseModel` and `CardioTraceContext` is a stdlib `dataclass`. Both are domain models in the same module. The Pydantic model gets `model_dump(mode="json")` for serialization, but the context could also benefit from validation (e.g., ensuring `tenant_id` is set before certain stages). Consider making both Pydantic models, or document why they differ.

---

### 15. `Env` class reinvents `pydantic-settings`

The custom `Env` helper class in `config.py` manually reads from `os.environ` with required/default logic. Since the project already depends on Pydantic (via FastAPI), you could use `pydantic-settings` to get environment variable loading, type coercion, `.env` file support, and validation out of the box.

---

### 16. Circular reference: `SensorHub` passes `self` to `MqttIngress`

```30:35:src/app/sensor_hub.py
        self.mqtt_ingress = MqttIngress(
            settings.mqtt_host,
            settings.mqtt_port,
            settings.mqtt_subscribe_pattern,
            self,
        )
```

This creates a bidirectional dependency that makes unit testing harder (the test fixture already needs to patch `MqttIngress` wholesale). Injecting a callback function `on_message: Callable` instead of the entire `SensorHub` instance would be cleaner and matches the `IngressLogic` protocol more honestly.

---

### 17. `data/rr_records.db` is tracked in the repo

A SQLite database file is checked into version control. This should likely be in `.gitignore`.

---

## Summary (priority order)

| Priority | Issue | Type |
|----------|-------|------|
| **High** | Bug: wrong variable in tenant error message | Bug |
| **High** | Missing cache write-through after enrich | Logic gap |
| **High** | No MQTT reconnection / resilience | Reliability |
| **High** | Incomplete exception handling in `on_message` | Reliability |
| **Medium** | Untyped `dict` in Pydantic payload models | Type safety |
| **Medium** | Double validation in parser chain | Performance |
| **Medium** | `SensorHub` God Object | Architecture |
| **Medium** | `BaseFrameParser._apply` not abstract | Correctness |
| **Low** | f-strings in log calls | Performance |
| **Low** | Dead `send_message` method | Dead code |
| **Low** | Identical sentinel strings | Fragility |
| **Low** | `hr` vs `heart_rate` naming inconsistency | Readability |
| **Low** | Mixed dataclass/Pydantic paradigm | Consistency |
| **Low** | Custom `Env` vs `pydantic-settings` | Simplification |
| **Low** | Circular `self` reference to MqttIngress | Coupling |
| **Low** | `rr_records.db` tracked in git | Hygiene |

Overall the codebase is well-structured for its size -- clean separation of concerns in most places, a solid test suite, and good use of protocols. The highest-impact items to address are the bug, the missing cache write-back, and the resilience gaps (MQTT reconnection and unhandled exceptions in the pipeline). The parser refactoring (typed models, single-pass validation) would be the highest-value medium-term improvement.

---

### Branch 1: `refactor/frame-parsers` (start here)

**Scope:** Everything in `parsers/frame_parsers.py` plus the related model changes.

What goes in:
- Replace untyped `dict` fields in `ApplePayload`, `GarminPayload`, `EhrPayload` with proper nested Pydantic models -- this eliminates all the `@model_validator` manual checking
- Eliminate double validation: combine `parsing_applicable` + `parse` into a single-pass `try_parse` that returns the result or `None`
- Make `BaseFrameParser` use `abc.ABC` + `@abstractmethod` for `_apply`
- Fix `hr` vs `heart_rate` naming inconsistency (touches `models.py` and the parsers)
- Remove `_to_optional_float` from the class (make it a module-level utility or remove it if Pydantic handles coercion natively with typed models)

**Why first:** It's the most self-contained change. It only touches `parsers/`, `models.py`, and their tests. Zero risk of interfering with the other two branches. It also establishes cleaner patterns that the other refactors benefit from.

---

### Branch 2: `refactor/mqtt-resilience` (second)

**Scope:** `mqtt_ingress.py` + the exception handling in `SensorHub.on_message`.

What goes in:
- Add a reconnect loop with exponential backoff in `consume_loop`
- Add a broad `except Exception` guard in `on_message` so a single message failure never kills the ingress task
- Switch f-string log calls to lazy `%`-style formatting (small, but you're already in these files)
- Consider adding a configurable max-retries / backoff ceiling to `AppSettings`

**Why second:** It's also self-contained (just two files), but benefits slightly from the parser refactor being done first since `on_message` calls into the parser chain. If the parser refactor changes what exceptions can surface, you want that settled before hardening the error handling.

---

### Branch 3: `refactor/sensor-hub-decomposition` (last)

**Scope:** Breaking up `SensorHub` into smaller collaborators.

What goes in:
- Extract pipeline logic (`identify_tenant`, `discover_device_specifics`, `backend_identification`, `save_record`) into a `MessagePipeline` or similar class
- `SensorHub` becomes a thin wiring layer: owns lifecycle (`__aenter__`/`__aexit__`), creates dependencies, passes them to the pipeline
- Decouple MqttIngress from SensorHub -- inject a callback or the pipeline directly instead of passing `self`
- Clean up the dead `send_message` method on `BackendApiClient` while you're restructuring
- Remove the sentinel string constants from `sensor_hub.py` module level (move to wherever the cache logic lands, or into a small enum/constants module)

**Why last:** This is the highest-risk refactor -- it reshapes the core wiring of the app. Having the parser and MQTT changes landed first means fewer moving parts when you restructure. It also means the tests from branches 1 and 2 are already green and stable, giving you a solid safety net.

---

### Practical notes

- **Branch off `main` independently** for branches 1 and 2 since they don't overlap. Branch 3 should be based on top of both (or on `main` after both are merged).
- **Keep tests green on each branch.** The parser refactor will require updating `test_frame_parsers.py` substantially. The MQTT branch needs new tests for reconnection behavior. The decomposition branch mostly reorganizes existing tests.
- **The naming bug** (wrong variable in tenant error message) is a one-liner -- I'd just fix it in whichever branch touches `sensor_hub.py` first (probably branch 2 or 3), or even as a standalone commit on `main` before starting.
