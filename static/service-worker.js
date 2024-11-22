const CACHE_NAME = "translator-v1";
const urlsToCache = [
  "/static/manifest.json",
  "/static/images/icon-192x192.png",
  "/static/images/icon-512x512.png",
  "/static/css/styles.css",
  "/static/js/main.js"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(urlsToCache))
  );
});

self.addEventListener("fetch", (event) => {
  // URL 객체 생성
  const url = new URL(event.request.url);
  
  // API 요청이나 동적 컨텐츠는 항상 네트워크를 통해 가져옴
  if (event.request.method === "POST" || 
      url.pathname.startsWith("/translate") || 
      url.pathname.startsWith("/login") || 
      url.pathname.startsWith("/logout")) {
    event.respondWith(fetch(event.request));
    return;
  }

  // 정적 자원은 캐시 우선, 네트워크 폴백 전략 사용
  event.respondWith(
    caches.match(event.request).then((response) => {
      if (response) {
        return response;
      }
      return fetch(event.request).then((response) => {
        // 유효한 응답인 경우에만 캐시에 저장
        if (!response || response.status !== 200 || response.type !== "basic") {
          return response;
        }

        const responseToCache = response.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, responseToCache);
        });

        return response;
      });
    })
  );
});
