class ApiProblem(Exception):
    def __init__(self, detail, status_code=422, code="INVALID_INPUT"):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.code = code
