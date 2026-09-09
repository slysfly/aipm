// 内存态令牌（会话级，不落 localStorage，避免 XSS 持久窃取）。
// 鉴权主通道为后端下发的 httpOnly Cookie（浏览器自动随请求携带，JS 不可读）；
// 此内存令牌仅作为同会话内的 Bearer 兜底。
// 独立成模块，避免 http 与 offline 层互相循环依赖。
let _sessionToken: string | null = null;
let _sessionRefreshToken: string | null = null;

export function setAuthToken(t: string | null) {
  _sessionToken = t;
}

export function getAuthToken(): string | null {
  return _sessionToken;
}

export function setRefreshToken(t: string | null) {
  _sessionRefreshToken = t;
}

export function getRefreshToken(): string | null {
  return _sessionRefreshToken;
}
