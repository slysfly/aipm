"""
IM Gateway 入站签名验签服务（Issue #12 安全加固）

[PMBOK KA: 沟通管理 | PG: 执行 — 外部沟通渠道集成]

设计要点（严格 fail-closed）：
1. **验签输入必须是原始请求体**（raw body bytes）。各平台签名均基于原始字节，
   解析后重新序列化会破坏签名，因此禁止用 `json.dumps(json.loads(...))` 参与验签。
2. **常量时间比较**：所有摘要比对统一走 `hmac.compare_digest`。
3. **fail-closed**：密钥未配置 / 缺少签名头 / 签名格式异常 / 时间戳超窗 /
   验签器内部异常 —— 一律返回 `ok=False`，由调用方在任何 DB 写入、AI 调用、
   绑定查询之前拒绝（HTTP 401）。
4. **不泄露敏感信息**：日志与错误码只记录 `reason`（枚举字符串）与来源 IP，
   绝不输出密钥或完整签名。

平台算法对照：
| 平台      | 签名头/字段                        | 待签名串                                       | 算法                        | 编码    | 密钥字段              |
|-----------|------------------------------------|------------------------------------------------|-----------------------------|---------|-----------------------|
| dingtalk  | `timestamp` + `sign`               | `{timestamp}\\n{secret}`                        | HMAC-SHA256                 | Base64  | app_secret(优先)      |
| feishu    | `X-Lark-Request-Timestamp/Nonce/Signature` | v2: `{ts}\\n{nonce}\\n{key}\\n{body}`<br>v1: `{ts}\\n{nonce}\\n{key}` | HMAC-SHA256 | hex     | encrypt_key(优先)     |
| wecom     | `msg_signature`+`timestamp`+`nonce` | `"".join(sorted([token, ts, nonce, aes_key]))`  | SHA-1                       | hex     | verification_token    |
| slack     | `X-Slack-Request-Timestamp/Signature` | `v0:{timestamp}:{raw_body}`                    | HMAC-SHA256                 | hex     | app_secret(Sign Sec.) |

依赖：仅使用标准库（`hmac`/`hashlib`/`base64`/`re`/`time`），不引入新三方包。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_TOLERANCE_SECONDS",
    "SUPPORTED_PLATFORMS",
    "VERIFIER_REGISTRY",
    "ProviderSecrets",
    "SignatureContext",
    "SignatureProof",
    "SignatureFailureReason",
    "VerificationResult",
    "issue_signature_proof",
    "is_valid_signature_proof",
    "log_signature_result",
    "rejection_detail",
    "verify_platform_signature",
    "verify_signature",
]

# 默认时间戳时效窗口（秒）。Slack / 钉钉官方均为 300s。
DEFAULT_TOLERANCE_SECONDS = 300

# 内部哨兵对象：只有本模块的 issue_signature_proof() 能生成有效 Proof，
# 防止调用方随手构造 `SignatureProof()` 伪造"已验签"标记。
_PROOF_SENTINEL = object()


# ============================================================
# 1. 失败原因枚举（对外只暴露这些字符串，不含任何密钥/签名信息）
# ============================================================
class SignatureFailureReason:
    """验签失败原因枚举。响应体与日志中只允许出现这些值。"""

    OK = "ok"
    VERIFICATION_DISABLED = "verification_disabled"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    SECRET_NOT_CONFIGURED = "secret_not_configured"
    MISSING_SIGNATURE = "missing_signature"
    MALFORMED_SIGNATURE = "malformed_signature"
    MISSING_TIMESTAMP = "missing_timestamp"
    MALFORMED_TIMESTAMP = "malformed_timestamp"
    TIMESTAMP_OUT_OF_WINDOW = "timestamp_out_of_window"
    SIGNATURE_MISMATCH = "signature_mismatch"
    MISSING_REQUEST_CONTEXT = "missing_request_context"
    VERIFIER_ERROR = "verifier_error"


# ============================================================
# 2. 密钥容器
# ============================================================
@dataclass
class ProviderSecrets:
    """单个平台的验签密钥集合。

    来源优先级：`IMProviderConfig`（DB，按平台隔离，支持独立配置与轮换）
    → `Settings` 环境变量（部署兜底）。两者皆空 → `secret_not_configured`（fail-closed）。

    注意：本对象**绝不可**被 `to_dict()`/日志序列化输出。
    """

    platform: str
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    verification_token: Optional[str] = None
    encrypt_key: Optional[str] = None

    @classmethod
    def from_config(
        cls,
        platform: str,
        config: Any = None,
    ) -> "ProviderSecrets":
        """从 `IMProviderConfig` 行对象构建，并回退到环境变量。

        Args:
            platform: 平台标识（dingtalk/feishu/wecom/slack）。
            config: `IMProviderConfig` 实例或 None。

        Returns:
            ProviderSecrets: 已按平台解析好的密钥集合（缺失项为 None）。
        """
        platform = (platform or "").strip().lower()

        def _db(field_name: str) -> Optional[str]:
            if config is None:
                return None
            value = getattr(config, field_name, None)
            return str(value).strip() if value else None

        def _first(*values: Optional[str]) -> Optional[str]:
            for value in values:
                if value and value.strip():
                    return value.strip()
            return None

        # --- 钉钉：HMAC 密钥为 AppSecret；Robot 模式下"加签密钥"常存在 verification_token
        if platform == "dingtalk":
            return cls(
                platform=platform,
                app_id=_db("app_id"),
                app_secret=_first(_db("app_secret"), settings.DINGTALK_APP_SECRET),
                verification_token=_db("verification_token"),
                encrypt_key=_db("encrypt_key"),
            )

        # --- 飞书：事件验签密钥为 Encrypt Key（缺失时回退 App Secret）
        if platform == "feishu":
            return cls(
                platform=platform,
                app_id=_db("app_id"),
                app_secret=_first(_db("app_secret"), settings.FEISHU_APP_SECRET),
                verification_token=_db("verification_token"),
                encrypt_key=_first(_db("encrypt_key"), settings.FEISHU_ENCRYPT_KEY),
            )

        # --- 企业微信：回调 Token 用于 SHA1(msg_signature)；EncodingAESKey 用于加解密
        if platform == "wecom":
            return cls(
                platform=platform,
                app_id=_db("app_id"),
                app_secret=_first(_db("app_secret"), settings.WECOM_CORP_SECRET),
                verification_token=_first(
                    _db("verification_token"), settings.WECOM_CB_TOKEN
                ),
                encrypt_key=_first(_db("encrypt_key"), settings.WECOM_ENCODING_AES_KEY),
            )

        # --- Slack：Signing Secret 复用 app_secret 字段
        if platform == "slack":
            return cls(
                platform=platform,
                app_id=_db("app_id"),
                app_secret=_first(_db("app_secret"), settings.SLACK_SIGNING_SECRET),
                verification_token=_db("verification_token"),
                encrypt_key=_db("encrypt_key"),
            )

        return cls(platform=platform, app_id=_db("app_id"), app_secret=_db("app_secret"))

    def signing_keys(self) -> List[str]:
        """返回该平台可接受的 HMAC/SHA1 密钥候选列表（去重、去空、保序）。

        多候选是为了兼容同一平台的不同部署形态（例如钉钉 AppSecret 与
        机器人"加签密钥"可能存放在不同字段）。安全性不降低：攻击者仍需
        命中其中任意一个密钥才能伪造签名。
        """
        ordered = (
            self.app_secret,
            self.encrypt_key,
            self.verification_token,
        )
        seen: set = set()
        keys: List[str] = []
        for value in ordered:
            if value and value.strip() and value.strip() not in seen:
                seen.add(value.strip())
                keys.append(value.strip())
        return keys


# ============================================================
# 3. 验签上下文
# ============================================================
@dataclass
class SignatureContext:
    """一次验签所需的全部输入（由路由层从 `Request` 组装）。"""

    platform: str
    raw_body: bytes = b""
    # header 名统一小写
    headers: Mapping[str, str] = field(default_factory=dict)
    query: Mapping[str, str] = field(default_factory=dict)
    # 已解析的业务报文字段（如企业微信 JSON 回调中的 MsgSignature/timestamp/nonce）
    body_fields: Mapping[str, Any] = field(default_factory=dict)
    secrets: ProviderSecrets = field(default_factory=lambda: ProviderSecrets(platform=""))
    timestamp_override: Optional[int] = None
    tolerance: int = DEFAULT_TOLERANCE_SECONDS
    now: Optional[float] = None

    def get(self, *names: str) -> Optional[str]:
        """按 `headers → query → body_fields` 顺序取第一个非空值。

        `body_fields` 采用**大小写不敏感**匹配：企业微信 JSON 回调的字段名为
        `MsgSignature`（首字母大写），而验签器内部统一使用小写名
        `msg_signature`，若不做归一化会漏取导致合法请求被拒。
        """
        for name in names:
            value = self.headers.get(name.lower())
            if value is not None and str(value).strip():
                return str(value).strip()
        for name in names:
            value = self.query.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()
        for name in names:
            value = self._lookup_body_field(name)
            if value is not None:
                return value
        if names and "timestamp" in {n.lower() for n in names}:
            if self.timestamp_override is not None:
                return str(self.timestamp_override)
        return None

    def _lookup_body_field(self, name: str) -> Optional[str]:
        """在 `body_fields` 中大小写不敏感地查找字段。"""
        if not self.body_fields:
            return None
        # 快路径：精确命中
        if name in self.body_fields:
            value = self.body_fields.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()
        # 慢路径：忽略下划线与大小写后匹配（MsgSignature ↔ msg_signature）
        target = name.replace("_", "").lower()
        for key, value in self.body_fields.items():
            if str(key).replace("_", "").lower() == target:
                if value is not None and str(value).strip():
                    return str(value).strip()
        return None


@dataclass
class VerificationResult:
    """验签结果。`ok` 为 False 时 `reason` 必填。"""

    ok: bool
    platform: str
    reason: str = SignatureFailureReason.OK
    # 仅供内部审计使用的非敏感补充信息（如缺失的头名），不得含密钥/签名原文
    detail: Optional[str] = None
    bypass: bool = False

    def to_safe_dict(self) -> Dict[str, Any]:
        """可安全返回给调用方的结构（不含密钥与签名）。"""
        return {"ok": self.ok, "platform": self.platform, "reason": self.reason}


@dataclass
class SignatureProof:
    """已验签凭据。由 `issue_signature_proof()` 生成，`inbound_message()` 消费。

    作用：平台 Webhook 端点已完成验签 → 生成 Proof → 传给统一入口
    （含飞书 `asyncio.create_task` 后台链路），避免重复验签，同时保证
    **不存在可绕过验签的调用路径**（无有效 Proof 一律 fail-closed）。
    """

    platform: str
    reason: str = SignatureFailureReason.OK
    _sentinel: Any = None

    def is_valid(self) -> bool:
        return self._sentinel is _PROOF_SENTINEL


# ============================================================
# 4. 通用工具（常量时间比较 / 时间戳窗口 / 编码归一化）
# ============================================================
def _hmac_sha256_hex(key: str, base_string: str) -> str:
    """HMAC-SHA256 → 小写 hex。"""
    digest = hmac.new(
        key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha256
    ).digest()
    return digest.hex()


def _hmac_sha256_b64(key: str, base_string: str) -> str:
    """HMAC-SHA256 → 标准 Base64（保留 `=` 补位）。"""
    digest = hmac.new(
        key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _sha1_hex(value: str) -> str:
    """SHA-1 → 小写 hex（企业微信 msg_signature）。"""
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _compare_hex(expected: str, provided: Optional[str]) -> bool:
    """hex 摘要常量时间比较（大小写不敏感）。"""
    if not provided:
        return False
    try:
        return hmac.compare_digest(expected.strip().lower(), provided.strip().lower())
    except (TypeError, ValueError):
        return False


def _compare_b64(expected: str, provided: Optional[str]) -> bool:
    """Base64 摘要常量时间比较（Base64 大小写敏感，禁止 lower）。"""
    if not provided:
        return False
    candidate = provided.strip()
    # 部分平台会把 Base64 里的 `+` 编码为 `%2B`，`=` 补位可能被网关裁剪
    candidate = candidate.replace(" ", "")
    padded = candidate + ("=" * ((-len(candidate)) % 4))
    try:
        if hmac.compare_digest(expected, candidate) or hmac.compare_digest(
            expected, padded
        ):
            return True
    except (TypeError, ValueError):
        return False
    return False


def _parse_timestamp(raw: Optional[str]) -> Optional[int]:
    """解析时间戳字符串；无法解析返回 None（调用方据此给出 malformed 原因）。"""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        pass
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _parse_kv_header(value: str) -> Dict[str, str]:
    """解析 `k=v,k=v` 形式的头（飞书 v1 复合签名头）。"""
    parsed: Dict[str, str] = {}
    for chunk in str(value).split(","):
        if "=" not in chunk:
            continue
        key, _, val = chunk.partition("=")
        parsed[key.strip().lower()] = val.strip()
    return parsed


def _in_window(timestamp: int, now: float, tolerance: int) -> bool:
    """时间戳时效窗口校验（防重放）。tolerance<=0 时按默认窗口处理（fail-closed）。"""
    effective = tolerance if tolerance and tolerance > 0 else DEFAULT_TOLERANCE_SECONDS
    return abs(now - float(timestamp)) <= float(effective)


# ============================================================
# 5. 各平台验签器
# ============================================================
def verify_dingtalk(ctx: SignatureContext) -> VerificationResult:
    """钉钉验签：`base64(HMAC-SHA256(secret, f"{timestamp}\\n{secret}"))`。

    签名与时间戳可来自 HTTP header 或 URL query（钉钉两种形态都会带）。
    """
    keys = ctx.secrets.signing_keys()
    if not keys:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.SECRET_NOT_CONFIGURED,
            detail="app_secret/verification_token 未配置",
        )

    signature = ctx.get("sign", "signature", "x-signature")
    if not signature:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_SIGNATURE, detail="sign"
        )

    ts_raw = ctx.get("timestamp")
    if not ts_raw:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_TIMESTAMP, detail="timestamp"
        )

    timestamp = _parse_timestamp(ts_raw)
    if timestamp is None:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MALFORMED_TIMESTAMP
        )

    now = ctx.now if ctx.now is not None else time.time()
    if not _in_window(timestamp, now, ctx.tolerance):
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.TIMESTAMP_OUT_OF_WINDOW
        )

    # 时间戳按原始字符串参与签名（平台签名的是它下发的那个字面量）
    base_string = f"{ts_raw}\n"
    for key in keys:
        expected = _hmac_sha256_b64(key, f"{base_string}{key}")
        if _compare_b64(expected, signature):
            return VerificationResult(True, ctx.platform, SignatureFailureReason.OK)

    return VerificationResult(
        False, ctx.platform, SignatureFailureReason.SIGNATURE_MISMATCH
    )


def verify_feishu(ctx: SignatureContext) -> VerificationResult:
    """飞书验签：同时兼容 v2（推荐）与 v1（历史）两种签名协议。

    - v2：`X-Lark-Request-Timestamp` + `X-Lark-Request-Nonce` + `X-Lark-Signature`
      base = `{ts}\\n{nonce}\\n{encrypt_key}\\n{raw_body}`
    - v1：`X-Lark-Signature: timestamp=..,nonce=..,signature=..`
      base = `{ts}\\n{nonce}\\n{encrypt_key}`

    另兼容两种常见的历史/私有部署写法：
      - `v1:{ts}:{nonce}:{encrypt_key}`
      - `{ts}\\n{secret}`

    上述候选均为明确定义的待签名串，命中任一仍需持有密钥，故不降低安全性。
    """
    keys = ctx.secrets.signing_keys()
    if not keys:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.SECRET_NOT_CONFIGURED,
            detail="encrypt_key/app_secret 未配置",
        )

    signature = ctx.get("x-lark-signature", "lark-signature", "signature", "sign")
    if not signature:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_SIGNATURE,
            detail="X-Lark-Signature",
        )

    ts_raw: Optional[str] = None
    nonce: Optional[str] = None

    # v1 复合头：timestamp=xxx,nonce=xxx,signature=xxx
    if "=" in signature and "," in signature:
        kv = _parse_kv_header(signature)
        if kv.get("signature"):
            signature = kv["signature"]
            ts_raw = ts_raw or kv.get("timestamp")
            nonce = nonce or kv.get("nonce")

    ts_raw = ts_raw or ctx.get("x-lark-request-timestamp", "timestamp")
    nonce = nonce or ctx.get("x-lark-request-nonce", "nonce")

    if not ts_raw:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_TIMESTAMP,
            detail="X-Lark-Request-Timestamp",
        )

    timestamp = _parse_timestamp(ts_raw)
    if timestamp is None:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MALFORMED_TIMESTAMP
        )

    now = ctx.now if ctx.now is not None else time.time()
    if not _in_window(timestamp, now, ctx.tolerance):
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.TIMESTAMP_OUT_OF_WINDOW
        )

    try:
        body_text = (ctx.raw_body or b"").decode("utf-8")
    except UnicodeDecodeError:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MALFORMED_SIGNATURE,
            detail="raw_body 非 UTF-8",
        )

    nonce_value = nonce or ""

    for key in keys:
        candidates = [
            # v2 官方（含原始请求体）
            f"{ts_raw}\n{nonce_value}\n{key}\n{body_text}",
            # v1 官方（不含请求体）
            f"{ts_raw}\n{nonce_value}\n{key}",
            # 兼容写法 A
            f"v1:{ts_raw}:{nonce_value}:{key}",
            # 兼容写法 B
            f"{ts_raw}\n{key}",
        ]
        for base_string in candidates:
            if _compare_hex(_hmac_sha256_hex(key, base_string), signature):
                return VerificationResult(True, ctx.platform, SignatureFailureReason.OK)

    return VerificationResult(
        False, ctx.platform, SignatureFailureReason.SIGNATURE_MISMATCH
    )


def verify_wecom(ctx: SignatureContext) -> VerificationResult:
    """企业微信验签：`msg_signature = SHA1("".join(sorted([token, timestamp, nonce, aes_key])))`。

    参数可来自 URL query 或 JSON 回调体（`MsgSignature`/`timestamp`/`nonce`）。
    """
    tokens = [
        value
        for value in (ctx.secrets.verification_token, ctx.secrets.app_secret)
        if value and value.strip()
    ]
    if not tokens:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.SECRET_NOT_CONFIGURED,
            detail="verification_token 未配置",
        )

    signature = ctx.get("msg_signature", "msgsignature", "signature", "sign")
    if not signature:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_SIGNATURE,
            detail="msg_signature",
        )

    ts_raw = ctx.get("timestamp")
    if not ts_raw:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_TIMESTAMP, detail="timestamp"
        )

    nonce = ctx.get("nonce")
    if not nonce:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_SIGNATURE, detail="nonce"
        )

    timestamp = _parse_timestamp(ts_raw)
    if timestamp is None:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MALFORMED_TIMESTAMP
        )

    now = ctx.now if ctx.now is not None else time.time()
    if not _in_window(timestamp, now, ctx.tolerance):
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.TIMESTAMP_OUT_OF_WINDOW
        )

    aes_key = (ctx.secrets.encrypt_key or "").strip()
    for token in tokens:
        base_string = "".join(sorted([token.strip(), str(ts_raw), str(nonce), aes_key]))
        if _compare_hex(_sha1_hex(base_string), signature):
            return VerificationResult(True, ctx.platform, SignatureFailureReason.OK)

    return VerificationResult(
        False, ctx.platform, SignatureFailureReason.SIGNATURE_MISMATCH
    )


def verify_slack(ctx: SignatureContext) -> VerificationResult:
    """Slack 验签：`hex(HMAC-SHA256(signing_secret, f"v0:{ts}:{raw_body}"))`。

    `X-Slack-Signature` 形如 `v0=<hex>`。注意是 **hex** 而非 Base64。
    """
    keys = ctx.secrets.signing_keys()
    if not keys:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.SECRET_NOT_CONFIGURED,
            detail="app_secret(Signing Secret) 未配置",
        )

    header = ctx.get("x-slack-signature", "slack-signature", "signature")
    if not header:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_SIGNATURE,
            detail="X-Slack-Signature",
        )

    ts_raw = ctx.get("x-slack-request-timestamp", "timestamp")
    if not ts_raw:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_TIMESTAMP,
            detail="X-Slack-Request-Timestamp",
        )

    timestamp = _parse_timestamp(ts_raw)
    if timestamp is None:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MALFORMED_TIMESTAMP
        )

    now = ctx.now if ctx.now is not None else time.time()
    if not _in_window(timestamp, now, ctx.tolerance):
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.TIMESTAMP_OUT_OF_WINDOW
        )

    candidate = header.strip()
    if not candidate.startswith("v0="):
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MALFORMED_SIGNATURE,
            detail="缺少 v0= 前缀",
        )
    provided = candidate[3:].strip()
    if not provided:
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MISSING_SIGNATURE
        )

    # 原始请求体按 bytes 参与签名，避免任何编码往返破坏签名
    try:
        base_bytes = b"v0:" + str(ts_raw).encode("utf-8") + b":" + (ctx.raw_body or b"")
    except (TypeError, ValueError):
        return VerificationResult(
            False, ctx.platform, SignatureFailureReason.MALFORMED_SIGNATURE
        )

    for key in keys:
        expected = hmac.new(
            key.encode("utf-8"), base_bytes, hashlib.sha256
        ).hexdigest()
        if _compare_hex(expected, provided):
            return VerificationResult(True, ctx.platform, SignatureFailureReason.OK)

    return VerificationResult(
        False, ctx.platform, SignatureFailureReason.SIGNATURE_MISMATCH
    )


# ============================================================
# 6. 注册表与调度
# ============================================================
VERIFIER_REGISTRY: Dict[str, Callable[[SignatureContext], VerificationResult]] = {
    "dingtalk": verify_dingtalk,
    "feishu": verify_feishu,
    "wecom": verify_wecom,
    "slack": verify_slack,
}

SUPPORTED_PLATFORMS = tuple(VERIFIER_REGISTRY.keys())


def verify_signature(ctx: SignatureContext) -> VerificationResult:
    """按平台分发验签。**本函数绝不抛异常**，任何异常都归一为 fail-closed 结果。"""
    platform = (ctx.platform or "").strip().lower()
    verifier = VERIFIER_REGISTRY.get(platform)
    if verifier is None:
        return VerificationResult(
            False, platform, SignatureFailureReason.UNSUPPORTED_PLATFORM
        )
    try:
        result = verifier(ctx)
    except Exception:
        # 验签器内部异常同样 fail-closed，绝不"验签失败就放行"
        logger.exception(
            "IM 验签器异常，按 fail-closed 拒绝 platform=%s", platform
        )
        return VerificationResult(
            False, platform, SignatureFailureReason.VERIFIER_ERROR
        )
    if not isinstance(result, VerificationResult):  # 防御：验签器返回非法结构
        logger.error("IM 验签器返回非法结果类型，按 fail-closed 拒绝 platform=%s", platform)
        return VerificationResult(
            False, platform, SignatureFailureReason.VERIFIER_ERROR
        )
    return result


async def verify_platform_signature(
    request: Any,
    platform: str,
    config: Any = None,
    *,
    timestamp_override: Optional[int] = None,
    body_fields: Optional[Mapping[str, Any]] = None,
    tolerance: Optional[int] = None,
) -> VerificationResult:
    """从 FastAPI `Request` 组装上下文并执行验签（fail-closed，永不抛异常）。

    Args:
        request: `fastapi.Request`。为 None（后台任务场景）时返回
            `missing_request_context`，调用方必须拒绝或要求传入有效 Proof。
        platform: 平台标识。
        config: `IMProviderConfig` 实例（提供密钥）。
        timestamp_override: 报文内时间戳兜底（仅当 header/query 均无时间戳时使用）。
        body_fields: 已解析的业务报文字段（企业微信 JSON 回调取 signature 用）。
        tolerance: 时间戳窗口秒数；None 时取 `Settings.IM_SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS`。

    Returns:
        VerificationResult: 验签结果。
    """
    platform = (platform or "").strip().lower()

    # 显式关闭开关：属于运维应急手段，仅记录 CRITICAL 日志（生产环境启动校验会拒绝）
    if not settings.IM_SIGNATURE_ENABLED:
        logger.critical(
            "IM 入站验签已被显式关闭（IM_SIGNATURE_ENABLED=false），"
            "platform=%s —— 所有入站请求将不做签名校验，存在伪造风险",
            platform,
        )
        return VerificationResult(
            True, platform, SignatureFailureReason.VERIFICATION_DISABLED, bypass=True
        )

    if platform not in VERIFIER_REGISTRY:
        return VerificationResult(
            False, platform, SignatureFailureReason.UNSUPPORTED_PLATFORM
        )

    if request is None:
        return VerificationResult(
            False, platform, SignatureFailureReason.MISSING_REQUEST_CONTEXT
        )

    effective_tolerance = (
        tolerance
        if tolerance is not None
        else int(settings.IM_SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS)
    )
    if effective_tolerance <= 0:
        # 配置异常时回退默认窗口，保持 fail-closed（而非关闭重放防护）
        logger.warning(
            "IM_SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS=%s 非法，回退默认值 %ss",
            effective_tolerance,
            DEFAULT_TOLERANCE_SECONDS,
        )
        effective_tolerance = DEFAULT_TOLERANCE_SECONDS

    try:
        raw_body = await request.body()
        headers = {key.lower(): value for key, value in request.headers.items()}
        query = dict(request.query_params)
    except Exception:
        logger.exception("读取 IM 原始请求失败，按 fail-closed 拒绝 platform=%s", platform)
        return VerificationResult(
            False, platform, SignatureFailureReason.VERIFIER_ERROR
        )

    ctx = SignatureContext(
        platform=platform,
        raw_body=raw_body or b"",
        headers=headers,
        query=query,
        body_fields=dict(body_fields or {}),
        secrets=ProviderSecrets.from_config(platform, config),
        timestamp_override=timestamp_override,
        tolerance=effective_tolerance,
    )
    return verify_signature(ctx)


# ============================================================
# 7. Proof 签发 / 校验
# ============================================================
def issue_signature_proof(result: VerificationResult) -> SignatureProof:
    """由验签结果签发 Proof。验签未通过时抛 ValueError（调用方须先判 ok）。

    [Issue #12 修复 D-01] 使用 `isinstance` 强类型守卫：
    仅凭 `getattr(result, "ok", False)` 判定会让任何含 `ok=True` 属性的
    鸭子类型对象（如外部可构造的同名类 / SimpleNamespace）都拿到**有效** Proof，
    等价于凭空伪造"已验签"凭据。故必须先确认它是本模块定义的 VerificationResult。

    Raises:
        ValueError: `result` 非 VerificationResult 实例，或 ok 为 False。
    """
    if not isinstance(result, VerificationResult) or not result.ok:
        raise ValueError("签名验证未通过，无法签发 SignatureProof")
    return SignatureProof(
        platform=result.platform,
        reason=result.reason,
        _sentinel=_PROOF_SENTINEL,
    )


def is_valid_signature_proof(proof: Any) -> bool:
    """校验 Proof 是否由本模块签发且有效。"""
    return isinstance(proof, SignatureProof) and proof.is_valid()


# ============================================================
# 8. 日志与响应辅助（脱敏）
# ============================================================
def log_signature_result(
    result: VerificationResult,
    *,
    source_ip: Optional[str] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """记录验签结果。**只输出 platform / reason / source_ip / 掩码标识**。

    严禁输出：密钥、完整签名、完整请求体。
    """
    context_bits = [f"platform={result.platform}", f"reason={result.reason}"]
    if source_ip:
        context_bits.append(f"source_ip={source_ip}")
    if result.detail:
        context_bits.append(f"detail={result.detail}")
    for key, value in (extra or {}).items():
        context_bits.append(f"{key}={value}")
    context = " ".join(context_bits)

    if result.ok and result.bypass:
        logger.critical("IM 入站验签被跳过（开关关闭）：%s", context)
    elif result.ok:
        logger.info("IM 入站验签通过：%s", context)
    else:
        logger.warning("IM 入站验签失败（已拒绝）：%s", context)


def rejection_detail(result: VerificationResult) -> Dict[str, Any]:
    """构造 401 响应体：`{"error": reason, "platform": provider}`，无任何敏感信息。"""
    return {"error": result.reason, "platform": result.platform}


def mask_identifier(value: Optional[str], keep: int = 8) -> str:
    """掩码 IM 用户标识（仅用于日志，避免明文 PII 落盘）。"""
    if not value:
        return "-"
    text = str(value)
    if len(text) <= keep:
        return text[:2] + "***"
    return f"{text[:keep]}***"