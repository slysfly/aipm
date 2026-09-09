import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

// PMI中国 AI-PM 前端构建配置
// 说明：本仓库源码此前在本地构建后仅上传 dist/，服务端缺少 index.html 与 vite.config。
// 现补齐以便服务端可独立重新构建。API 基址在运行时由 VITE_API_BASE 或默认 /api 决定，
// 与后端同源部署，无需在此写死后端地址。

// 自定义 plugin：每次 build 前清空 dist/assets 下的旧 chunk（保留 dist 根目录的 icon.svg/sw.js 等）
// 解决 emptyOutDir:false 导致同名 chunk 重复堆积的问题（同一组件在 dist/assets/ 出现 5-7 份不同 hash 旧文件）
const cleanAssetsPlugin = {
  name: "clean-assets-before-build",
  buildStart() {
    const assetsDir = path.resolve(process.cwd(), "dist", "assets");
    if (fs.existsSync(assetsDir)) {
      const files = fs.readdirSync(assetsDir);
      let n = 0;
      for (const f of files) {
        const p = path.join(assetsDir, f);
        try {
          if (fs.statSync(p).isFile()) {
            fs.unlinkSync(p);
            n += 1;
          }
        } catch (e) {
          // 忽略单个文件失败
        }
      }
      if (n > 0) {
        // eslint-disable-next-line no-console
        console.log(`[clean-assets] removed ${n} stale chunks from dist/assets/`);
      }
    }
  },
};

export default defineConfig({
  plugins: [react(), cleanAssetsPlugin],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: {
    outDir: "dist",
    // 保留 icon.svg / manifest.* / sw.js / offline.html 等根级静态资源，不被清空
    emptyOutDir: false,
    chunkSizeWarningLimit: 2500,
  },
});
