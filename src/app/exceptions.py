class SensorHubException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


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
    pass


class BackendApiValidationError(BackendApiError):
    pass


class DeviceIdentityNotFoundError(BackendApiError):
    pass
