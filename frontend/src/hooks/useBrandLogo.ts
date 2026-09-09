/**
 * useBrandLogo - 品牌 Logo 共享 Hook
 *
 * 从 /api/v1/system/brand-logo 获取品牌 Logo 信息，
 * 所有组件（侧边栏 / 登录页 / 设置页）共用同一份数据。
 *
 * 返回值：
 *   logoUrl    - 图片 URL（有上传时为完整路径，无则为 null）
 *   hasLogo    - 是否已设置 Logo
 *   isLoading  - 加载中
 *   refresh()  - 强制刷新（上传后调用）
 */

import { useState, useEffect, useCallback } from "react";
import { get } from "../api/http";

interface BrandInfo {
  has_logo: boolean;
  logo_url: string | null;
  filename?: string;
  mime_type?: string;
  size_bytes?: number;
  uploaded_at?: string;
}

export function useBrandLogo() {
  const [info, setInfo] = useState<BrandInfo>({ has_logo: false, logo_url: null });
  const [isLoading, setIsLoading] = useState(true);

  const fetchLogo = useCallback(async () => {
    try {
      const data = await get("/system/brand-logo");
      setInfo({
        has_logo: data.has_logo || false,
        logo_url: data.has_logo ? data.logo_url : null,
        filename: data.filename,
        mime_type: data.mime_type,
        size_bytes: data.size_bytes,
        uploaded_at: data.uploaded_at,
      });
    } catch {
      setInfo({ has_logo: false, logo_url: null });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogo();
  }, [fetchLogo]);

  return {
    // 对外暴露 camelCase 别名（与组件解构一致），同时保留 snake_case 以兼容旧调用
    logoUrl: info.logo_url,
    hasLogo: info.has_logo,
    ...info,
    isLoading,
    refresh: fetchLogo,
  };
}
