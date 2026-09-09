"""
PMI中国AI项目管理社区 - 测试基础设施
使用独立的 SQLite 内存/文件数据库，避免污染开发数据。
运行：在 backend/ 目录下执行  pytest  （需先 pip install -r requirements-dev.txt）
"""
import os
import sys
import asyncio
from pathlib import Path

# 确保后端包根目录（backend/）在 sys.path 中，使 `import app` 可用（无论从何处运行 pytest）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 必须在导入 app 之前设置测试环境
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_pm.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest
from httpx import AsyncClient, ASGITransport

from app.db.session import engine, Base, async_session_maker
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def setup_db():
    """创建/清理测试表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as c:
        yield c


async def _register_and_login(client: AsyncClient, suffix: str = ""):
    email = f"tester{suffix}@example.com"
    username = f"tester{suffix}"
    # 注册（幂等：失败不影响登录）
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "Test1234!",
            "full_name": "测试用户",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Test1234!"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


def data_of(r):
    """解包统一响应信封 {code, data, message} -> 返回 data；无信封则原样返回。

    用于兼容「信封中间件上线前」编写的用例：它们按裸响应读字段。
    凡响应含 data 键（即被包裹）就返回内层，否则原样返回，对未包裹的端点无副作用。
    """
    body = r.json()
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


@pytest.fixture
async def auth_headers(client):
    return await _register_and_login(client)


async def _create_superuser_headers(client):
    """注册一个用户并通过DB提升为超级用户，返回认证头"""
    suffix = f"su_{int(asyncio.get_event_loop().time())}"
    email = f"sup_{suffix}@example.com"
    username = f"sup_{suffix}"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email, "username": username,
            "password": "SuAdmin1234!",
            "full_name": "超级用户",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "SuAdmin1234!"},
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 直接从DB提升为超级用户
    from app.db.session import async_session_maker
    from app.models import User
    from sqlalchemy import select
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user:
            user.is_superuser = True
            await session.commit()

    return headers
