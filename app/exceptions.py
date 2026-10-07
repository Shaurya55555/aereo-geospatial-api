class IngestionError(Exception):
    """A problem with the uploaded data that the client can fix (maps to HTTP 4xx)."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
