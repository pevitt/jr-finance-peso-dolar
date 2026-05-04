from abc import ABC
from typing import Any, List, Optional

from django.db import models


class BaseSelector(ABC):
    model = None

    @classmethod
    def create(cls, **kwargs) -> models.Model:
        if not cls.model:
            raise NotImplementedError("Model must be defined in subclass")
        return cls.model.objects.create(**kwargs)

    @classmethod
    def update(cls, instance: models.Model, **kwargs) -> models.Model:
        for key, value in kwargs.items():
            setattr(instance, key, value)
        instance.save()
        return instance

    @classmethod
    def delete(cls, instance: models.Model) -> bool:
        instance.delete()
        return True

    @classmethod
    def get_by_id(cls, id: Any) -> Optional[models.Model]:
        if not cls.model:
            raise NotImplementedError("Model must be defined in subclass")
        return cls.model.objects.filter(id=id).first()

    @classmethod
    def get_all(cls) -> List[models.Model]:
        if not cls.model:
            raise NotImplementedError("Model must be defined in subclass")
        return cls.model.objects.all()

    @classmethod
    def filter(cls, **filters) -> List[models.Model]:
        if not cls.model:
            raise NotImplementedError("Model must be defined in subclass")
        return cls.model.objects.filter(**filters)

    @classmethod
    def get_or_create(cls, defaults=None, **kwargs) -> tuple[models.Model, bool]:
        if not cls.model:
            raise NotImplementedError("Model must be defined in subclass")
        return cls.model.objects.get_or_create(defaults=defaults, **kwargs)

    @classmethod
    def bulk_create(cls, objects: List[models.Model]) -> List[models.Model]:
        if not cls.model:
            raise NotImplementedError("Model must be defined in subclass")
        return cls.model.objects.bulk_create(objects)

    @classmethod
    def count(cls, **filters) -> int:
        if not cls.model:
            raise NotImplementedError("Model must be defined in subclass")
        return cls.model.objects.filter(**filters).count()

    @classmethod
    def exists(cls, **filters) -> bool:
        if not cls.model:
            raise NotImplementedError("Model must be defined in subclass")
        return cls.model.objects.filter(**filters).exists()
