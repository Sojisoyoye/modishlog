"""Invoice schemes domain exceptions."""


class SchemeNotFoundError(Exception):
    def __init__(self, scheme_id=None):
        super().__init__(f"Invoice scheme not found: {scheme_id}")
