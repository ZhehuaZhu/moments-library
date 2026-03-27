const CACHE_NAME = "moments-library-pwa-v1";
const OFFLINE_URL = "/offline";
const CORE_ASSETS = [
    OFFLINE_URL,
    "/manifest.webmanifest",
    "/apple-touch-icon.png",
    "/static/pwa/icons/icon-192.png",
    "/static/pwa/icons/icon-512.png",
    "/static/pwa/icons/icon-maskable-512.png",
    "/static/css/style.css",
    "/static/js/app.js",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)),
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key)),
            ),
        ),
    );
    self.clients.claim();
});

function shouldHandleStaticAsset(url) {
    return (
        url.pathname.startsWith("/static/css/") ||
        url.pathname.startsWith("/static/js/") ||
        url.pathname.startsWith("/static/pwa/")
    );
}

self.addEventListener("fetch", (event) => {
    const { request } = event;

    if (request.method !== "GET") {
        return;
    }

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) {
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(() => caches.match(OFFLINE_URL)),
        );
        return;
    }

    if (!shouldHandleStaticAsset(url)) {
        return;
    }

    event.respondWith(
        caches.match(request).then((cachedResponse) => {
            const networkResponse = fetch(request)
                .then((response) => {
                    if (response.ok) {
                        const responseClone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
                    }
                    return response;
                })
                .catch(() => cachedResponse);

            return cachedResponse || networkResponse;
        }),
    );
});
