class CanvasBotError(Exception):
    """Base application error."""


class UnsupportedDesignError(CanvasBotError):
    """The prompt requests a design category outside the supported MVP."""


class PipelineError(CanvasBotError):
    """A generation stage failed."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
