from enum import Enum

from rest_framework import status

from utils.exceptions.base_exceptions import BaseAPIException


class FinanceErrorCode(Enum):
    F01 = dict(code="F01", message="Perfil de usuario no encontrado", status=status.HTTP_404_NOT_FOUND)
    F02 = dict(code="F02", message="Cuenta no encontrada", status=status.HTTP_404_NOT_FOUND)
    F03 = dict(code="F03", message="Transacción no encontrada", status=status.HTTP_404_NOT_FOUND)
    F04 = dict(code="F04", message="Gasto mensual no encontrado", status=status.HTTP_404_NOT_FOUND)
    F05 = dict(code="F05", message="La cuenta no pertenece al usuario", status=status.HTTP_400_BAD_REQUEST)


class FinanceException(BaseAPIException):
    def __init__(self, error_code: FinanceErrorCode, message: str = None):
        super().__init__(error_code, message)
