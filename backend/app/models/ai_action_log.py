"""AI 操作执行日志模型。

记录每一次「AI 项目经理直接操作系统」的执行结果，**一张卡片（一个 client_token）对应一行**：

- client_token：前端每张操作卡片一个 UUID，唯一索引保证同一次确认只执行一次（幂等）；
  并发重复确认时由唯一约束 + 服务层 IntegrityError 兜底，杜绝双击/超时重试导致的重复建库。
- results：本次所有 action 的执行结果明细（JSON 数组），含每个 action 的 old_values 旧值快照，供后续（P1）撤销使用。
- status：整体执行状态 ok / partial（部分成功）/ error。
即便业务写库失败，日志也始终落库（外层事务提交），保证"每次执行都留痕"。

**关于 executed_at 的默认值**：
 故意不用 `server_default=strftime(...)` —— 老贾之前已踩过坑：
   - A 服 SQLite 用 strftime 是为了本地时间；
   - B 服 PostgreSQL 没有 strftime，必须用 CURRENT_TIMESTAMP（返回 UTC）；
   - 一列用两套语法会让 `Base.metadata.create_all` 在 B 服 CREATE TABLE 时直接报
     "function strftime does not exist" → 应用启动失败 → systemd 进入 auto-restart 死循环。
 改用「Python 端 default=datetime.utcnow」：SQLite / PostgreSQL 都接受，行为统一。
 服务层在写入前显式赋 `datetime.utcnow()`，DB 默认仅作直接 INSERT 的兜底。
"""
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer, Text, JSON, ForeignKey
from app.db.session import Base
from app.models import generate_uuid


class AIActionLog(Base):
    __tablename__ = "ai_action_log"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    client_token = Column(String(64), unique=True, nullable=False, index=True)  # 幂等键（每卡一次）
    action_count = Column(Integer, default=0)
    results = Column(JSON, default=list)        # 每条 action 的执行结果明细（含 old_values 快照）
    created_task_ids = Column(JSON, default=list)  # 本次新建的任务 ID 列表
    status = Column(String(20), default="ok")    # ok | partial | error
    error = Column(Text)
    succeeded = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    truncated = Column(Integer, default=0)       # 是否因超 30 条被截断
    # 不在 server_default 里写 strftime / CURRENT_TIMESTAMP —— 服务层在 execute_actions
    # 显式赋 datetime.utcnow()。这样 SQLite 与 PostgreSQL 行为一致，且服务端可测。
    executed_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __repr__(self):
        return f"<AIActionLog {self.client_token} {self.status}>"
