// Fundus – Kamera-Scanner für QR-Codes (Etiketten) und ISBN-Strichcodes.
// Nutzt die eingebaute BarcodeDetector-Schnittstelle des Browsers, sonst die
// lokal ausgelieferte ZXing-Bibliothek (WebAssembly). Lädt nichts aus dem Internet.
(function () {
  "use strict";

  const root = document.getElementById("scanner");
  if (!root) return;

  const video = root.querySelector("video");
  const status = root.querySelector("[data-status]");
  const startButton = root.querySelector("[data-start]");
  const mode = root.dataset.mode; // "exemplar" oder "isbn"
  const target = root.dataset.target;
  const formats = ["qr_code", "ean_13", "ean_8", "code_128"];
  let stream = null;
  let done = false;

  function say(text) {
    status.textContent = text;
  }

  async function detector() {
    if ("BarcodeDetector" in window) {
      try {
        const supported = await window.BarcodeDetector.getSupportedFormats();
        if (supported.includes("qr_code")) {
          return new window.BarcodeDetector({ formats: formats.filter((f) => supported.includes(f)) });
        }
      } catch (e) {
        /* weiter mit der mitgelieferten Bibliothek */
      }
    }
    const api = window.BarcodeDetectionAPI;
    api.setZXingModuleOverrides({ locateFile: () => root.dataset.wasm });
    return new api.BarcodeDetector({ formats: formats });
  }

  function isbnFrom(value) {
    const digits = value.replace(/[^0-9Xx]/g, "");
    return /^(97[89]\d{10}|\d{9}[\dXx])$/.test(digits) ? digits : null;
  }

  function handle(value) {
    if (done) return;
    value = value.trim();
    if (mode === "isbn") {
      const isbn = isbnFrom(value);
      if (!isbn) {
        say("Das ist keine ISBN. Bitte den Strichcode auf der Buchrückseite scannen.");
        return;
      }
      value = isbn;
    }
    done = true;
    if (navigator.vibrate) navigator.vibrate(80);
    say("Erkannt: " + value);
    stop();
    window.location.href = target.replace("__CODE__", encodeURIComponent(value));
  }

  function stop() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }

  async function start() {
    if (!window.isSecureContext || !navigator.mediaDevices) {
      say("Die Kamera funktioniert nur über eine sichere Verbindung (https). Bitte die Nummer eintippen.");
      return;
    }
    startButton.hidden = true;
    say("Kamera wird gestartet …");
    let scan;
    try {
      scan = await detector();
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 } },
        audio: false,
      });
    } catch (error) {
      startButton.hidden = false;
      say(
        error && error.name === "NotAllowedError"
          ? "Kein Zugriff auf die Kamera. Bitte in den Browser-Einstellungen erlauben oder die Nummer eintippen."
          : "Die Kamera konnte nicht gestartet werden. Bitte die Nummer eintippen."
      );
      return;
    }
    video.srcObject = stream;
    await video.play();
    say("Code ins Bild halten …");

    const tick = async () => {
      if (done || !stream) return;
      if (video.readyState >= 2) {
        try {
          const codes = await scan.detect(video);
          if (codes.length) handle(codes[0].rawValue);
        } catch (e) {
          /* einzelnes Bild nicht lesbar – weiter */
        }
      }
      window.setTimeout(tick, 150);
    };
    tick();
  }

  startButton.addEventListener("click", start);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stop();
    } else if (!done && !stream) {
      startButton.hidden = false;
      say("Kamera pausiert.");
    }
  });
  window.addEventListener("pagehide", stop);
  // Ohne Klick starten, wo der Browser es erlaubt (z. B. App vom Startbildschirm).
  start();
})();
