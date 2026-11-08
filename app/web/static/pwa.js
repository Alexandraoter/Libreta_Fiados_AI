// Registra el service worker (solo funciona en HTTPS o en localhost).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => { });
  });
}
