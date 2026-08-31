import time
import math
import random
import uuid

from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ---------------------------------------------------------------------------
# Configuration de l'arène et des personnages
# ---------------------------------------------------------------------------
ARENA_W = 1000
ARENA_H = 700
TICK_RATE = 1 / 30.0  # 30 mises à jour / seconde
RESPAWN_DELAY = 3.0
PLAYER_RADIUS = 18
PROJECTILE_RADIUS = 5

CHARACTERS = {
    "forestier": {
        "label": "Forestier",
        "sprite": "forestier",
        "tint": None,
        "color": "#4FA8E8",
        "maxHealth": 110,
        "speed": 210,
        "damage": 9,
        "fireRate": 0.28,
        "projSpeed": 560,
        "range": 340,
    },
    "paysan": {
        "label": "Paysan",
        "sprite": "paysan",
        "tint": None,
        "color": "#5DBE7C",
        "maxHealth": 180,
        "speed": 130,
        "damage": 12,
        "fireRate": 0.6,
        "projSpeed": 420,
        "range": 260,
    },
    "paysan_elite": {
        "label": "Paysan d'Élite",
        "sprite": "paysan",
        "tint": "0xE8624F",
        "color": "#E8624F",
        "maxHealth": 85,
        "speed": 165,
        "damage": 26,
        "fireRate": 1.0,
        "projSpeed": 780,
        "range": 560,
    },
}

SPAWN_POINTS = [
    (60, 60), (ARENA_W - 60, 60),
    (60, ARENA_H - 60), (ARENA_W - 60, ARENA_H - 60),
    (ARENA_W // 2, 60), (ARENA_W // 2, ARENA_H - 60),
]

players = {}       # sid -> player dict
projectiles = {}   # id -> projectile dict


def random_spawn():
    return random.choice(SPAWN_POINTS)


def public_player(p):
    return {
        "id": p["id"],
        "name": p["name"],
        "type": p["type"],
        "sprite": p["sprite"],
        "tint": p["tint"],
        "color": p["color"],
        "x": p["x"],
        "y": p["y"],
        "angle": p["angle"],
        "health": p["health"],
        "maxHealth": p["maxHealth"],
        "alive": p["alive"],
        "moving": (abs(p["dx"]) > 0.01 or abs(p["dy"]) > 0.01),
        "shooting": p["shooting"],
        "lastShot": p["lastShot"],
        "justHit": p.get("justHit", 0),
        "justDied": p.get("justDied", 0),
        "kills": p["kills"],
        "deaths": p["deaths"],
    }


@app.route("/")
def index():
    return render_template("index.html", characters=CHARACTERS)


@socketio.on("connect")
def on_connect():
    pass


@socketio.on("disconnect")
def on_disconnect(*args, **kwargs):
    from flask import request
    sid = request.sid
    if sid in players:
        del players[sid]


@socketio.on("join")
def on_join(data):
    from flask import request
    sid = request.sid
    char_type = data.get("type") if data.get("type") in CHARACTERS else "forestier"
    char = CHARACTERS[char_type]
    x, y = random_spawn()

    players[sid] = {
        "id": sid,
        "name": (data.get("name") or "Joueur")[:16],
        "type": char_type,
        "sprite": char["sprite"],
        "tint": char["tint"],
        "color": char["color"],
        "x": x,
        "y": y,
        "angle": 0,
        "dx": 0,
        "dy": 0,
        "speed": char["speed"],
        "damage": char["damage"],
        "fireRate": char["fireRate"],
        "projSpeed": char["projSpeed"],
        "range": char["range"],
        "maxHealth": char["maxHealth"],
        "health": char["maxHealth"],
        "alive": True,
        "shooting": False,
        "lastShot": 0.0,
        "respawnAt": None,
        "justHit": 0,
        "justDied": 0,
        "kills": 0,
        "deaths": 0,
    }
    socketio.emit("joined", {"id": sid, "arena": {"w": ARENA_W, "h": ARENA_H}}, to=sid)


@socketio.on("input")
def on_input(data):
    from flask import request
    sid = request.sid
    p = players.get(sid)
    if not p or not p["alive"]:
        return
    dx = float(data.get("dx", 0) or 0)
    dy = float(data.get("dy", 0) or 0)
    norm = math.hypot(dx, dy)
    if norm > 1:
        dx, dy = dx / norm, dy / norm
    p["dx"], p["dy"] = dx, dy
    if "angle" in data:
        p["angle"] = float(data["angle"])
    if "shooting" in data:
        p["shooting"] = bool(data["shooting"])


def spawn_projectile(p):
    pid = str(uuid.uuid4())
    projectiles[pid] = {
        "id": pid,
        "owner": p["id"],
        "x": p["x"] + math.cos(p["angle"]) * (PLAYER_RADIUS + 4),
        "y": p["y"] + math.sin(p["angle"]) * (PLAYER_RADIUS + 4),
        "vx": math.cos(p["angle"]) * p["projSpeed"],
        "vy": math.sin(p["angle"]) * p["projSpeed"],
        "damage": p["damage"],
        "traveled": 0.0,
        "range": p["range"],
        "color": p["color"],
    }


def game_loop():
    last = time.time()
    while True:
        socketio.sleep(TICK_RATE)
        now = time.time()
        dt = now - last
        last = now

        # Mouvement + tir des joueurs
        for sid, p in list(players.items()):
            if not p["alive"]:
                if p["respawnAt"] and now >= p["respawnAt"]:
                    x, y = random_spawn()
                    p["x"], p["y"] = x, y
                    p["health"] = p["maxHealth"]
                    p["alive"] = True
                    p["respawnAt"] = None
                continue

            p["x"] += p["dx"] * p["speed"] * dt
            p["y"] += p["dy"] * p["speed"] * dt
            p["x"] = max(PLAYER_RADIUS, min(ARENA_W - PLAYER_RADIUS, p["x"]))
            p["y"] = max(PLAYER_RADIUS, min(ARENA_H - PLAYER_RADIUS, p["y"]))

            if p["shooting"] and (now - p["lastShot"]) >= p["fireRate"]:
                p["lastShot"] = now
                spawn_projectile(p)

        # Mouvement des projectiles + collisions
        for pid, proj in list(projectiles.items()):
            proj["x"] += proj["vx"] * dt
            proj["y"] += proj["vy"] * dt
            proj["traveled"] += math.hypot(proj["vx"] * dt, proj["vy"] * dt)

            if (proj["traveled"] > proj["range"] or proj["x"] < 0 or
                    proj["x"] > ARENA_W or proj["y"] < 0 or proj["y"] > ARENA_H):
                del projectiles[pid]
                continue

            hit_sid = None
            for sid, p in players.items():
                if sid == proj["owner"] or not p["alive"]:
                    continue
                dist = math.hypot(p["x"] - proj["x"], p["y"] - proj["y"])
                if dist <= PLAYER_RADIUS + PROJECTILE_RADIUS:
                    hit_sid = sid
                    break

            if hit_sid:
                target = players[hit_sid]
                target["health"] -= proj["damage"]
                target["justHit"] = now
                if target["health"] <= 0 and target["alive"]:
                    target["alive"] = False
                    target["justDied"] = now
                    target["deaths"] += 1
                    target["respawnAt"] = now + RESPAWN_DELAY
                    shooter = players.get(proj["owner"])
                    if shooter:
                        shooter["kills"] += 1
                del projectiles[pid]

        # Diffusion de l'état à tous les clients
        socketio.emit("state", {
            "players": [public_player(p) for p in players.values()],
            "projectiles": [
                {"id": pr["id"], "x": pr["x"], "y": pr["y"], "color": pr["color"]}
                for pr in projectiles.values()
            ],
        })


socketio.start_background_task(game_loop)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
