/// <reference lib="webworker" />

const CACHE_NAME = "voxel-v1";
const STATIC_ASSETS = ["/", "/manifest.json", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (event) => {
	event.waitUntil(
		caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
	);
	self.skipWaiting();
});

self.addEventListener("activate", (event) => {
	event.waitUntil(
		caches.keys().then((keys) =>
			Promise.all(
				keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
			)
		)
	);
	self.clients.claim();
});

self.addEventListener("fetch", (event) => {
	const { request } = event;
	const url = new URL(request.url);

	// Let API, WebSocket, and server requests pass through to network
	if (
		url.pathname.startsWith("/api") ||
		url.pathname.startsWith("/ws") ||
		url.pathname.startsWith("/config") ||
		url.pathname.startsWith("/devices") ||
		url.pathname.startsWith("/profiles") ||
		url.pathname.startsWith("/roots") ||
		url.pathname.startsWith("/session")
	) {
		return;
	}

	// Static assets: try cache first, fall back to network, update cache
	event.respondWith(
		caches.match(request).then(
			(cached) =>
				cached ||
				fetch(request).then((response) => {
					if (response.ok) {
						const clone = response.clone();
						caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
					}
					return response;
				})
		)
	);
});
