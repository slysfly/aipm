// vite.config.ts
import { defineConfig } from "file:///C:/Users/visua/Downloads/Codebuddy-AI-PM/AI-PM-Installer/frontend/node_modules/vite/dist/node/index.js";
import react from "file:///C:/Users/visua/Downloads/Codebuddy-AI-PM/AI-PM-Installer/frontend/node_modules/@vitejs/plugin-react/dist/index.js";
var vite_config_default = defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // API 已通过 VITE_API_BASE 直接锁定到 8000 端口，无需再走代理
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 2e3,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/")) return "vendor";
          if (id.includes("node_modules/antd")) return "antd";
          if (id.includes("node_modules/@ant-design")) return "antd";
          if (id.includes("node_modules/echarts")) return "charts";
          if (id.includes("node_modules/@dnd-kit")) return "dnd";
          if (id.includes("node_modules/framer-motion")) return "motion";
          if (id.includes("node_modules/@tiptap")) return "editor";
          if (id.includes("node_modules/react-big-calendar") || id.includes("node_modules/moment")) return "calendar";
        }
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJDOlxcXFxVc2Vyc1xcXFx2aXN1YVxcXFxEb3dubG9hZHNcXFxcQ29kZWJ1ZGR5LUFJLVBNXFxcXEFJLVBNLUluc3RhbGxlclxcXFxmcm9udGVuZFwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiQzpcXFxcVXNlcnNcXFxcdmlzdWFcXFxcRG93bmxvYWRzXFxcXENvZGVidWRkeS1BSS1QTVxcXFxBSS1QTS1JbnN0YWxsZXJcXFxcZnJvbnRlbmRcXFxcdml0ZS5jb25maWcudHNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL0M6L1VzZXJzL3Zpc3VhL0Rvd25sb2Fkcy9Db2RlYnVkZHktQUktUE0vQUktUE0tSW5zdGFsbGVyL2Zyb250ZW5kL3ZpdGUuY29uZmlnLnRzXCI7aW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSBcInZpdGVcIjtcclxuaW1wb3J0IHJlYWN0IGZyb20gXCJAdml0ZWpzL3BsdWdpbi1yZWFjdFwiO1xyXG5cclxuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcclxuICBwbHVnaW5zOiBbcmVhY3QoKV0sXHJcbiAgc2VydmVyOiB7XHJcbiAgICBwb3J0OiA1MTczLFxyXG4gICAgLy8gQVBJIFx1NURGMlx1OTAxQVx1OEZDNyBWSVRFX0FQSV9CQVNFIFx1NzZGNFx1NjNBNVx1OTUwMVx1NUI5QVx1NTIzMCA4MDAwIFx1N0FFRlx1NTNFM1x1RkYwQ1x1NjVFMFx1OTcwMFx1NTE4RFx1OEQ3MFx1NEVFM1x1NzQwNlxyXG4gICAgcHJveHk6IHtcclxuICAgICAgXCIvYXBpXCI6IHtcclxuICAgICAgICB0YXJnZXQ6IHByb2Nlc3MuZW52LlZJVEVfQVBJX1RBUkdFVCB8fCBcImh0dHA6Ly9sb2NhbGhvc3Q6ODAwMFwiLFxyXG4gICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcclxuICAgICAgfSxcclxuICAgIH0sXHJcbiAgfSxcclxuICBidWlsZDoge1xyXG4gICAgb3V0RGlyOiBcImRpc3RcIixcclxuICAgIHNvdXJjZW1hcDogZmFsc2UsXHJcbiAgICBjaHVua1NpemVXYXJuaW5nTGltaXQ6IDIwMDAsXHJcbiAgICByb2xsdXBPcHRpb25zOiB7XHJcbiAgICAgIG91dHB1dDoge1xyXG4gICAgICAgIG1hbnVhbENodW5rcyhpZDogc3RyaW5nKSB7XHJcbiAgICAgICAgICBpZiAoaWQuaW5jbHVkZXMoXCJub2RlX21vZHVsZXMvcmVhY3QtZG9tXCIpIHx8IGlkLmluY2x1ZGVzKFwibm9kZV9tb2R1bGVzL3JlYWN0L1wiKSkgcmV0dXJuIFwidmVuZG9yXCI7XHJcbiAgICAgICAgICBpZiAoaWQuaW5jbHVkZXMoXCJub2RlX21vZHVsZXMvYW50ZFwiKSkgcmV0dXJuIFwiYW50ZFwiO1xyXG4gICAgICAgICAgaWYgKGlkLmluY2x1ZGVzKFwibm9kZV9tb2R1bGVzL0BhbnQtZGVzaWduXCIpKSByZXR1cm4gXCJhbnRkXCI7XHJcbiAgICAgICAgICBpZiAoaWQuaW5jbHVkZXMoXCJub2RlX21vZHVsZXMvZWNoYXJ0c1wiKSkgcmV0dXJuIFwiY2hhcnRzXCI7XHJcbiAgICAgICAgICBpZiAoaWQuaW5jbHVkZXMoXCJub2RlX21vZHVsZXMvQGRuZC1raXRcIikpIHJldHVybiBcImRuZFwiO1xyXG4gICAgICAgICAgaWYgKGlkLmluY2x1ZGVzKFwibm9kZV9tb2R1bGVzL2ZyYW1lci1tb3Rpb25cIikpIHJldHVybiBcIm1vdGlvblwiO1xyXG4gICAgICAgICAgaWYgKGlkLmluY2x1ZGVzKFwibm9kZV9tb2R1bGVzL0B0aXB0YXBcIikpIHJldHVybiBcImVkaXRvclwiO1xyXG4gICAgICAgICAgaWYgKGlkLmluY2x1ZGVzKFwibm9kZV9tb2R1bGVzL3JlYWN0LWJpZy1jYWxlbmRhclwiKSB8fCBpZC5pbmNsdWRlcyhcIm5vZGVfbW9kdWxlcy9tb21lbnRcIikpIHJldHVybiBcImNhbGVuZGFyXCI7XHJcbiAgICAgICAgfSxcclxuICAgICAgfSxcclxuICAgIH0sXHJcbiAgfSxcclxufSk7XHJcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBbVksU0FBUyxvQkFBb0I7QUFDaGEsT0FBTyxXQUFXO0FBRWxCLElBQU8sc0JBQVEsYUFBYTtBQUFBLEVBQzFCLFNBQVMsQ0FBQyxNQUFNLENBQUM7QUFBQSxFQUNqQixRQUFRO0FBQUEsSUFDTixNQUFNO0FBQUE7QUFBQSxJQUVOLE9BQU87QUFBQSxNQUNMLFFBQVE7QUFBQSxRQUNOLFFBQVEsUUFBUSxJQUFJLG1CQUFtQjtBQUFBLFFBQ3ZDLGNBQWM7QUFBQSxNQUNoQjtBQUFBLElBQ0Y7QUFBQSxFQUNGO0FBQUEsRUFDQSxPQUFPO0FBQUEsSUFDTCxRQUFRO0FBQUEsSUFDUixXQUFXO0FBQUEsSUFDWCx1QkFBdUI7QUFBQSxJQUN2QixlQUFlO0FBQUEsTUFDYixRQUFRO0FBQUEsUUFDTixhQUFhLElBQVk7QUFDdkIsY0FBSSxHQUFHLFNBQVMsd0JBQXdCLEtBQUssR0FBRyxTQUFTLHFCQUFxQixFQUFHLFFBQU87QUFDeEYsY0FBSSxHQUFHLFNBQVMsbUJBQW1CLEVBQUcsUUFBTztBQUM3QyxjQUFJLEdBQUcsU0FBUywwQkFBMEIsRUFBRyxRQUFPO0FBQ3BELGNBQUksR0FBRyxTQUFTLHNCQUFzQixFQUFHLFFBQU87QUFDaEQsY0FBSSxHQUFHLFNBQVMsdUJBQXVCLEVBQUcsUUFBTztBQUNqRCxjQUFJLEdBQUcsU0FBUyw0QkFBNEIsRUFBRyxRQUFPO0FBQ3RELGNBQUksR0FBRyxTQUFTLHNCQUFzQixFQUFHLFFBQU87QUFDaEQsY0FBSSxHQUFHLFNBQVMsaUNBQWlDLEtBQUssR0FBRyxTQUFTLHFCQUFxQixFQUFHLFFBQU87QUFBQSxRQUNuRztBQUFBLE1BQ0Y7QUFBQSxJQUNGO0FBQUEsRUFDRjtBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
