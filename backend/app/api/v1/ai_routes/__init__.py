"""
PMI中国AI项目管理社区 - AI路由包
按逻辑分组整合AI相关路由
"""

from app.api.v1.ai_routes.chat import router as chat_router
from app.api.v1.ai_routes.agent import router as agent_router
from app.api.v1.ai_routes.nlp import router as nlp_router
from app.api.v1.ai_routes.assist import router as assist_router
from app.api.v1.ai_routes.monitor import router as monitor_router
from app.api.v1.ai_routes.pmbok_v3 import router as pmbok_v3_router
