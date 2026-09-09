import React, { createContext, useContext, useEffect, useState } from "react";
import { authApi } from "../api";
import { getAuthToken, setAuthToken } from "../api/http";
import { getRefreshToken, setRefreshToken } from "../api/token";

interface AuthState {
  token: string | null;
  user: any;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  token: null,
  user: null,
  loading: true,
  login: async () => {},
  logout: () => {},
  refreshUser: async () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = async () => {
    // 内存态无 token：直接短路不发请求（避免 /auth/me 401 在浏览器 Network 红字 + React 警告）
    // 注意：Cookie 自动鉴权场景下 token 为 null 仍可能通过 withCredentials 恢复，
    // 因此先看是否有内存 token；没有则尝试一次 silent 请求（登录页首次加载用此路径探活）。
    if (!getAuthToken()) {
      try {
        const me = await authApi.me(); // silent: true（authApi 已设）
        if (me && me.access_token) {
          setAuthToken(me.access_token);
          setToken(me.access_token);
        }
        setUser(me?.user ?? me);
      } catch {
        setUser(null);
        setToken(null);
      } finally {
        setLoading(false);
      }
      return;
    }
    try {
      const me = await authApi.me();
      if (me && me.access_token) {
        setAuthToken(me.access_token);
        setToken(me.access_token);
        if (me.refresh_token) setRefreshToken(me.refresh_token);
      }
      setUser(me?.user ?? me);
    } catch {
      setAuthToken(null);
      setToken(null);
      setRefreshToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshUser();
  }, []);

  const login = async (username: string, password: string) => {
    setLoading(true);
    try {
      const res = await authApi.login(username, password);
      setAuthToken(res.access_token);
      setToken(res.access_token);
      if (res.refresh_token) setRefreshToken(res.refresh_token);
      const me = await authApi.me();
      if (me?.refresh_token) setRefreshToken(me.refresh_token);
      setUser(me?.user ?? me);
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    authApi.logout().catch(() => {});
    setAuthToken(null);
    setToken(null);
    setRefreshToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ token, user, loading, login, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
