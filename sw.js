/* Service worker de Mini Yolotzin: permite abrir la app sin conexión.
   Estrategia «red primero»: siempre intenta descargar la versión más reciente
   (para que los datos nuevos se vean en cuanto se publiquen) y, si no hay red,
   usa la copia guardada. Cambia CACHE al modificar la lista de archivos. */
const CACHE = 'mini-yolotzin-v7';
const FILES = [
  './', './index.html', './model-data.js', './metro-catalog.js', './weather-summary.js',
  './metro-diagram.js',
  './gtfs-segments.js', './route-engine.js', './route-planner-ui.js', './live-reports.js',
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
  const url = new URL(request.url);
  // Las cuentas (/api/) nunca se guardan en la copia sin conexión.
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.includes('/api/')) return;
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
