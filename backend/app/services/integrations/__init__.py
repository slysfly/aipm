"""
PMI中国 AI-PM 外部集成包。

此处 import 各官方插件模块，利用其在模块加载时调用 ``register_plugin`` 的
副作用，将插件填充进 ``plugin_sdk.PLUGIN_REGISTRY`` 全局注册表。
只要在应用任一位置 ``import app.services.integrations``（或 import 其任意子模块），
插件即完成注册，无需其它初始化步骤。
"""

from app.services.integrations import plugin_sdk  # noqa: F401  确保注册表先定义
from app.services.integrations.plugins import (  # noqa: F401  触发各插件注册
    webhook,
    slack,
    github,
    confluence,
    jenkins,
)
