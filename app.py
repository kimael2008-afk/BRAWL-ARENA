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
# --- Taille du monde : la carte de base (1000x700) est répétée en tuiles ---
TILE_W = 1000
TILE_H = 700
WORLD_TILES_X = 3
WORLD_TILES_Y = 3
ARENA_W = TILE_W * WORLD_TILES_X
ARENA_H = TILE_H * WORLD_TILES_Y
TICK_RATE = 1 / 30.0  # 30 mises à jour / seconde
RESPAWN_DELAY = 3.0
PLAYER_RADIUS = 18
PROJECTILE_RADIUS = 5

# --- Armes au sol ---
MAX_WEAPONS_ON_GROUND = 16
WEAPON_SPAWN_CHANCE_PER_TICK = 0.04
WEAPON_PICKUP_RADIUS = 26

WEAPON_TYPES = {
    "fists": {"label": "Poings", "color": "#8b90a0", "damage": 4, "fireRate": 0.45, "projSpeed": 420, "range": 180},
    "sword": {"label": "Épée", "color": "#4FA8E8", "damage": 8, "fireRate": 0.30, "projSpeed": 560, "range": 300},
    "axe": {"label": "Hache", "color": "#5DBE7C", "damage": 6, "fireRate": 0.20, "projSpeed": 700, "range": 480},
    "mace": {"label": "Masse", "color": "#E8624F", "damage": 14, "fireRate": 0.65, "projSpeed": 380, "range": 220},
}
MAX_MONSTERS = 18
MONSTER_SPAWN_CHANCE_PER_TICK = 0.05
SLIME_RADIUS = 16
SLIME_HEALTH = 30
SLIME_LIFESPAN = 60.0   # secondes avant disparition si pas tué
SLIME_KILL_REWARD = 1   # ajouté au compteur de kills du tueur
SLIME_SPEED = 55
SLIME_CONTACT_DAMAGE = 3
SLIME_CONTACT_COOLDOWN = 1.2  # secondes entre deux morsures sur le même joueur

# Obstacles solides (arbres, rochers, palissades) repérés sur une tuile de fond
# (espace 1000x700), puis répétés sur toute la grille du monde.
_BASE_OBSTACLES = [
    (90, 80, 95),    # grande canopée haut-gauche
    (520, 380, 62),  # arbre isolé avec tronc visible
    (870, 560, 82),  # bosquet bas-droite
    (955, 610, 65),  # second arbre bas-droite
    (160, 160, 34), (230, 140, 34), (300, 150, 34), (370, 170, 34),
    (430, 190, 34), (480, 220, 34), (510, 250, 30),  # palissade tressée (haut)
    (300, 300, 34), (220, 330, 34), (150, 360, 34),
    (90, 390, 34), (60, 430, 30),                    # palissade tressée (bas)
]

OBSTACLES = [
    (bx + tx * TILE_W, by + ty * TILE_H, br)
    for ty in range(WORLD_TILES_Y)
    for tx in range(WORLD_TILES_X)
    for (bx, by, br) in _BASE_OBSTACLES
]


def resolve_obstacles(x, y, radius):
    """Empêche x,y de pénétrer un obstacle ; renvoie la position corrigée."""
    for ox, oy, orad in OBSTACLES:
        dx, dy = x - ox, y - oy
        dist = math.hypot(dx, dy)
        min_dist = orad + radius
        if dist < min_dist and dist > 0.001:
            push = (min_dist - dist)
            x += (dx / dist) * push
            y += (dy / dist) * push
    return x, y

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
    (bx + tx * TILE_W, by + ty * TILE_H)
    for ty in range(WORLD_TILES_Y)
    for tx in range(WORLD_TILES_X)
    for (bx, by) in [(70, 70), (TILE_W - 70, 70), (70, TILE_H - 70), (TILE_W - 70, TILE_H - 70)]
]

players = {}       # sid -> player dict
projectiles = {}   # id -> projectile dict
monsters = {}       # id -> monster dict
weapons = {}         # id -> weapon dict (au sol)


def random_spawn():
    return random.choice(SPAWN_POINTS)


def spawn_weapon():
    wid = str(uuid.uuid4())
    wtype = random.choice([k for k in WEAPON_TYPES if k != "fists"])
    for _ in range(20):
        x = random.uniform(30, ARENA_W - 30)
        y = random.uniform(30, ARENA_H - 30)
        if not in_obstacle(x, y, 20):
            break
    weapons[wid] = {"id": wid, "type": wtype, "x": x, "y": y}


def public_weapon(w):
    return {"id": w["id"], "type": w["type"], "color": WEAPON_TYPES[w["type"]]["color"]}


def equip_weapon(p, wtype):
    stats = WEAPON_TYPES[wtype]
    p["weapon"] = wtype
    p["damage"] = stats["damage"]
    p["fireRate"] = stats["fireRate"]
    p["projSpeed"] = stats["projSpeed"]
    p["range"] = stats["range"]


def kill_player(p, now):
    p["alive"] = False
    p["justDied"] = now
    p["deaths"] += 1
    p["respawnAt"] = now + RESPAWN_DELAY
    if p["weapon"] != "fists":
        wid = str(uuid.uuid4())
        weapons[wid] = {"id": wid, "type": p["weapon"], "x": p["x"], "y": p["y"]}
        equip_weapon(p, "fists")


def in_obstacle(x, y, margin=0):
    for ox, oy, orad in OBSTACLES:
        if math.hypot(x - ox, y - oy) < orad + margin:
            return True
    return False


def spawn_slime():
    mid = str(uuid.uuid4())
    for _ in range(20):
        x = random.uniform(SLIME_RADIUS + 20, ARENA_W - SLIME_RADIUS - 20)
        y = random.uniform(SLIME_RADIUS + 20, ARENA_H - SLIME_RADIUS - 20)
        if not in_obstacle(x, y, SLIME_RADIUS):
            break
    angle = random.uniform(0, math.pi * 2)
    monsters[mid] = {
        "id": mid,
        "type": "slime",
        "x": x,
        "y": y,
        "health": SLIME_HEALTH,
        "maxHealth": SLIME_HEALTH,
        "spawnAt": time.time(),
        "moveAngle": angle,
        "nextTurnAt": time.time() + random.uniform(1.5, 3.5),
        "lastBite": {},  # sid -> timestamp du dernier contact
    }


def public_monster(m):
    return {
        "id": m["id"],
        "type": m["type"],
        "x": m["x"],
        "y": m["y"],
        "health": m["health"],
        "maxHealth": m["maxHealth"],
    }


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
        "weapon": p["weapon"],
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
    fists = WEAPON_TYPES["fists"]
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
        "weapon": "fists",
        "damage": fists["damage"],
        "fireRate": fists["fireRate"],
        "projSpeed": fists["projSpeed"],
        "range": fists["range"],
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
        "angle": p["angle"],
        "damage": p["damage"],
        "traveled": 0.0,
        "range": p["range"],
        "color": WEAPON_TYPES[p["weapon"]]["color"],
        "weapon": p["weapon"],
    }


def game_loop():
    last = time.time()
    while True:
        socketio.sleep(TICK_RATE)
        now = time.time()
        dt = now - last
        last = now

        # Cycle de vie des slimes : expiration puis apparition aléatoire
        for mid, m in list(monsters.items()):
            if now - m["spawnAt"] > SLIME_LIFESPAN:
                del monsters[mid]
        if len(monsters) < MAX_MONSTERS and random.random() < MONSTER_SPAWN_CHANCE_PER_TICK:
            spawn_slime()

        # Déplacement erratique des slimes + collision de contact avec les joueurs
        for m in monsters.values():
            if now >= m["nextTurnAt"]:
                m["moveAngle"] = random.uniform(0, math.pi * 2)
                m["nextTurnAt"] = now + random.uniform(1.5, 3.5)

            nx = m["x"] + math.cos(m["moveAngle"]) * SLIME_SPEED * dt
            ny = m["y"] + math.sin(m["moveAngle"]) * SLIME_SPEED * dt
            if nx < SLIME_RADIUS or nx > ARENA_W - SLIME_RADIUS:
                m["moveAngle"] = math.pi - m["moveAngle"]
            else:
                m["x"] = nx
            if ny < SLIME_RADIUS or ny > ARENA_H - SLIME_RADIUS:
                m["moveAngle"] = -m["moveAngle"]
            else:
                m["y"] = ny
            m["x"], m["y"] = resolve_obstacles(m["x"], m["y"], SLIME_RADIUS)

            for sid, p in players.items():
                if not p["alive"]:
                    continue
                dist = math.hypot(p["x"] - m["x"], p["y"] - m["y"])
                if dist <= SLIME_RADIUS + PLAYER_RADIUS:
                    last = m["lastBite"].get(sid, 0)
                    if now - last >= SLIME_CONTACT_COOLDOWN:
                        m["lastBite"][sid] = now
                        p["health"] -= SLIME_CONTACT_DAMAGE
                        p["justHit"] = now
                        if p["health"] <= 0 and p["alive"]:
                            kill_player(p, now)

        # Apparition aléatoire des armes au sol
        if len(weapons) < MAX_WEAPONS_ON_GROUND and random.random() < WEAPON_SPAWN_CHANCE_PER_TICK:
            spawn_weapon()

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
            p["x"], p["y"] = resolve_obstacles(p["x"], p["y"], PLAYER_RADIUS)

            # Ramassage d'une arme au sol
            for wid, w in list(weapons.items()):
                dist = math.hypot(p["x"] - w["x"], p["y"] - w["y"])
                if dist <= WEAPON_PICKUP_RADIUS:
                    equip_weapon(p, w["type"])
                    del weapons[wid]
                    break

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

            hit_mid = None
            if not hit_sid:
                for mid, m in monsters.items():
                    dist = math.hypot(m["x"] - proj["x"], m["y"] - proj["y"])
                    if dist <= SLIME_RADIUS + PROJECTILE_RADIUS:
                        hit_mid = mid
                        break

            if hit_mid:
                m = monsters[hit_mid]
                m["health"] -= proj["damage"]
                if m["health"] <= 0:
                    del monsters[hit_mid]
                    shooter = players.get(proj["owner"])
                    if shooter:
                        shooter["kills"] += SLIME_KILL_REWARD
                del projectiles[pid]
                continue

            if hit_sid:
                target = players[hit_sid]
                target["health"] -= proj["damage"]
                target["justHit"] = now
                if target["health"] <= 0 and target["alive"]:
                    kill_player(target, now)
                    shooter = players.get(proj["owner"])
                    if shooter:
                        shooter["kills"] += 1
                del projectiles[pid]

        # Diffusion de l'état à tous les clients
        socketio.emit("state", {
            "players": [public_player(p) for p in players.values()],
            "projectiles": [
                {"id": pr["id"], "x": pr["x"], "y": pr["y"], "color": pr["color"], "angle": pr["angle"], "weapon": pr["weapon"]}
                for pr in projectiles.values()
            ],
            "monsters": [public_monster(m) for m in monsters.values()],
            "weapons": [public_weapon(w) for w in weapons.values()],
        })


socketio.start_background_task(game_loop)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
