"""
PMI中国AI项目管理社区 - 邮件发送核心模块
支持通过 SMTP 发送文本/HTML 邮件；未配置 SMTP 时抛出明确异常，
避免对外表现为"发送成功"的假象。
"""

import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class EmailNotConfiguredException(Exception):
    """邮件服务未配置时抛出"""

    def __init__(self, message: str = "邮件服务未配置（SMTP_USER 为空），无法发送邮件"):
        self.message = message
        super().__init__(message)


async def send_email(
    to: List[str],
    subject: str,
    body: str,
    html: Optional[str] = None,
    from_addr: Optional[str] = None,
) -> dict:
    """
    发送邮件（异步）。

    Args:
        to: 收件人列表
        subject: 主题
        body: 纯文本正文
        html: HTML 正文（可选）
        from_addr: 发件人（默认取 settings.EMAILS_FROM）

    Returns:
        dict: {"success": bool, "to": [...], "message": str}

    Raises:
        EmailNotConfiguredException: 未配置 SMTP 凭证时
    """
    if not to:
        raise EmailNotConfiguredException("收件人列表为空")

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise EmailNotConfiguredException()

    from_addr = from_addr or settings.EMAILS_FROM
    smtp_host = settings.SMTP_HOST
    smtp_port = settings.SMTP_PORT

    def _send_sync():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to)
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(from_addr, to, msg.as_string())

    try:
        await asyncio.to_thread(_send_sync)
        logger.info(f"📧 邮件已发送 -> {to} 主题: {subject}")
        return {"success": True, "to": to, "message": "邮件发送成功"}
    except EmailNotConfiguredException:
        raise
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        raise EmailNotConfiguredException(f"邮件发送失败: {e}")
