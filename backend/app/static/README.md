# PMI中国 AI-PM · 静态资源目录

本目录存放后端直接服务的静态资源：

- `favicon.svg` — 站点图标（橙红渐变 T 字 logo）
- `robots.txt` — 搜索引擎爬虫规则
- 可扩展：站点 logo、默认头像等

## 路由

通过 `app/serve.py` 的 `StaticFiles` 挂载到 `/static` 路径。
