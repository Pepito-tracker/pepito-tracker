# =============================================================
#  server.py — Pepito Tracker (multi-bateaux, sans état)
#  Page web de suivi servie à la famille/aux proches.
#  Start command : gunicorn server:app
#  requirements.txt : flask, gunicorn
# =============================================================

import time
import hashlib
from flask import Flask, request, jsonify, abort, Response

app = Flask(__name__)

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
    return ("Pepito Tracker — CapLog (Pepito Marine Labs). "
            "Le lien de suivi de chaque bateau se trouve dans l'app "
            "CapLog -> Reglages -> Tracker live.")


MAP_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Position — CapLog</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root{ --bg:#071a2f; --panel:#0a2742; --accent:#35c2ff; --on:#2ecc71;
         --off:#ff5c5c; --orange:#ff9f1c; --border:#1d436d; --muted:#5a8aaa; }
  html,body{margin:0;height:100%;background:var(--bg);font-family:system-ui,sans-serif;color:#fff;}
  #map{height:100vh;width:100vw;}
  #hud{position:absolute;top:12px;left:12px;z-index:1000;
       background:rgba(7,26,47,.94);border:1px solid var(--border);
       border-radius:12px;padding:14px 16px;min-width:210px;
       box-shadow:0 4px 18px rgba(0,0,0,.4);}
  #hud .title{font-weight:800;color:var(--accent);font-size:16px;
              letter-spacing:.5px;margin-bottom:2px;}
  #hud .boat{font-size:12px;color:#cfe6f5;margin-bottom:8px;}
  #hud .state{display:flex;align-items:center;font-size:12px;
              margin-bottom:10px;color:#cfe6f5;}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;}
  .on{background:var(--on);box-shadow:0 0 8px var(--on);} .off{background:var(--off);}
  #hud .grid{display:grid;grid-template-columns:auto auto;gap:6px 18px;}
  #hud .lbl{font-size:9px;color:var(--muted);letter-spacing:1.2px;text-transform:uppercase;}
  #hud .val{font-size:18px;font-weight:700;line-height:1;}
  #hud .val .u{font-size:10px;font-weight:500;color:var(--muted);margin-left:2px;}
  #hud .prop{margin-top:10px;font-size:13px;font-weight:600;}
  #hud .prop.moteur{color:var(--off);} #hud .prop.voile{color:var(--on);}
  #hud .prop.idle{color:var(--muted);}
  #hud .durs{margin-top:8px;display:flex;gap:14px;border-top:1px solid var(--border);padding-top:8px;}
  #hud .durs .lbl{margin-bottom:2px;}
  #hud .durs .d{font-size:14px;font-weight:700;}
  #hud .durs .moteur{color:var(--off);} #hud .durs .voile{color:var(--on);}
  #hud .upd{margin-top:8px;font-size:9px;color:var(--muted);}
</style>
</head>
<body>
<div id="hud">
  <div class="title">CapLog</div>
  <div class="boat" id="boat">—</div>
  <div class="state"><span id="dot" class="dot off"></span><span id="state">connexion…</span></div>
  <div class="grid">
    <div><div class="lbl">Vitesse</div><div class="val"><span id="spd">—</span><span class="u">nds</span></div></div>
    <div><div class="lbl">Cap</div><div class="val"><span id="cap">—</span><span class="u">°</span></div></div>
    <div><div class="lbl">Distance</div><div class="val"><span id="dist">—</span><span class="u">NM</span></div></div>
    <div><div class="lbl">Position</div><div class="val" style="font-size:12px;font-weight:600" id="pos">—</div></div>
  </div>
  <div class="prop idle" id="prop">—</div>
  <div class="durs">
    <div><div class="lbl">Moteur</div><div class="d moteur" id="dmoteur">—</div></div>
    <div><div class="lbl">Voile</div><div class="d voile" id="dvoile">—</div></div>
  </div>
  <div class="upd" id="upd"></div>
</div>
<div id="map"></div>
<script>
const BID = "__BID__";
const map = L.map('map', { zoomControl:false }).setView([46.4962, -1.7841], 8);
L.control.zoom({ position:'topright' }).addTo(map);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);

let marker = null, trace = L.polyline([], {color:'#35c2ff', weight:3}).addTo(map);
let firstFix = true;

function fmt(v, d){ return (v==null || isNaN(v)) ? '—' : Number(v).toFixed(d); }
function dur(m){
  if(m==null || isNaN(m)) return '—';
  m = Math.round(m);
  const h = Math.floor(m/60), mn = m%60;
  return h>0 ? (h+'h'+String(mn).padStart(2,'0')) : (mn+' min');
}

async function poll(){
  try{
    const r = await fetch('/b/' + BID + '/data', {cache:'no-store'});
    const d = await r.json();
    if(!d.found){ setState(false, 'aucune position'); return; }

    document.getElementById('boat').textContent = d.boat_name || 'Bateau';

    const lat = d.lat, lon = d.lon;
    if(lat != null && lon != null && !(lat===0 && lon===0)){
      const ll = [lat, lon];
      if(!marker){ marker = L.circleMarker(ll, {radius:8, color:'#fff',
                     fillColor:'#2ecc71', fillOpacity:1, weight:2}).addTo(map); }
      marker.setLatLng(ll);
      marker.setStyle({fillColor: d.online ? '#2ecc71' : '#ff5c5c'});
      trace.addLatLng(ll);
      if(firstFix){ map.setView(ll, 12); firstFix = false; }
      document.getElementById('pos').textContent =
        lat.toFixed(4) + '°, ' + lon.toFixed(4) + '°';
    }

    document.getElementById('spd').textContent  = fmt(d.speed, 1);
    document.getElementById('cap').textContent  = (d.cap==null) ? '—' : Math.round(d.cap);
    document.getElementById('dist').textContent = fmt(d.distance, 1);

    const prop = document.getElementById('prop');
    if(d.engine){ prop.textContent = '\u2699 ' + d.engine; prop.className = 'prop moteur'; }
    else if(d.sail){ prop.textContent = '\u26F5 ' + d.sail; prop.className = 'prop voile'; }
    else { prop.textContent = '—'; prop.className = 'prop idle'; }

    document.getElementById('dmoteur').textContent = dur(d.duree_moteur);
    document.getElementById('dvoile').textContent  = dur(d.duree_voile);

    setState(d.online, d.online ? 'en navigation' :
             'hors-ligne — il y a ' + Math.round((d.age_s||0)/60) + ' min');

    const min = Math.round((d.age_s||0)/60);
    document.getElementById('upd').textContent =
      d.online ? "mis a jour a l'instant" : ('dernier point il y a ' + min + ' min');
  }catch(e){ setState(false, 'serveur injoignable'); }
}

function setState(online, txt){
  document.getElementById('state').textContent = txt;
  document.getElementById('dot').className = 'dot ' + (online ? 'on':'off');
}

poll();
setInterval(poll, 15000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
