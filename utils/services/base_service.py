from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from django.db import models


class BaseService(ABC):

    @classmethod
    @abstractmethod
    def create(cls, **kwargs) -> models.Model:
        pass

    @classmethod
    @abstractmethod
    def update(cls, instance: models.Model, **kwargs) -> models.Model:
        pass

    @classmethod
    @abstractmethod
    def delete(cls, instance: models.Model) -> bool:
        pass

    @classmethod
    @abstractmethod
    def get_by_id(cls, id: Any) -> Optional[models.Model]:
        pass

    @classmethod
    @abstractmethod
    def get_all(cls) -> List[models.Model]:
        pass

    @classmethod
    @abstractmethod
    def get_by_filters(cls, **filters) -> List[models.Model]:
        pass

    @classmethod
    def validate_data(cls, data: Dict) -> bool:
        return True

    @classmethod
    def process_before_save(cls, data: Dict) -> Dict:
        return data

    @classmethod
    def process_after_save(cls, instance: models.Model) -> models.Model:
        return instance
