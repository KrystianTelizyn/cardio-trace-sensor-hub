import inspect
from collections.abc import Callable
from app.models import CardioTraceContext
from app.metrics import PIPELINE_MESSAGES_DROPPED_TOTAL
from logging import getLogger

logger = getLogger(__name__)


def handles_pipeline_error(*exc_types: type[Exception]):
    """
    Decorator to mark a method as handling specific pipeline errors.
    """

    def decorator(func):
        setattr(func, "__handled_exceptions__", exc_types)
        return func

    return decorator


class PipelineStep:
    _error_handlers: list[tuple[type[Exception], Callable]] | None = None

    async def pre(self, context: CardioTraceContext) -> None:
        return None

    async def run(self, context: CardioTraceContext) -> None:
        raise NotImplementedError

    async def on_error(self, context: CardioTraceContext, exc: Exception) -> None:
        for exc_type, handler in self._get_error_handlers():
            if isinstance(exc, exc_type):
                await handler(context, exc)  # bound method
                return
        logger.exception("Error processing message on topic %s: %s", context.topic, exc)
        PIPELINE_MESSAGES_DROPPED_TOTAL.labels(reason="unexpected").inc()

    def _get_error_handlers(self):
        if self._error_handlers is None:
            handlers = []
            for _, method in inspect.getmembers(self, predicate=callable):
                exc_types = getattr(method, "__handled_exceptions__", ())
                for exc_type in exc_types:
                    handlers.append((exc_type, method))
            self._error_handlers = handlers
        return self._error_handlers
