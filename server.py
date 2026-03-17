# =============================================================
#  Pepito Tracker — Serveur Flask
#  Hébergé sur Render.com ou Railway.app (gratuit)
#  
#  API :
#    POST /update  — reçoit position + données depuis le logiciel bord
#    GET  /data    — renvoie position + trace au navigateur web
#    GET  /        — sert la page de suivi
# =============================================================

from flask import Flask, request, jsonify, render_template
from datetime import datetime
import os
import json

app = Flask(__name__)

# ── Clé secrète partagée avec le logiciel bord ───────────────
# À changer avant déploiement !
API_KEY = os.environ.get("PEPITO_API_KEY", "pepito2026secret")

# ── Stockage en mémoire ───────────────────────────────────────
# (persist jusqu'au redémarrage du serveur)
state = {
    "boat_name":   "Pepito",
    "last_update": None,
    "online":      False,
    "lat":         None,
    "lon":         None,
    "speed":       0.0,
    "cap":         0,
    "distance":    0.0,
    "engine":      "0.00 h",
    "sail":        "0.00 h",
    "trace":       [],          # Liste de [lat, lon]
    "events":      [],          # Derniers événements
}

MAX_TRACE  = 5000   # Points GPS max en mémoire
MAX_EVENTS = 50     # Événements max conservés


# =============================================================
#  POST /update — reçu depuis le logiciel bord toutes les 30s
# =============================================================

@app.route("/update", methods=["POST"])
def update():
    # Vérification clé API
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data"}), 400

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    state["last_update"] = now
    state["online"]      = True
    state["boat_name"]   = data.get("boat_name",  state["boat_name"])
    state["lat"]         = data.get("lat")
    state["lon"]         = data.get("lon")
    state["speed"]       = data.get("speed",    0.0)
    state["cap"]         = data.get("cap",      0)
    state["distance"]    = data.get("distance", 0.0)
    state["engine"]      = data.get("engine",   "0.00 h")
    state["sail"]        = data.get("sail",     "0.00 h")

    # Ajouter à la trace si position valide
    if state["lat"] and state["lon"]:
        state["trace"].append([state["lat"], state["lon"]])
        if len(state["trace"]) > MAX_TRACE:
            state["trace"] = state["trace"][-MAX_TRACE:]

    # Événement optionnel
    event = data.get("event")
    if event:
        state["events"].insert(0, {
            "time":  now,
            "event": event
        })
        state["events"] = state["events"][:MAX_EVENTS]

    return jsonify({"status": "ok"}), 200


# =============================================================
#  GET /data — consulté par la page web toutes les 15s
# =============================================================

@app.route("/data")
def get_data():
    return jsonify(state)


# =============================================================
#  GET / — page de suivi
# =============================================================

@app.route("/")
def index():
    return render_template("index.html", boat_name=state["boat_name"])


# =============================================================
#  GET /offline — endpoint pour signaler la déconnexion
# =============================================================

@app.route("/offline", methods=["POST"])
def offline():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    state["online"] = False
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
