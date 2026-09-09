"""
官方插件子包。

各插件模块在被 import 时会自行调用 ``register_plugin`` 完成注册，
父包 ``app.services.integrations.__init__`` 会 import 本子包下的插件模块。
本文件保持为空即可（避免重复注册副作用）。
"""
