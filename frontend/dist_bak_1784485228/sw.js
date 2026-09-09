const CACHE_NAME = 'ai-pm-pwa-v1'
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon.svg',
  '/src/main.tsx',
]

const OFFLINE_PAGE = `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>离线 - AI-PM</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
      background: #f8fafc; color: #0f172a;
      display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 24px;
    }
    .offline-container { text-align: center; max-width: 400px; }
    .offline-icon { width: 80px; height: 80px; margin: 0 auto 24px; background: #cffafe; border-radius: 24px; display: flex; align-items: center; justify-content: center; }
    .offline-icon svg { width: 40px; height: 40px; color: #0891b2; }
    h1 { font-size: 24px; font-weight: 700; margin-bottom: 12px; }
    p { font-size: 16px; color: #64748b; margin-bottom: 24px; line-height: 1.6; }
    .retry-btn {
      display: inline-flex; align-items: center; gap: 8px; padding: 12px 24px;
      background: #0891b2; color: #fff; border: none; border-radius: 12px; font-size: 14px; font-weight: 600; cursor: pointer;
    }
    .retry-btn:hover { background: #06b6d4; }
  </style>
</head>
<body>
  <div class="offline-container">
    <div class="offline-icon">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
      </svg>
    </div>
    <h1>您当前处于离线状态</h1>
    <p>请检查网络连接后重试。已缓存的内容仍可正常访问。</p>
    <button class="retry-btn" onclick="window.location.reload()">重新加载</button>
  </div>
</body>
</html>
`

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) =>
      Promise.all(cacheNames.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    ).then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => new Response(OFFLINE_PAGE, { headers: { 'Content-Type': 'text/html; charset=utf-8' } })))
    return
  }
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached
      return fetch(request).then((response) => {
        if (!response || response.status !== 200 || response.type !== 'basic') return response
        // Only cache GET / HEAD requests – Cache API rejects POST/PUT/DELETE
        if (request.method !== 'GET' && request.method !== 'HEAD') return response
        const copy = response.clone()
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy))
        return response
      }).catch(() => {
        if (request.destination === 'image') return new Response('', { status: 204 })
        return new Response('Network error', { status: 408 })
      })
    })
  )
})

self.addEventListener('push', (event) => {
  if (!event.data) return
  const data = event.data.json()
  event.waitUntil(
    self.registration.showNotification(data.title || 'AI-PM 通知', {
      body: data.body || '', icon: '/icon.svg', badge: '/icon.svg',
      tag: data.tag || 'default', requireInteraction: data.requireInteraction || false, data: data.payload || {},
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((list) => {
      if (list.length > 0) { list[0].focus(); list[0].postMessage({ type: 'NOTIFICATION_CLICK', payload: event.notification.data }) }
      else self.clients.openWindow('/')
    })
  )
})
