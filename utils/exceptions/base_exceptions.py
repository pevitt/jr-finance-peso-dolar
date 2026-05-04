from rest_framework.exceptions import APIException


class BaseAPIException(APIException):
    def __init__(self, error_code, message: str = None):
        error = error_code.value.copy()
        if message:
            error["message"] = message
        self.status_code = error["status"]
        super().__init__(detail={"code": error["code"], "message": error["message"]})
