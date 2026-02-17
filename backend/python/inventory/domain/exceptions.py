class ValidationError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class NotFoundError(Exception):
    def __init__(self, message="Product not found"):
        self.message = message
        super().__init__(self.message)


class DuplicateError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
