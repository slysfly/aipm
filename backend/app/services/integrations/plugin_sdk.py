"""
PMI中国 AI-PM —— 应用市场 Plugin SDK

提供插件开发的基础抽象与全局注册表：
- ``BasePlugin``：所有插件（官方或第三方）应继承的基类。
- ``PLUGIN_REGISTRY``：插件 id -> 插件实例 的全局注册表。
- ``register_plugin`` / ``get_plugin`` / ``list_plugins``：注册与查询辅助函数。

插件在模块被 import 时通过 ``register_plugin(...)`` 完成副作用注册，
``integrations/__init__.py`` 会 import 各插件模块以触发这一注册过程。
"""

from typing import Dict, Any, List, Optional

# 全局插件注册表：插件 id -> 插件实例
PLUGIN_REGISTRY: Dict[str, "BasePlugin"] = {}


class BasePlugin:
    """
    插件抽象基类。

    子类必须设置以下元数据字段（建议在 ``__init__`` 中赋值）：
    - ``id``：全局唯一插件标识（用于安装 / 执行路由）。
    - ``name``：展示名称。
    - ``description``：一句话功能说明。
    - ``category``：分类（integration/automation/report/ai/utility）。
    - ``version``：语义化版本号。
    - ``config_schema``：描述所需配置的 JSON Schema（dict），用于前端渲染表单。

    子类必须实现 ``execute``：
    - ``context``：触发上下文，含 ``project_id`` / ``user_id`` / ``event`` 等。
    - ``config``：该项目安装时保存的配置（来自 AppInstallation.config）。
    - 返回值：dict，建议包含 ``ok`` 布尔字段；失败时返回 ``{"ok": False, "error": ...}``。
    """

    # 以下为默认占位值，子类应在 __init__ 中覆盖
    id: str = ""
    name: str = ""
    description: str = ""
    category: str = "integration"
    version: str = "1.0.0"
    config_schema: Dict[str, Any] = {}

    async def execute(self, context: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行插件逻辑。子类必须实现。

        :param context: 触发上下文，例如
            {"project_id": "...", "user_id": "...", "event": "task.created", ...}
        :param config: 该插件在本项目安装时保存的配置
        :return: 执行结果 dict，建议包含 ``ok`` 字段
        """
        raise NotImplementedError("插件必须实现 execute 方法")


def register_plugin(plugin: BasePlugin) -> None:
    """将插件实例注册到全局注册表（重复 id 会覆盖）。"""
    if not plugin or not getattr(plugin, "id", ""):
        raise ValueError("插件必须设置非空的 id 才能注册")
    PLUGIN_REGISTRY[plugin.id] = plugin


def get_plugin(plugin_id: str) -> Optional[BasePlugin]:
    """按 id 获取已注册插件，未找到返回 None。"""
    return PLUGIN_REGISTRY.get(plugin_id)


def list_plugins() -> List[BasePlugin]:
    """返回所有已注册插件实例列表。"""
    return list(PLUGIN_REGISTRY.values())
