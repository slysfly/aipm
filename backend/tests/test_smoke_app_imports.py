"""
冒烟测试 0：启动 / 导入健全性（验证「启动崩溃」修复）

仅做导入级校验，不触碰数据库、不启动端口：
- app.main 可构建（注册全部 60+ 路由，无导入期异常）
- serve.py 可导入（生产入口模块加载不崩溃）
- 关键路由已注册：项目 CRUD、/openclaw/assistant/chat、/integrations/inbound/agent、/health

运行（在 backend/ 目录下）：
    ../../venv/Scripts/python -m pytest tests/test_smoke_app_imports.py -v
"""
import importlib

from app.main import app


def _route_paths():
    return {getattr(r, "path", None) for r in app.routes}


def test_app_main_builds_and_is_fastapi():
    """app.main.app 构建成功，且是 FastAPI 实例。"""
    assert app is not None
    assert app.__class__.__name__ == "FastAPI"


def test_core_routes_registered():
    """核心路由已挂在 /api/v1 下，OpenClaw 与 inbound/agent 就绪。"""
    paths = _route_paths()
    # 项目 CRUD（集合端点带尾斜杠，由 serve 中间件补全，路由表登记为 /api/v1/projects）
    assert any(p and p.startswith("/api/v1/projects") for p in paths), \
        f"缺少 projects 路由: {sorted(p for p in paths if p and 'projects' in p)}"
    # AI 助手对话（F-03 端点），路径含 /api/v1 前缀
    assert "/api/v1/openclaw/assistant/chat" in paths, "缺少 /api/v1/openclaw/assistant/chat 路由"
    # 连接器 -> Agent 入站桥接
    assert "/api/v1/integrations/inbound/agent" in paths, "缺少 /api/v1/integrations/inbound/agent 路由"
    # 健康检查 + 根路径
    assert "/health" in paths, "缺少 /health 路由"


def test_serve_module_imports_without_crash():
    """生产入口 serve.py 可导入（验证启动崩溃修复：模块加载不抛异常）。"""
    # cwd 必须位于 backend/（conftest 已将其加入 sys.path）。
    mod = importlib.import_module("serve")
    assert hasattr(mod, "app"), "serve 模块缺少 app 对象"
    assert mod.app.__class__.__name__ == "FastAPI"
