"""
IM Gateway Models — 多平台即时通讯接入网关
[PMBOK KA: 沟通管理 | PG: 执行 — 外部沟通渠道集成]

核心设计原则：
1. 用户隔离：每个用户独立绑定IM账号，数据不串台
2. 全能力：通过IM可执行查询/创建/更新/删除等所有操作
3. 冲突检测：AI自动检测并发冲突并提示
4. 审计日志：所有行为完整记录
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Float, Boolean, Index, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


# ============================================================
# 1. 平台级配置（管理员设置，全局唯一）
# ============================================================
class IMProviderConfig(Base):
    """IM平台配置：每个平台一条记录，存储 App ID / Secret 等凭证"""
    __tablename__ = "im_provider_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider = Column(String(50), nullable=False, unique=True, index=True)  # dingtalk / feishu / wecom / slack
    provider_name = Column(String(100))  # 显示名：钉钉 / 飞书 / 企业微信
    category = Column(String(30), default="im")  # im / dev / productivity

    # 平台凭证（加密存储）
    app_id = Column(String(200))
    app_secret = Column(String(500))
    verification_token = Column(String(200))  # 钉钉/企微的 token
    encrypt_key = Column(String(200))         # 钉钉/企微的 AES key
    webhook_url = Column(String(500))         # 回调地址

    # 能力开关
    enabled = Column(Boolean, default=False)
    capabilities = Column(JSON, default=list)  # ["chat", "command", "notification"]

    # 元信息
    created_by = Column(String(36))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "providerName": self.provider_name,
            "category": self.category,
            "appId": (self.app_id or "")[:8] + "****" if self.app_id else "",  # 脱敏
            "appSecret": "****" if self.app_secret else "",
            "verificationToken": self.verification_token,
            "encryptKey": "****" if self.encrypt_key else "",
            "webhookUrl": self.webhook_url,
            "enabled": self.enabled,
            "capabilities": self.capabilities or [],
            "createdBy": self.created_by,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_dict_full(self):
        """内部使用：返回完整凭证（不含脱敏）"""
        return {
            "id": self.id,
            "provider": self.provider,
            "providerName": self.provider_name,
            "appId": self.app_id,
            "appSecret": self.app_secret,
            "verificationToken": self.verification_token,
            "encryptKey": self.encrypt_key,
            "webhookUrl": self.webhook_url,
            "enabled": self.enabled,
            "capabilities": self.capabilities or [],
        }


# ============================================================
# 2. 用户绑定（用户 ↔ IM账号 映射，严格隔离）
# ============================================================
class UserIMBinding(Base):
    """用户IM账号绑定：一个AIPM用户可绑定多个平台的IM账号"""
    __tablename__ = "user_im_bindings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)

    # IM端身份
    im_user_id = Column(String(200), nullable=False, index=True)   # 平台内用户ID
    im_user_name = Column(String(200))                             # 昵称
    im_tenant_id = Column(String(200))                             # 租户ID（企业ID/部门ID）
    im_union_id = Column(String(200))                              # 跨应用统一ID（飞书）

    # 绑定状态
    status = Column(String(20), default="active")  # active / disabled / revoked
    bound_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True))

    # 会话上下文
    default_project_id = Column(String(36))       # 默认关联项目
    preferences = Column(JSON, default=dict)      # 语言/通知偏好等

    __table_args__ = (
        # 注意：不再对 (user_id, provider) 设唯一约束。
        # 自动绑定会把多个 IM 账号映射到同一系统用户（个人/单租户部署），
        # 真正的隔离由 (provider, im_user_id) 唯一约束保证（一个 IM 账号只绑定一次）。
        Index("ix_binding_user_provider", "user_id", "provider"),
        Index("ix_binding_im_user", "provider", "im_user_id", unique=True),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.user_id,
            "provider": self.provider,
            "imUserId": self.im_user_id,
            "imUserName": self.im_user_name,
            "imTenantId": self.im_tenant_id,
            "status": self.status,
            "boundAt": self.bound_at.isoformat() if self.bound_at else None,
            "lastActiveAt": self.last_active_at.isoformat() if self.last_active_at else None,
            "defaultProjectId": self.default_project_id,
            "preferences": self.preferences or {},
        }


# ============================================================
# 3. 会话 session（IM对话上下文）
# ============================================================
class IMConversationSession(Base):
    """IM对话会话：维护每段对话的上下文窗口"""
    __tablename__ = "im_conversation_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    binding_id = Column(String(36), ForeignKey("user_im_bindings.id"), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    im_chat_id = Column(String(200), index=True)     # 群聊/私聊ID

    # 会话状态
    status = Column(String(20), default="active")    # active / closed / archived
    message_count = Column(Integer, default=0)

    # 时间
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_message_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))

    def to_dict(self):
        return {
            "id": self.id,
            "bindingId": self.binding_id,
            "userId": self.user_id,
            "provider": self.provider,
            "imChatId": self.im_chat_id,
            "status": self.status,
            "messageCount": self.message_count,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "lastMessageAt": self.last_message_at.isoformat() if self.last_message_at else None,
            "closedAt": self.closed_at.isoformat() if self.closed_at else None,
        }


# ============================================================
# 4. 审计日志（所有行为完整记录）
# ============================================================
class IMAuditLog(Base):
    """IM操作审计日志：记录所有通过IM执行的操作"""
    __tablename__ = "im_audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("im_conversation_sessions.id"), index=True)

    # 操作内容
    action_type = Column(String(50), nullable=False, index=True)  # chat_read / command_exec / data_query / conflict_alert
    action_category = Column(String(30))  # query / create / update / delete / system
    raw_input = Column(Text)              # 用户原始输入
    parsed_intent = Column(JSON)          # AI解析的意图
    executed_action = Column(JSON)        # 实际执行的操作

    # 结果
    result_status = Column(String(20), default="success")  # success / error / conflict / blocked
    result_data = Column(JSON)           # 返回给用户的数据
    error_message = Column(Text)
    conflict_details = Column(JSON)      # 冲突详情（如有）

    # 性能
    ai_process_ms = Column(Float)        # AI处理耗时
    total_ms = Column(Float)             # 总耗时

    # IP安全
    source_ip = Column(String(50))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.user_id,
            "provider": self.provider,
            "sessionId": self.session_id,
            "actionType": self.action_type,
            "actionCategory": self.action_category,
            "rawInput": self.raw_input,
            "parsedIntent": self.parsed_intent,
            "executedAction": self.executed_action,
            "resultStatus": self.result_status,
            "resultData": self.result_data,
            "errorMessage": self.error_message,
            "conflictDetails": self.conflict_details,
            "aiProcessMs": self.ai_process_ms,
            "totalMs": self.total_ms,
            "sourceIp": self.source_ip,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
