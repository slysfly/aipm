from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime


class WebhookEvent:
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_DELETED = "task.deleted"
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    COMMENT_CREATED = "comment.created"
    RISK_CREATED = "risk.created"
    STATUS_CHANGED = "status.changed"

    ALL_EVENTS = [
        TASK_CREATED, TASK_UPDATED, TASK_DELETED,
        PROJECT_CREATED, PROJECT_UPDATED,
        COMMENT_CREATED, RISK_CREATED, STATUS_CHANGED
    ]


class WebhookBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: HttpUrl
    events: List[str] = []
    is_active: bool = True
    project_id: Optional[str] = None


class WebhookCreate(WebhookBase):
    secret: Optional[str] = None


class WebhookUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[HttpUrl] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None
    secret: Optional[str] = None


class WebhookResponse(WebhookBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    last_triggered_at: Optional[datetime] = None
    last_status: str = "pending"
    failure_count: int = 0

    class Config:
        from_attributes = True


class WebhookListResponse(BaseModel):
    items: List[WebhookResponse]
    total: int
    page: int
    page_size: int


class WebhookDeliveryResponse(BaseModel):
    id: str
    webhook_id: str
    event: str
    payload: Optional[Dict[str, Any]] = None
    response_status: Optional[int] = None
    success: bool
    retry_count: int
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WebhookDeliveryListResponse(BaseModel):
    items: List[WebhookDeliveryResponse]
    total: int
    page: int
    page_size: int


class WebhookTestRequest(BaseModel):
    event: str = Field(default=WebhookEvent.TASK_CREATED)
    payload: Optional[Dict[str, Any]] = None


class WebhookTestResponse(BaseModel):
    success: bool
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
