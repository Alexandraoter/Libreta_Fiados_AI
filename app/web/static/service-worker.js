// Service worker de Libreta de Fiados.
// Guarda en caché SOLO los archivos estáticos de la interfaz.
// Las llamadas a /api/ nunca se cachean: los saldos y movimientos siempre vienen del servidor.
const CACHE = "libreta-fiados-v2";
const ARCHIVOS = [
  "/", "/index.html", "/consultas.html", "/styles.css", "/pwa.js", "/manifest.json",
  "/icons/favicon.svg", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/apple-touch-icon.png",
];
const CONOCIDOS = new Set(ARCHIVOS);

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ARCHIVOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((claves) => Promise.all(
        claves.filter((k) => k.startsWith("libreta-fiados-") && k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// Estrategia: responde desde caché al instante y actualiza la copia en segundo plano.
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || !CONOCIDOS.has(url.pathname)) return;  // /api/ y el resto pasan directo

  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const guardada = await cache.match(req, { ignoreSearch: true });
    const red = fetch(req)
      .then((res) => { if (res.ok) cache.put(req, res.clone()); return res; })
      .catch(() => null);
    if (guardada) { e.waitUntil(red); return guardada; }
    return (await red) || (req.mode === "navigate" ? cache.match("/index.html") : Response.error());
  })());
});
