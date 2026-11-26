"""One error type for the whole service, so every error has the same shape.

Every error body looks like this, so a program (or a model) can act on it:
    {"error": "not_found", "detail": "No incident INC-9999", "hint": "Use GET /incidents to find valid IDs"}
"""


class ServiceError(Exception):
    def __init__(self, status_code, error, detail, hint, headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.error = error            # a short, stable code such as "not_found"
        self.detail = detail          # what went wrong, in one sentence
        self.hint = hint              # what the caller can do about it
        self.headers = headers        # extra HTTP headers, for example Retry-After

    def body(self):
        return {"error": self.error, "detail": self.detail, "hint": self.hint}
