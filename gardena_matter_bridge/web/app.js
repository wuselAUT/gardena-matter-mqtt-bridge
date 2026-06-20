"use strict";

function $(id) { return document.getElementById(id); }

// Sprach-Erkennung wie die uebrige UI / die Gateway-Seite:
// navigator.language 'de'* -> Deutsch, sonst Englisch.
function detectLang() {
  var nav = (navigator.language || navigator.userLanguage || "en").toLowerCase();
  return nav.indexOf("de") === 0 ? "de" : "en";
}

// Spec verbatim. Beide Sprachen, damit die Sprachwahl der UI folgt.
var DONE_HINT = {
  de: "Fertig. Die Bridge läuft jetzt eigenständig auf dem Gateway — du kannst " +
      "dieses Add-on stoppen. Öffne es nur wieder, um die Bridge zu aktualisieren.",
  en: "Done. The bridge now runs standalone on the gateway — you can stop this " +
      "add-on. Re-open it only to update the bridge."
};

function doneHintText() {
  var lang = detectLang();
  return DONE_HINT[lang] || DONE_HINT.en;
}

function setText(id, value, fallback) {
  $(id).textContent = (value === undefined || value === null || value === "")
    ? (fallback || "—") : String(value);
}

function renderDeploy(deploy) {
  setText("deploy-state", deploy.state, "idle");
  $("deploy-state").className = "badge badge-" + (deploy.state || "idle");
  setText("deploy-message", deploy.message, "");
  const ol = $("deploy-steps");
  ol.innerHTML = "";
  (deploy.steps || []).forEach(function (step) {
    const li = document.createElement("li");
    li.textContent = step;
    ol.appendChild(li);
  });

  // nach erfolgreichem Deploy die dezente Standalone-Notiz zeigen
  // (sprachabhaengig DE/EN). Bei jedem anderen Status ausblenden.
  const note = $("done-note");
  if (deploy.state === "success") {
    note.textContent = doneHintText();
    note.hidden = false;
  } else {
    note.textContent = "";
    note.hidden = true;
  }
}

function renderGateway(gw) {
  setText("bridge-summary", gw.summary, "Status unbekannt.");
  setText("gateway-host", gw.gateway_host, "—");
  setText("updated-at", gw.updated_at, "—");
  setText("manual-code", gw.manual_code, "—");
  setText("qr-payload", gw.qr_payload, "—");

  const win = $("commissioning-window");
  if (gw.commissioning === "open" && gw.commissioning_remaining > 0) {
    win.textContent = "Commissioning-Fenster offen (~" +
      gw.commissioning_remaining + "s verbleibend).";
  } else if (gw.commissioning === "closed") {
    win.textContent = "Commissioning-Fenster geschlossen — bei Bedarf auf der " +
      "Gateway-Seite erneut öffnen.";
  } else {
    win.textContent = "";
  }

  const link = $("gateway-link");
  if (gw.gateway_matter_url) {
    link.href = gw.gateway_matter_url;
  }
}

function refresh() {
  fetch("api/status")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      renderDeploy(data.deploy || {});
      const gw = data.gateway || {};
      // summary serverseitig optional; sonst hier minimal ableiten.
      if (!gw.summary) {
        gw.summary = gw.bridge_active ? "Bridge aktiv." :
          (gw.reachable ? "Bridge inaktiv." : "Bridge noch nicht deployt.");
      }
      renderGateway(gw);
    })
    .catch(function () {
      setText("bridge-summary", "Status konnte nicht geladen werden.");
    });
}

$("redeploy-btn").addEventListener("click", function () {
  $("deploy-hint").textContent = "Sende Deploy-Anforderung …";
  fetch("api/deploy", { method: "POST" })
    .then(function (r) { return r.json(); })
    .then(function (res) {
      $("deploy-hint").textContent = res.message || "";
    })
    .catch(function () {
      $("deploy-hint").textContent = "Deploy-Anforderung fehlgeschlagen.";
    });
});

refresh();
setInterval(refresh, 5000);
