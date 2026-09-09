from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class CustomFieldBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=255)
    field_key: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|date|checkbox|user|attachment)$")
    entity_type: str = Field(..., pattern="^(project|task|risk|resource)$")
    options: List[Dict[str, Any]] = []
    is_required: bool = False
    default_value: Optional[Any] = None
    sort_order: int = 0
    project_id: Optional[str] = None
    is_global: bool = False


class CustomFieldCreate(CustomFieldBase):
    pass


class CustomFieldUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None
    field_key: Optional[str] = None
    field_type: Optional[str] = None
    options: Optional[List[Dict[str, Any]]] = None
    is_required: Optional[bool] = None
    default_value: Optional[Any] = None
    sort_order: Optional[int] = None
    is_global: Optional[bool] = None


class CustomFieldResponse(CustomFieldBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class CustomFieldValueBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    custom_field_id: str
    entity_id: str
    entity_type: str
    value: Optional[Any] = None


class CustomFieldValueCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: Optional[Any] = None


class CustomFieldValueUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: Optional[Any] = None


class CustomFieldValueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    custom_field_id: str
    entity_id: str
    entity_type: str
    value: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
    custom_field: Optional[CustomFieldResponse] = None


class CustomFieldValueWithField(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_id: str
    field_name: str
    field_key: str
    field_type: str
    value: Optional[Any] = None
    is_required: bool
    options: List[Dict[str, Any]] = []
