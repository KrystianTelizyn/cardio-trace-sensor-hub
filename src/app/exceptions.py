class SensorHubException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class PipelineStageError(SensorHubException):
    def __init__(self, *, stage: str, message: str):
        self.stage = stage
        super().__init__(f"[{stage}] {message}")


class ConfigError(SensorHubException):
    pass


class HubNotReadyError(SensorHubException):
    def __init__(self, *, checks: dict[str, bool]):
        self.checks = checks
        super().__init__("Sensor hub is not ready")


class FrameParsingError(SensorHubException):
    pass


class TenantIdentificationError(SensorHubException):
    pass


class BackendApiError(SensorHubException):
    def __init__(self, message: str, *, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class BackendApiValidationError(BackendApiError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message, status_code=status_code)


class DeviceIdentityNotFoundError(SensorHubException):
    pass


class SessionIdentityNotFoundError(SensorHubException):
    pass
