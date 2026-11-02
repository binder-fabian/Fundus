"""Installierbare Web-App: Manifest, Service Worker und Offline-Seite."""

from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control

SERVICE_WORKER = """// Fundus – Service Worker: macht die App installierbar und zeigt ohne
// Verbindung eine Hinweisseite. Daten werden bewusst nicht offline gespeichert.
const CACHE = "fundus-v1";
const OFFLINE = "%(offline)s";
const ASSETS = [OFFLINE, "%(css)s", "%(icon)s"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE)));
  }
});
"""


@login_not_required
@cache_control(max_age=3600)
def manifest(request):
    return JsonResponse(
        {
            "name": "Fundus",
            "short_name": "Fundus",
            "description": "Katalog und Ausleihe der Schule",
            "lang": "de",
            "start_url": reverse("home"),
            "scope": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#0b5cad",
            "icons": [
                {
                    "src": static("fundus/icons/icon-192.png"),
                    "sizes": "192x192",
                    "type": "image/png",
                },
                {
                    "src": static("fundus/icons/icon-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                },
                {
                    "src": static("fundus/icons/icon-maskable-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
            "shortcuts": [{"name": "Scannen", "url": reverse("scanner")}],
        },
        content_type="application/manifest+json",
    )


@login_not_required
@cache_control(max_age=0, no_cache=True)
def service_worker(request):
    body = SERVICE_WORKER % {
        "offline": reverse("offline"),
        "css": static("fundus/fundus.css"),
        "icon": static("fundus/icons/icon-192.png"),
    }
    response = HttpResponse(body, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


@login_not_required
def offline(request):
    return render(request, "core/offline.html")
