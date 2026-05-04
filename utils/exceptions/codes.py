from enum import Enum

from rest_framework import status


class GeneralErrorCode(Enum):
    G00 = dict(code="G00", message="An unexpected error occurred", status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    G01 = dict(code="G01", message="Not found", status=status.HTTP_404_NOT_FOUND)
    G02 = dict(code="G02", message="Bad request", status=status.HTTP_400_BAD_REQUEST)
    G03 = dict(code="G03", message="Unauthorized", status=status.HTTP_401_UNAUTHORIZED)
    G04 = dict(code="G04", message="Forbidden", status=status.HTTP_403_FORBIDDEN)
