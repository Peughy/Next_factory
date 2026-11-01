"""FOYER — application Flask de maison connectée."""

from __future__ import annotations

import random
import threading
import time
from copy import deepcopy
from datetime import datetime
from typing import Any

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

_lock = threading.Lock()


@app.context_processor
def inject_boot():
    return {"boot": snapshot()}


def _now() -> str:
    return datetime.now().strftime("%H:%M")


def _iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _event(kind: str, title: str, detail: str, severity: str = "info") -> dict[str, Any]:
    return {
        "id": int(time.time() * 1000) + random.randint(0, 99),
        "kind": kind,
        "title": title,
        "detail": detail,
        "severity": severity,
        "time": _now(),
        "iso": _iso(),
    }


STATE: dict[str, Any] = {
    "house": {
        "name": "Siège Alpha",
        "armed": False,
        "presence": True,
        "power_kw": 1.42,
        "humidity": 46,
        "air_quality": 92,
    },
    "climate": {
        "mode": "auto",
        "target": 21.5,
        "fan": 2,
    },
    "sensors": {
        "temperature": {
            "label": "Température",
            "unit": "°C",
            "value": 21.4,
            "status": "ok",
            "room": "bureau",
            "updated": _now(),
        },
        "rfid": {
            "label": "RFID",
            "last_uid": "A4:91:C2:18",
            "last_name": "Camille",
            "authorized": True,
            "status": "ok",
            "updated": _now(),
        },
        "motion": {
            "label": "Mouvement",
            "detected": False,
            "zone": "salle de réunion",
            "status": "ok",
            "updated": _now(),
        },
        "smoke": {
            "label": "Fumée",
            "level": 4,
            "alarm": False,
            "status": "ok",
            "updated": _now(),
        },
    },
    "rooms": [
        {
            "id": "bureau",
            "name": "Salle de réunion",
            "floor": "Siège",
            "temperature": 21.6,
            "occupied": True,
            "lights": True,
            "brightness": 78,
            "shutters": 70,
            "lock": False,
        },
    ],
    "badges": [
        {"uid": "A4:91:C2:18", "name": "Camille", "role": "Directrice", "active": True},
        {"uid": "B1:07:E9:44", "name": "Léa", "role": "Collaboratrice", "active": True},
        {"uid": "C8:33:AA:01", "name": "Visiteur", "role": "Invité", "active": False},
    ],
    "scenes": [
        {
            "id": "home",
            "name": "Ouverture",
            "desc": "Lumières opérationnelles, climat 21,5 °C, sécurité désarmée.",
        },
        {
            "id": "away",
            "name": "Fermeture",
            "desc": "Système éteint, volets fermés, alarme armée.",
        },
        {
            "id": "night",
            "name": "Mode nuit",
            "desc": "Éclairage faible, température 19 °C, accès verrouillé.",
        },
        {
            "id": "movie",
            "name": "Réunion",
            "desc": "Salle préparée, éclairage doux et ambiance de travail.",
        },
    ],
    "events": [
        _event("rfid", "Accès autorisé", "Badge Camille — accès au siège", "ok"),
        _event("temp", "Climat stabilisé", "Salle de réunion à 21,4 °C", "info"),
        _event("motion", "Zone calme", "Aucun mouvement détecté", "info"),
        _event("smoke", "Air sain", "Niveau fumée 4 % — aucun risque", "ok"),
    ],
    "history": {
        "temperature": [20.8, 21.0, 21.2, 21.1, 21.4, 21.6, 21.5, 21.4],
        "smoke": [3, 4, 4, 5, 4, 3, 4, 4],
        "motion": [0, 1, 0, 0, 1, 0, 0, 0],
        "power": [0.9, 1.1, 1.6, 1.4, 1.3, 1.5, 1.42, 1.38],
    },
}


def _room(room_id: str) -> dict[str, Any] | None:
    for room in STATE["rooms"]:
        if room["id"] == room_id:
            return room
    return None


def _push_event(event: dict[str, Any]) -> None:
    STATE["events"].insert(0, event)
    STATE["events"] = STATE["events"][:40]


def _avg_temp() -> float:
    temps = [r["temperature"] for r in STATE["rooms"]]
    return round(sum(temps) / len(temps), 1)


def snapshot() -> dict[str, Any]:
    with _lock:
        data = deepcopy(STATE)
    data["sensors"]["temperature"]["value"] = _avg_temp()
    data["kpis"] = {
        "rooms_on": sum(1 for r in data["rooms"] if r["lights"]),
        "rooms_total": len(data["rooms"]),
        "locked": sum(1 for r in data["rooms"] if r["lock"]),
        "occupied": sum(1 for r in data["rooms"] if r["occupied"]),
        "alerts": sum(
            1
            for e in data["events"]
            if e["severity"] in ("warn", "danger") and e.get("iso", "").startswith(datetime.now().strftime("%Y-%m-%d"))
        ),
    }
    smoke = data["sensors"]["smoke"]
    motion = data["sensors"]["motion"]
    data["security"] = {
        "level": "alerte" if smoke["alarm"] else ("vigilance" if motion["detected"] and data["house"]["armed"] else "serein"),
        "door": next((r["lock"] for r in data["rooms"] if r["id"] == "entree"), False),
        "garage": next((r["lock"] for r in data["rooms"] if r["id"] == "garage"), False),
    }
    return data


@app.route("/")
def dashboard():
    return render_template("dashboard.html", page="dashboard", title="Tableau de bord")


@app.route("/pieces")
def rooms():
    return render_template("rooms.html", page="rooms", title="Pièces")


@app.route("/securite")
def security():
    return render_template("security.html", page="security", title="Sécurité")


@app.route("/climat")
def climate():
    return render_template("climate.html", page="climate", title="Climat")


@app.route("/scenarios")
def scenes():
    return render_template("scenes.html", page="scenes", title="Scénarios")


@app.route("/activite")
def activity():
    return render_template("activity.html", page="activity", title="Activité")


@app.route("/parametres")
def settings():
    return render_template("settings.html", page="settings", title="Paramètres")


@app.get("/api/status")
def api_status():
    return jsonify(snapshot())


@app.post("/api/rooms/<room_id>")
def api_room(room_id: str):
    payload = request.get_json(silent=True) or {}
    with _lock:
        room = _room(room_id)
        if not room:
            return jsonify({"error": "Pièce inconnue"}), 404
        for key in ("lights", "brightness", "shutters", "lock", "occupied"):
            if key in payload:
                room[key] = payload[key]
        if payload.get("lights") is False:
            room["brightness"] = room.get("brightness", 0)
        label = room["name"]
        if "lights" in payload:
            _push_event(
                _event(
                    "light",
                    f"{label} — lumières {'allumées' if room['lights'] else 'éteintes'}",
                    f"Intensité {room['brightness']} %",
                    "info",
                )
            )
        if "lock" in payload:
            _push_event(
                _event(
                    "lock",
                    f"{label} — {'verrouillée' if room['lock'] else 'déverrouillée'}",
                    "Commande depuis l’application",
                    "ok" if room["lock"] else "warn",
                )
            )
    return jsonify(snapshot())


@app.post("/api/house")
def api_house():
    payload = request.get_json(silent=True) or {}
    with _lock:
        if "armed" in payload:
            STATE["house"]["armed"] = bool(payload["armed"])
            _push_event(
                _event(
                    "alarm",
                    "Alarme armée" if STATE["house"]["armed"] else "Alarme désarmée",
                    "Système de sécurité mis à jour",
                    "ok" if STATE["house"]["armed"] else "warn",
                )
            )
        if "name" in payload:
            STATE["house"]["name"] = str(payload["name"])[:48]
    return jsonify(snapshot())


@app.post("/api/climate")
def api_climate():
    payload = request.get_json(silent=True) or {}
    with _lock:
        climate = STATE["climate"]
        if "target" in payload:
            climate["target"] = max(16.0, min(28.0, float(payload["target"])))
        if "mode" in payload and payload["mode"] in ("off", "auto", "heat", "cool"):
            climate["mode"] = payload["mode"]
        if "fan" in payload:
            climate["fan"] = max(0, min(3, int(payload["fan"])))
        _push_event(
            _event(
                "temp",
                f"Consigne {climate['target']:.1f} °C",
                f"Mode {climate['mode']} · ventilation {climate['fan']}",
                "info",
            )
        )
    return jsonify(snapshot())


@app.post("/api/scenes/<scene_id>")
def api_scene(scene_id: str):
    with _lock:
        if scene_id == "home":
            STATE["house"]["armed"] = False
            STATE["house"]["presence"] = True
            STATE["climate"]["target"] = 21.5
            STATE["climate"]["mode"] = "auto"
            for room in STATE["rooms"]:
                room["occupied"] = room["id"] in ("salon", "entree")
                room["lights"] = room["id"] in ("salon", "entree", "cuisine")
                room["brightness"] = 70 if room["lights"] else 20
                room["lock"] = room["id"] in ("garage",)
                if room["id"] == "entree":
                    room["lock"] = False
            _push_event(_event("scene", "Scénario « Je rentre »", "Maison prête à vous accueillir", "ok"))
        elif scene_id == "away":
            STATE["house"]["armed"] = True
            STATE["house"]["presence"] = False
            STATE["climate"]["mode"] = "off"
            for room in STATE["rooms"]:
                room["lights"] = False
                room["occupied"] = False
                room["shutters"] = 0
                room["lock"] = True
            _push_event(_event("scene", "Scénario « Je sors »", "Maison sécurisée et éteinte", "ok"))
        elif scene_id == "night":
            STATE["house"]["armed"] = True
            STATE["climate"]["target"] = 19.0
            STATE["climate"]["mode"] = "auto"
            for room in STATE["rooms"]:
                room["occupied"] = room["id"] == "chambre"
                room["lights"] = room["id"] == "entree"
                room["brightness"] = 18 if room["id"] == "entree" else 0
                room["shutters"] = 0
                room["lock"] = room["id"] in ("entree", "garage")
            _push_event(_event("scene", "Scénario « Bonne nuit »", "Chemin lumineux et consigne 19 °C", "ok"))
        elif scene_id == "movie":
            STATE["house"]["armed"] = False
            for room in STATE["rooms"]:
                if room["id"] == "salon":
                    room["lights"] = True
                    room["brightness"] = 18
                    room["shutters"] = 0
                    room["occupied"] = True
                else:
                    room["lights"] = False
                    room["occupied"] = False
            _push_event(_event("scene", "Scénario « Cinéma »", "Salon tamisé, volets baissés", "info"))
        else:
            return jsonify({"error": "Scénario inconnu"}), 404
    return jsonify(snapshot())


@app.post("/api/rfid/simulate")
def api_rfid_simulate():
    payload = request.get_json(silent=True) or {}
    uid = payload.get("uid")
    with _lock:
        badge = next((b for b in STATE["badges"] if b["uid"] == uid), None)
        if badge is None:
            badge = next((b for b in STATE["badges"] if b["active"]), STATE["badges"][0])
        allowed = bool(badge["active"])
        STATE["sensors"]["rfid"].update(
            {
                "last_uid": badge["uid"],
                "last_name": badge["name"],
                "authorized": allowed,
                "status": "ok" if allowed else "danger",
                "updated": _now(),
            }
        )
        if allowed:
            entree = _room("entree")
            if entree:
                entree["lock"] = False
                entree["lights"] = True
            _push_event(_event("rfid", f"Badge {badge['name']}", "Accès autorisé — entrée ouverte", "ok"))
        else:
            _push_event(_event("rfid", f"Badge {badge['name']}", "Accès refusé — badge inactif", "danger"))
    return jsonify(snapshot())


@app.post("/api/badges/<uid>/toggle")
def api_badge_toggle(uid: str):
    with _lock:
        badge = next((b for b in STATE["badges"] if b["uid"] == uid), None)
        if not badge:
            return jsonify({"error": "Badge inconnu"}), 404
        badge["active"] = not badge["active"]
        _push_event(
            _event(
                "rfid",
                f"Badge {badge['name']}",
                "Activé" if badge["active"] else "Désactivé",
                "ok" if badge["active"] else "warn",
            )
        )
    return jsonify(snapshot())


@app.post("/api/alerts/ack")
def api_ack():
    with _lock:
        STATE["sensors"]["smoke"]["alarm"] = False
        STATE["sensors"]["smoke"]["level"] = 6
        STATE["sensors"]["smoke"]["status"] = "ok"
        STATE["sensors"]["motion"]["detected"] = False
        STATE["sensors"]["motion"]["status"] = "ok"
        _push_event(_event("smoke", "Alertes acquittées", "Capteurs de fumée et de mouvement réarmés", "ok"))
    return jsonify(snapshot())


def _simulate() -> None:
    """Variation réaliste des capteurs pour la démo live."""
    while True:
        time.sleep(4)
        with _lock:
            climate = STATE["climate"]
            for room in STATE["rooms"]:
                drift = (climate["target"] - room["temperature"]) * (0.08 if climate["mode"] != "off" else 0.01)
                noise = random.uniform(-0.12, 0.12)
                room["temperature"] = round(room["temperature"] + drift + noise, 1)
            STATE["sensors"]["temperature"]["value"] = _avg_temp()
            STATE["sensors"]["temperature"]["updated"] = _now()

            smoke = STATE["sensors"]["smoke"]
            if not smoke["alarm"]:
                smoke["level"] = max(1, min(18, smoke["level"] + random.choice([-1, 0, 0, 1])))
            smoke["alarm"] = smoke["level"] >= 35
            smoke["status"] = "danger" if smoke["alarm"] else "ok"
            smoke["updated"] = _now()

            if random.random() < 0.08:
                zone = random.choice(["entrée", "salon", "garage", "cuisine"])
                was_detected = STATE["sensors"]["motion"]["detected"]
                STATE["sensors"]["motion"]["detected"] = True
                STATE["sensors"]["motion"]["zone"] = zone
                STATE["sensors"]["motion"]["updated"] = _now()
                occupied_id = {"entrée": "entree", "salon": "salon", "garage": "garage", "cuisine": "cuisine"}[zone]
                room = _room(occupied_id)
                if room:
                    room["occupied"] = True
                if STATE["house"]["armed"]:
                    STATE["sensors"]["motion"]["status"] = "warn"
                    if not was_detected:
                        _push_event(
                            _event("motion", "Mouvement inattendu", f"Détection dans {zone} alors que l’alarme est armée", "warn")
                        )
                else:
                    STATE["sensors"]["motion"]["status"] = "ok"
            elif random.random() < 0.45:
                STATE["sensors"]["motion"]["detected"] = False
                STATE["sensors"]["motion"]["status"] = "ok"
                STATE["sensors"]["motion"]["updated"] = _now()

            hist = STATE["history"]
            hist["temperature"].append(STATE["sensors"]["temperature"]["value"])
            hist["smoke"].append(smoke["level"])
            hist["motion"].append(1 if STATE["sensors"]["motion"]["detected"] else 0)
            hist["power"].append(round(0.7 + sum(0.18 for r in STATE["rooms"] if r["lights"]) + random.uniform(0, 0.2), 2))
            for key in hist:
                hist[key] = hist[key][-12:]

            STATE["house"]["power_kw"] = hist["power"][-1]
            STATE["house"]["humidity"] = max(35, min(62, STATE["house"]["humidity"] + random.choice([-1, 0, 0, 1])))


def _maybe_smoke_demo() -> None:
    time.sleep(90)
    with _lock:
        if not STATE["sensors"]["smoke"]["alarm"]:
            STATE["sensors"]["smoke"]["level"] = 42
            STATE["sensors"]["smoke"]["alarm"] = True
            STATE["sensors"]["smoke"]["status"] = "danger"
            _push_event(_event("smoke", "Alerte fumée", "Seuil critique dépassé — vérifiez la cuisine", "danger"))


threading.Thread(target=_simulate, daemon=True).start()
threading.Thread(target=_maybe_smoke_demo, daemon=True).start()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
