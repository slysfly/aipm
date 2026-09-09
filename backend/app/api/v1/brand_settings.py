"""
PMI中国AI项目管理社区 - 品牌设置 API（管理员）
管理员在"系统设置 > 品牌设置"中上传品牌 Logo，一次上传全局生效（Favicon / 侧边栏 / 登录页 / PWA图标）。

[PMBOK KA: 采购管理 (Procurement) — 系统品牌资产]
对应PMI第6版标准：系统品牌资产管理"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.security import require_superuser
from app.models import User

router = APIRouter()

# ── 存储路径 ────────────────────────────────────────────────
# 品牌Logo独立存储在 backend/static/uploads/ 目录下（与通用附件分开）
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # .../backend/
UPLOAD_DIR = _BACKEND_DIR / "static" / "uploads"
BRAND_META_FILE = UPLOAD_DIR / "brand_meta.json"
MAX_SIZE = 512 * 1024        # 512 KB
ALLOWED_TYPES = {"image/png", "image/svg+xml", "image/webp", "image/jpeg"}
ALLOWED_EXTENSIONS = {".png", ".svg", ".webp", ".jpg", ".jpeg"}

# 确保目录存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _get_logo_filename(ext: str) -> str:
    return f"brand_logo{ext}"


def _get_brand_meta() -> dict:
    """读取当前品牌元数据"""
    if BRAND_META_FILE.exists():
        try:
            return json.loads(BRAND_META_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _save_brand_meta(meta: dict):
    """保存品牌元数据"""
    BRAND_META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")


# ── Schema ───────────────────────────────────────────────────
class BrandInfo(BaseModel):
    """品牌信息响应"""
    has_logo: bool = False
    logo_url: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: int = 0
    uploaded_at: Optional[str] = None


class BrandUploadResponse(BaseModel):
    """上传结果"""
    success: bool
    message: str
    data: Optional[BrandInfo] = None


# ── API Endpoints ────────────────────────────────────────────

@router.get("/brand-logo", response_model=BrandInfo, summary="获取当前品牌Logo信息")
async def get_brand_info():
    """
    获取当前已上传的品牌 Logo 信息（不含图片数据，仅元数据）。
    前端据此决定是否展示 Logo 图片。

    无需登录——仅返回公开的 Logo 元数据（是否有上传 / 文件名 / MIME 类型），
    与 /brand-logo/file 保持一致的访问策略。
    """
    meta = _get_brand_meta()
    if not meta.get("filename"):
        return BrandInfo()

    filepath = UPLOAD_DIR / meta["filename"]
    if not filepath.exists():
        # 文件不存在，清理脏数据
        BRAND_META_FILE.unlink(missing_ok=True)
        return BrandInfo()

    return BrandInfo(
        has_logo=True,
        logo_url="/api/v1/system/brand-logo/file",
        filename=meta["filename"],
        mime_type=meta.get("mime_type"),
        size_bytes=meta.get("size_bytes", 0),
        uploaded_at=meta.get("uploaded_at"),
    )


@router.get("/brand-logo/file", summary="获取品牌Logo文件")
async def get_brand_logo_file():
    """
    返回品牌 Logo 图片文件。所有前端组件通过此 URL 加载同一张 Logo。
    无需登录（用于 favicon 和公开页面）。
    """
    meta = _get_brand_meta()
    if not meta.get("filename"):
        raise HTTPException(status_code=404, detail="未设置品牌 Logo")

    filepath = UPLOAD_DIR / meta["filename"]
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Logo 文件不存在")

    return FileResponse(
        path=str(filepath),
        media_type=meta.get("mime_type", "image/png"),
        filename=meta["filename"],
    )


@router.post("/brand-logo/upload", response_model=BrandUploadResponse, summary="上传品牌Logo")
async def upload_brand_logo(
    file: UploadFile = File(..., description="品牌 Logo 图片文件"),
    current_user: User = Depends(require_superuser),
):
    """
    上传品牌 Logo 图片。成功后将自动替换系统中所有 Logo 显示位置：

    **支持的格式**：PNG / SVG / WebP / JPG
    **大小限制**：≤ 512 KB
    **推荐尺寸**：正方形，≥ 128×128 px（将自适应缩放至各位置）

    > 上传后无需重启服务，所有前端位置即时生效（Favicon 需刷新页面）。
    """

    # ── 校验文件类型 ──
    content_type = (file.content_type or "").lower().strip()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型：{content_type}。允许的格式：{', '.join(sorted(ALLOWED_TYPES))}",
        )

    # ── 校验扩展名 ──
    ext = Path(file.filename or "").suffix.lower() or (
        ".svg" if "svg" in content_type else
        ".webp" if "webp" in content_type else
        ".png"
    )
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不允许的扩展名：{ext}。允许的扩展名：{', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # ── 读取并校验大小 ──
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大：{len(content) / 1024:.0f} KB，上限 {MAX_SIZE // 1024} KB",
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件内容为空")

    # ── 删除旧 Logo ──
    old_meta = _get_brand_meta()
    if old_meta.get("filename"):
        old_path = UPLOAD_DIR / old_meta["filename"]
        if old_path.exists():
            old_path.unlink()

    # ── 保存新 Logo ──
    from datetime import datetime
    filename = _get_logo_filename(ext)
    filepath = UPLOAD_DIR / filename
    filepath.write_bytes(content)

    # ── 更新元数据 ──
    meta = {
        "filename": filename,
        "mime_type": content_type,
        "size_bytes": len(content),
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "original_name": file.filename,
    }
    _save_brand_meta(meta)

    return BrandUploadResponse(
        success=True,
        message=f"品牌 Logo 已上传成功（{len(content) / 1024:.1f} KB），系统全部 Logo 位置已同步更新",
        data=BrandInfo(
            has_logo=True,
            logo_url="/api/v1/system/brand-logo/file",
            filename=filename,
            mime_type=content_type,
            size_bytes=len(content),
            uploaded_at=meta["uploaded_at"],
        ),
    )


@router.delete("/brand-logo", response_model=BrandUploadResponse, summary="删除品牌Logo")
async def delete_brand_logo(current_user: User = Depends(require_superuser)):
    """删除品牌 Logo，恢复为默认图标"""
    meta = _get_brand_meta()
    if not meta.get("filename"):
        return BrandUploadResponse(success=False, message="未设置品牌 Logo")

    filepath = UPLOAD_DIR / meta["filename"]
    if filepath.exists():
        filepath.unlink()

    BRAND_META_FILE.unlink(missing_ok=True)

    return BrandUploadResponse(
        success=True,
        message="品牌 Logo 已删除，系统将恢复使用默认图标",
    )
