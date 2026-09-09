"""
PMI中国AI项目管理社区 - 数据导入导出API路由
提供任务导出（Excel/CSV/PDF）和导入功能

[PMBOK KA: 整合管理 (Integration) — 数据导出导入、报表生成]
对应PMI第6版标准：数据导出导入

[CPMAI Phase: CPMAI Phase: Data Preparation | Domain: Data for AI — 数据准备与格式转换]"""

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db
from app.models import User
from app.core.security import get_current_user
from app.core.exceptions import ValidationException
from app.services.export_import import ExportService, ImportService

# 拆分导出/导入为独立路由，分别挂载到 /exports 与 /imports，
# 避免将同一 router 同时挂两个前缀导致端点重复暴露。
export_router = APIRouter(tags=["数据导出"])
import_router = APIRouter(tags=["数据导入"])


@export_router.get("/projects/{project_id}/tasks/excel")
async def export_tasks_excel(
    project_id: str,
    status: Optional[str] = Query(None, description="按状态筛选"),
    priority: Optional[int] = Query(None, description="按优先级筛选"),
    assignee_id: Optional[str] = Query(None, description="按负责人筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    filters = {}
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    if assignee_id:
        filters["assignee_id"] = assignee_id

    file_bytes = await ExportService.export_tasks_to_excel(db, project_id, filters if filters else None)

    filename = f"tasks_{project_id}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return StreamingResponse(
        __import__('io').BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@export_router.get("/projects/{project_id}/tasks/csv")
async def export_tasks_csv(
    project_id: str,
    status: Optional[str] = Query(None, description="按状态筛选"),
    priority: Optional[int] = Query(None, description="按优先级筛选"),
    assignee_id: Optional[str] = Query(None, description="按负责人筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    filters = {}
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    if assignee_id:
        filters["assignee_id"] = assignee_id

    file_bytes = await ExportService.export_tasks_to_csv(db, project_id, filters if filters else None)

    filename = f"tasks_{project_id}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        __import__('io').BytesIO(file_bytes),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@export_router.get("/projects/{project_id}/report/pdf")
async def export_project_report_pdf(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    file_bytes, file_type = await ExportService.export_project_report_to_pdf(db, project_id)

    if file_type == "html":
        filename = f"report_{project_id}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        return StreamingResponse(
            __import__('io').BytesIO(file_bytes),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        filename = f"report_{project_id}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return StreamingResponse(
            __import__('io').BytesIO(file_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


@import_router.post("/tasks")
async def import_tasks(
    file: UploadFile = File(..., description="上传的Excel或CSV文件"),
    project_id: str = Form(..., description="目标项目ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    content = await file.read()

    if not content:
        raise ValidationException(message="文件内容为空")

    # 根据文件名后缀判断文件类型
    filename = file.filename or ""
    if filename.lower().endswith(('.xlsx', '.xls')):
        data = ImportService.parse_excel(content)
    elif filename.lower().endswith('.csv'):
        data = ImportService.parse_csv(content)
    else:
        raise ValidationException(message="不支持的文件格式，请上传 Excel (.xlsx) 或 CSV (.csv) 文件")

    # 验证数据
    is_valid, errors = ImportService.validate_task_data(data)
    if not is_valid:
        raise ValidationException(
            message="数据验证失败",
            details={"errors": errors}
        )

    # 导入任务
    result = await ImportService.import_tasks(db, project_id, data, current_user.id)

    return {
        "success": True,
        "message": f"导入完成：成功 {result['created']} 条，失败 {result['failed']} 条",
        "data": result
    }


@import_router.post("/tasks/preview")
async def preview_import_tasks(
    file: UploadFile = File(..., description="上传的Excel或CSV文件"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    content = await file.read()

    if not content:
        raise ValidationException(message="文件内容为空")

    # 根据文件名后缀判断文件类型
    filename = file.filename or ""
    if filename.lower().endswith(('.xlsx', '.xls')):
        data = ImportService.parse_excel(content)
    elif filename.lower().endswith('.csv'):
        data = ImportService.parse_csv(content)
    else:
        raise ValidationException(message="不支持的文件格式，请上传 Excel (.xlsx) 或 CSV (.csv) 文件")

    # 验证数据
    is_valid, errors = ImportService.validate_task_data(data)

    # 规范化数据用于预览
    normalized = ImportService.normalize_task_data(data[:50])  # 最多预览50条

    return {
        "success": True,
        "data": {
            "total": len(data),
            "preview": normalized[:5],  # 预览前5条
            "valid": is_valid,
            "errors": errors[:10] if errors else [],  # 最多显示10条错误
        }
    }


@import_router.get("/template")
async def download_import_template(
    current_user: User = Depends(get_current_user)
):
    file_bytes = ImportService.generate_template_excel()

    filename = f"task_import_template_{__import__('datetime').datetime.now().strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        __import__('io').BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
