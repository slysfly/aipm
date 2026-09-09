// PMI中国 AI-PM Service Worker
// 策略（v3 修复：静态资源改为网络优先，解决部署后用户仍加载旧缓存的问题）：
// - 静态资源（JS/CSS/字体/图标）：网络优先，失败回退到缓存（v2 是缓存优先，已导致多次部署不生效）
// - API 请求（/api/）：网络优先，失败回退到缓存
// - HTML 导航：网络优先，失败回退到离线页
// - WS（/api/v1/ws/）：不缓存，直接放行

const CACHE_VERSION = "ai-pm-v29";
const OFFLINE_URL = "/offline.html";

const PRECACHE_URLS = [
  "/",
  "/offline.html",
  "/manifest.webmanifest",
  "/icon.svg",
];

// ============== 安装：预缓存核心资源 ==============
self.addEventListener("install", (event) => {
  console.log("[SW] install");
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

// ============== 激活：清理旧缓存 ==============
self.addEventListener("activate", (event) => {
  console.log("[SW] activate");
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_VERSION)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ============== 拦截请求 ==============
self.addEventListener("fetch", (event) => {
  const req = event.request;

  // 仅处理 HTTP/HTTPS 请求（过滤掉 chrome-extension://、chrome:// 等）
  if (!req.url.startsWith("http://") && !req.url.startsWith("https://")) {
    return;
  }

  const url = new URL(req.url);

  // WebSocket 请求：直接放行
  if (req.url.startsWith("ws://") || req.url.startsWith("wss://")) {
    return;
  }

  // API 请求（GET）：网络优先，失败回退缓存
  if (url.pathname.startsWith("/api/")) {
    if (req.method === "GET") {
      event.respondWith(networkFirst(req));
    }
    // 非 GET API 请求不拦截
    return;
  }

  // HTML 导航：网络优先，失败回退离线页
  if (req.mode === "navigate" || (req.method === "GET" && req.headers.get("accept")?.includes("text/html"))) {
    event.respondWith(networkFirstWithOffline(req));
    return;
  }

  // 静态资源：网络优先（v3 修复：确保部署后立即生效，不再被旧缓存阻塞）
  if (req.method === "GET" && /\.(js|css|svg|png|jpg|jpeg|gif|woff2?|ttf|ico)$/.test(url.pathname)) {
    event.respondWith(networkFirst(req));
    return;
  }

  // 其他 GET：尝试网络，失败回退缓存
  if (req.method === "GET") {
    event.respondWith(networkFirst(req));
  }
});

// ============== 缓存策略函数 ==============

async function cacheFirst(req) {
  const cache = await caches.open(CACHE_VERSION);
  const cached = await cache.match(req);
  if (cached) {
    // 后台更新
    fetch(req).then((res) => {
      if (res && res.status === 200) {
        cache.put(req, res.clone());
      }
    }).catch(() => {});
    return cached;
  }
  try {
    const res = await fetch(req);
    if (res && res.status === 200) {
      cache.put(req, res.clone());
    }
    return res;
  } catch (e) {
    return cached || new Response("离线", { status: 503 });
  }
}

async function networkFirst(req) {
  const cache = await caches.open(CACHE_VERSION);
  try {
    const res = await fetch(req);
    if (res && res.status === 200) {
      cache.put(req, res.clone());
    }
    return res;
  } catch (e) {
    const cached = await cache.match(req);
    return cached || new Response(JSON.stringify({ error: "offline" }), {
      status: 503,
      headers: { "Content-Type": "application/json" }
    });
  }
}

async function networkFirstWithOffline(req) {
  try {
    const res = await fetch(req);
    const cache = await caches.open(CACHE_VERSION);
    cache.put(req, res.clone());
    return res;
  } catch (e) {
    const cache = await caches.open(CACHE_VERSION);
    const cached = await cache.match(req);
    return cached || (await cache.match(OFFLINE_URL)) || new Response("离线", { status: 503 });
  }
}

// ============== 消息：客户端可强制更新 ==============
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") {
    self.skipWaiting();
  }
  if (event.data === "CLEAR_CACHE") {
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => caches.delete(k)))
    ).then(() => {
      event.source?.postMessage({ type: "CACHE_CLEARED" });
    });
  }
});
