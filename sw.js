/* Service worker de Mini Yolotzin: permite abrir la app sin conexión.
   Estrategia «red primero»: siempre intenta descargar la versión más reciente
   (para que los datos nuevos se vean en cuanto se publiquen) y, si no hay red,
   usa la copia guardada. Cambia CACHE al modificar la lista de archivos. */
const CACHE = 'mini-yolotzin-v1';
const FILES = [
  './', './index.html', './model-data.js', './metro-catalog.js', './weather-summary.js',
  './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png', './icons/icon-maskable-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return;
  event.respondWith(
    fetch(request)
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request, { ignoreSearch: true }).then(hit => hit || caches.match('./index.html')))
  );
});
