import inspect
from collections.abc import Callable
from app.models import CardioTraceContext
from app.metrics import PIPELINE_MESSAGES_DROPPED_TOTAL
from logging import getLogger

logger = getLogger(__name__)


def handles_pipeline_error(*exc_types: type[Exception], reason: str | None = None):
    """
    Decorator to mark a method as handling specific pipeline errors.
    """

    def decorator(func):
        setattr(func, "__handled_exceptions__", exc_types)
        setattr(func, "__drop_reason__", reason)
        return func

    return decorator


class PipelineStep:
    _error_handlers: list[tuple[type[Exception], Callable, str | None]] | None = None

    async def pre(self, context: CardioTraceContext) -> None:
        return None

    async def run(self, context: CardioTraceContext) -> None:
        raise NotImplementedError

    async def on_error(
        self,
        context: CardioTraceContext,
        exc: Exception,
        fail_reason: str | None = None,
    ) -> None:
        matched_reason = None
        for exc_type, handler, decorator_reason in self._get_error_handlers():
            if isinstance(exc, exc_type):
                dynamic_reason = await handler(context, exc)  # bound method
                matched_reason = dynamic_reason or decorator_reason
                break
        else:
            logger.exception(
                "Error processing message on topic %s: %s", context.topic, exc
            )
        PIPELINE_MESSAGES_DROPPED_TOTAL.labels(
            reason=matched_reason or fail_reason or "unexpected"
        ).inc()

    def _get_error_handlers(self):
        if self._error_handlers is None:
            handlers = []
            for _, method in inspect.getmembers(self, predicate=callable):
                exc_types = getattr(method, "__handled_exceptions__", ())
                drop_reason = getattr(method, "__drop_reason__", None)
                for exc_type in exc_types:
                    handlers.append((exc_type, method, drop_reason))
            self._error_handlers = handlers
        return self._error_handlers
