from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any, Union
from datetime import datetime


class ConditionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: str
    operator: str = Field(..., pattern="^(field_equals|field_contains|field_greater_than|field_less_than|field_in_list)$")
    value: Any


class ConditionGroupSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operator: str = Field(..., pattern="^(AND|OR)$")
    conditions: List[Union["ConditionSchema", "ConditionGroupSchema"]]


class ActionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str = Field(..., pattern="^(update_field|send_notification|create_task|assign_task|send_email|add_label|move_status)$")
    params: Dict[str, Any] = {}


class AutomationRuleBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: bool = True
    trigger_type: str = Field(...)
    trigger_conditions: Dict[str, Any] = {}
    actions: List[Dict[str, Any]] = []
    project_id: Optional[str] = None
    is_global: bool = False


class AutomationRuleCreate(AutomationRuleBase):
    pass


class AutomationRuleUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    trigger_type: Optional[str] = None
    trigger_conditions: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    project_id: Optional[str] = None
    is_global: Optional[bool] = None


class AutomationRuleResponse(AutomationRuleBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class AutomationRuleToggle(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_active: bool


class AutomationTestRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    entity_type: str = "task"
    trigger_data: Dict[str, Any] = {}


class AutomationTestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    rule_name: str
    triggered: bool
    conditions_result: bool
    actions_executed: List[Dict[str, Any]]
    errors: List[str] = []


ConditionSchema.model_rebuild()
ConditionGroupSchema.model_rebuild()
