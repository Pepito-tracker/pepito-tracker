# =============================================================
#  server.py — Pepito Tracker (multi-bateaux, sans état)
#  À déployer sur Render. Start command :
#      gunicorn server:app
#  requirements.txt : flask, gunicorn
#
#  Sécurité : l'ID public = sha256(boat_token)[:12]. Impossible
#  de pousser une position sans connaître le token du bateau.
#  Aucun compte, aucune base : positions live en mémoire.
# =============================================================

import time
import hashlib
from flask import Flask, request, jsonify, abort, Response

app = Flask(__name__)

# boat_id -> dict(données + ts + online)
BOATS = {}
OFFLINE_AFTER = 120   # secondes sans /update => hors-ligne


def _id_from_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


@app.post("/update")
def update():
    token = request.headers.get("X-Boat-Token", "")
    if not token:
        abort(401)
    bid = _id_from_token(token)
    data = request.get_json(force=True, silent=True) or {}
    data["ts"]     = time.time()
    data["online"] = True
    BOATS[bid] = data
    return jsonify({"ok": True, "id": bid})


@app.post("/offline")
def offline():
    token = request.headers.get("X-Boat-Token", "")
    if token:
        bid = _id_from_token(token)
        if bid in BOATS:
            BOATS[bid]["online"] = False
    return jsonify({"ok": True})


@app.get("/b/<bid>/data")
def boat_data(bid):
    d = BOATS.get(bid)
    if not d:
        return jsonify({"found": False})
    age    = time.time() - d.get("ts", 0)
    online = d.get("online", False) and age < OFFLINE_AFTER
    out = dict(d)
    out["found"]  = True
    out["online"] = online
    out["age_s"]  = int(age)
    return jsonify(out)


@app.get("/b/<bid>")
def boat_map(bid):
    return Response(MAP_HTML.replace("__BID__", bid), mimetype="text/html")


@app.get("/")
def home():
    return "Pepito Tracker — CapLog (Pepito Marine Labs)"


MAP_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Position — CapLog</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root{ --bg:#071a2f; --accent:#35c2ff; --on:#2ecc71; --off:#ff5c5c; --border:#1d436d; }
  html,body{margin:0;height:100%;background:var(--bg);font-family:system-ui,sans-serif;color:#fff;}
  #map{height:100vh;width:100vw;}
  #hud{position:absolute;top:12px;left:12px;z-index:1000;background:rgba(7,26,47,.92);
       border:1px solid var(--border);border-radius:10px;padding:12px 14px;min-width:180px;}
  #hud .t{font-weight:700;color:var(--accent);margin-bottom:6px;}
  #hud .l{font-size:13px;opacity:.85;margin:2px 0;}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;}
  .on{background:var(--on);} .off{background:var(--off);}
</style>
</head>
<body>
<div id="hud">
  <div class="t">CapLog</div>
  <div class="l"><span id="state-dot" class="dot off"></span><span id="state">connexion…</span></div>
  <div class="l" id="pos">—</div>
  <div class="l" id="spd">—</div>
</div>
<div id="map"></div>
<script>
const BID = "__BID__";
const map = L.map('map').setView([46.4962, -1.7841], 8);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);

let marker = null, trace = L.polyline([], {color:'#35c2ff', weight:3}).addTo(map);
let firstFix = true;

async function poll(){
  try{
    const r = await fetch(`/b/${BID}/data`, {cache:'no-store'});
    const d = await r.json();
    if(!d.found){ setState(false, 'aucune position'); return; }

    const lat = d.lat, lon = d.lon;
    if(lat != null && lon != null){
      const ll = [lat, lon];
      if(!marker){ marker = L.circleMarker(ll, {radius:8, color:'#fff',
                     fillColor:'#2ecc71', fillOpacity:1, weight:2}).addTo(map); }
      marker.setLatLng(ll);
      marker.setStyle({fillColor: d.online ? '#2ecc71' : '#ff5c5c'});
      trace.addLatLng(ll);
      if(firstFix){ map.setView(ll, 12); firstFix = false; }
      document.getElementById('pos').textContent =
        `${lat.toFixed(4)}°, ${lon.toFixed(4)}°`;
    }
    if(d.sog != null || d.speed != null){
      document.getElementById('spd').textContent =
        `${(d.sog ?? d.speed).toFixed(1)} nds`;
    }
    setState(d.online, d.online ? 'en navigation' :
             `dernière position il y a ${Math.round((d.age_s||0)/60)} min`);
  }catch(e){ setState(false, 'serveur injoignable'); }
}

function setState(online, txt){
  document.getElementById('state').textContent = txt;
  document.getElementById('state-dot').className = 'dot ' + (online ? 'on':'off');
}

poll();
setInterval(poll, 15000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
