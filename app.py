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
# --- Taille du monde ---
ARENA_W = 2000
ARENA_H = 1400
TICK_RATE = 1 / 30.0  # 30 mises à jour / seconde
RESPAWN_DELAY = 3.0
PLAYER_RADIUS = 18
PROJECTILE_RADIUS = 5

# --- Armes au sol ---
MAX_WEAPONS_ON_GROUND = 16
WEAPON_SPAWN_CHANCE_PER_TICK = 0.3
WEAPON_PICKUP_RADIUS = 26

WEAPON_TYPES = {
    "fists": {"label": "Poings", "color": "#8b90a0", "damage": 4, "fireRate": 0.45, "projSpeed": 420, "range": 180},
    "sword": {"label": "Épée", "color": "#4FA8E8", "damage": 8, "fireRate": 0.30, "projSpeed": 560, "range": 300},
    "axe": {"label": "Hache", "color": "#5DBE7C", "damage": 6, "fireRate": 0.20, "projSpeed": 700, "range": 480},
    "mace": {"label": "Masse", "color": "#E8624F", "damage": 14, "fireRate": 0.65, "projSpeed": 380, "range": 220},
}

# --- Progression de l'arme équipée (façon MO.CO) ---
WEAPON_XP_PER_MONSTER_KILL = 8
WEAPON_XP_PER_PLAYER_KILL = 30
WEAPON_XP_BASE = 30           # XP nécessaire pour passer du niveau 1 au niveau 2
WEAPON_XP_GROWTH = 1.35       # multiplicateur de coût par niveau
LEVELUP_CHOICE_TIMEOUT = 8.0  # secondes avant sélection automatique

BONUS_POOL = [
    {"id": "damage_up", "label": "Dégâts +15%", "desc": "Chaque coup frappe plus fort.", "dmgMult": 1.15},
    {"id": "firerate_up", "label": "Cadence +15%", "desc": "Tire plus vite.", "frMult": 1.0 / 1.15},
    {"id": "range_up", "label": "Portée +20%", "desc": "Les tirs vont plus loin.", "rangeMult": 1.20},
    {"id": "speed_up", "label": "Vitesse +10%", "desc": "Déplacement plus rapide.", "speedMult": 1.10},
    {"id": "health_up", "label": "PV max +15", "desc": "Encaisse plus de coups.", "hpBonus": 15},
]
MAX_MONSTERS = 10
MONSTER_SPAWN_CHANCE_PER_TICK = 0.06
SLIME_RADIUS = 16
SLIME_HEALTH = 30
SLIME_LIFESPAN = 180.0  # secondes avant disparition si pas tué (et jamais s'il vient d'être touché)
SLIME_KILL_REWARD = 1   # ajouté au compteur de kills du tueur
SLIME_SPEED = 55
SLIME_CONTACT_DAMAGE = 3
SLIME_CONTACT_COOLDOWN = 1.2  # secondes entre deux morsures sur le même joueur

# --- Décor / obstacles : arbres, rochers, souches dispersés sur la carte.
# Générés une fois avec une graine fixe pour un placement stable entre redémarrages.
# Chaque obstacle : (x, y, rayon_collision, type) — le type sert au rendu client.
_OBSTACLE_SPECS = [
    ("tree", 46, 46),   # (kind, radius, count)
    ("rock", 22, 30),
    ("stump", 24, 26),
]

def _generate_obstacles():
    rng = random.Random(1337)
    placed = []
    margin = 80
    for kind, radius, count in _OBSTACLE_SPECS:
        attempts = 0
        added = 0
        while added < count and attempts < count * 40:
            attempts += 1
            x = rng.uniform(margin, ARENA_W - margin)
            y = rng.uniform(margin, ARENA_H - margin)
            ok = True
            for ox, oy, orad, okind in placed:
                min_gap = radius + orad + 30
                if math.hypot(x - ox, y - oy) < min_gap:
                    ok = False
                    break
            if ok:
                placed.append((x, y, radius, kind))
                added += 1
    return placed


OBSTACLES = _generate_obstacles()

# Index spatial (grille de cellules) pour accélérer les tests de collision :
# évite de comparer chaque joueur à TOUS les obstacles à chaque tick.
_OBSTACLE_CELL = 200
_obstacle_grid = {}
for _ox, _oy, _orad, _okind in OBSTACLES:
    _key = (int(_ox // _OBSTACLE_CELL), int(_oy // _OBSTACLE_CELL))
    _obstacle_grid.setdefault(_key, []).append((_ox, _oy, _orad))


def resolve_obstacles(x, y, radius):
    """Empêche x,y de pénétrer un obstacle ; renvoie la position corrigée."""
    cx, cy = int(x // _OBSTACLE_CELL), int(y // _OBSTACLE_CELL)
    for gx in (cx - 1, cx, cx + 1):
        for gy in (cy - 1, cy, cy + 1):
            for ox, oy, orad in _obstacle_grid.get((gx, gy), ()):
                dx, dy = x - ox, y - oy
                min_dist = orad + radius
                dist_sq = dx * dx + dy * dy
                if dist_sq < min_dist * min_dist and dist_sq > 0.0001:
                    dist = math.sqrt(dist_sq)
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
    (x, y)
    for x in range(100, ARENA_W - 100 + 1, (ARENA_W - 200) // 4)
    for y in range(100, ARENA_H - 100 + 1, (ARENA_H - 200) // 3)
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


def apply_weapon_stats(p):
    """Recalcule les stats effectives à partir de l'arme équipée + bonus accumulés."""
    base = WEAPON_TYPES[p["weapon"]]
    b = p["weaponBonuses"]
    p["damage"] = base["damage"] * b["dmgMult"]
    p["fireRate"] = base["fireRate"] * b["frMult"]
    p["projSpeed"] = base["projSpeed"]
    p["range"] = base["range"] * b["rangeMult"]
    p["speed"] = p["baseSpeed"] * b["speedMult"]
    newMax = p["baseMaxHealth"] + b["hpBonus"]
    if newMax != p["maxHealth"]:
        p["health"] = p["health"] + (newMax - p["maxHealth"])
        p["maxHealth"] = newMax


def equip_weapon(p, wtype):
    p["weapon"] = wtype
    p["weaponLevel"] = 1
    p["weaponXP"] = 0
    p["weaponXPNext"] = WEAPON_XP_BASE
    p["weaponBonuses"] = {"dmgMult": 1.0, "frMult": 1.0, "rangeMult": 1.0, "speedMult": 1.0, "hpBonus": 0}
    p["pendingChoice"] = None
    p["pendingChoiceAt"] = None
    apply_weapon_stats(p)


def award_weapon_xp(p, amount, now):
    if p["pendingChoice"] is not None:
        return  # en attente d'un choix : pas de nouvelle XP tant que non résolu
    p["weaponXP"] += amount
    if p["weaponXP"] >= p["weaponXPNext"]:
        options = random.sample(BONUS_POOL, 2)
        p["pendingChoice"] = options
        p["pendingChoiceAt"] = now
        socketio.emit("levelup", {
            "level": p["weaponLevel"] + 1,
            "options": [{"id": o["id"], "label": o["label"], "desc": o["desc"]} for o in options],
        }, to=p["id"])


def resolve_levelup(p, choice_index):
    options = p["pendingChoice"]
    if not options:
        return
    choice_index = max(0, min(len(options) - 1, choice_index))
    bonus = options[choice_index]
    b = p["weaponBonuses"]
    if "dmgMult" in bonus:
        b["dmgMult"] *= bonus["dmgMult"]
    if "frMult" in bonus:
        b["frMult"] *= bonus["frMult"]
    if "rangeMult" in bonus:
        b["rangeMult"] *= bonus["rangeMult"]
    if "speedMult" in bonus:
        b["speedMult"] *= bonus["speedMult"]
    if "hpBonus" in bonus:
        b["hpBonus"] += bonus["hpBonus"]

    p["weaponLevel"] += 1
    p["weaponXP"] = 0
    p["weaponXPNext"] = round(WEAPON_XP_BASE * (WEAPON_XP_GROWTH ** (p["weaponLevel"] - 1)))
    p["pendingChoice"] = None
    p["pendingChoiceAt"] = None
    apply_weapon_stats(p)


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
    for ox, oy, orad, okind in OBSTACLES:
        if math.hypot(x - ox, y - oy) < orad + margin:
            return True
    return False


def _generate_flower_patches():
    """Décor purement visuel (pas de collision), évite juste de recouvrir un obstacle."""
    rng = random.Random(4242)
    placed = []
    margin = 60
    count = 24
    attempts = 0
    while len(placed) < count and attempts < count * 40:
        attempts += 1
        x = rng.uniform(margin, ARENA_W - margin)
        y = rng.uniform(margin, ARENA_H - margin)
        if in_obstacle(x, y, 40):
            continue
        placed.append((x, y))
    return placed


DECOR_FLOWERS = _generate_flower_patches()


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
        "type": "orc",
        "x": x,
        "y": y,
        "health": SLIME_HEALTH,
        "maxHealth": SLIME_HEALTH,
        "spawnAt": time.time(),
        "moveAngle": angle,
        "nextTurnAt": time.time() + random.uniform(1.5, 3.5),
        "lastBite": {},  # sid -> timestamp du dernier contact
        "justAttacked": 0,
        "justDied": 0,
        "alive": True,
    }


def public_monster(m):
    return {
        "id": m["id"],
        "type": m["type"],
        "x": m["x"],
        "y": m["y"],
        "health": m["health"],
        "maxHealth": m["maxHealth"],
        "moveAngle": m["moveAngle"],
        "justAttacked": m["justAttacked"],
        "justDied": m["justDied"],
        "alive": m["alive"],
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
        "facingAngle": p["facingAngle"],
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
        "weaponLevel": p["weaponLevel"],
        "weaponXP": p["weaponXP"],
        "weaponXPNext": p["weaponXPNext"],
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
        "facingAngle": math.pi / 2,  # direction du sprite (marche), distincte de la visée
        "dx": 0,
        "dy": 0,
        "baseSpeed": char["speed"],
        "speed": char["speed"],
        "baseMaxHealth": char["maxHealth"],
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
    equip_weapon(players[sid], "fists")
    socketio.emit("joined", {
        "id": sid,
        "arena": {"w": ARENA_W, "h": ARENA_H},
        "obstacles": [{"x": ox, "y": oy, "r": orad, "kind": okind} for ox, oy, orad, okind in OBSTACLES],
    }, to=sid)


@socketio.on("choose_bonus")
def on_choose_bonus(data):
    from flask import request
    sid = request.sid
    p = players.get(sid)
    if not p or p["pendingChoice"] is None:
        return
    resolve_levelup(p, int(data.get("index", 0)))


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
    if norm > 0.01:
        p["facingAngle"] = math.atan2(dy, dx)
    if "angle" in data:
        p["angle"] = float(data["angle"])
    if "shooting" in data:
        p["shooting"] = bool(data["shooting"])


MELEE_HALF_CONE = math.radians(50)  # demi-angle du cône d'attaque au corps-à-corps


def angle_diff(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return d


def melee_attack(p, now):
    """Frappe immédiate au corps-à-corps : touche tout ce qui est dans la portée
    de la lame et dans le cône de balayage, sans aucun projectile."""
    reach = p["range"]

    for sid, target in players.items():
        if sid == p["id"] or not target["alive"]:
            continue
        dx, dy = target["x"] - p["x"], target["y"] - p["y"]
        dist = math.hypot(dx, dy)
        if dist > reach + PLAYER_RADIUS:
            continue
        if abs(angle_diff(math.atan2(dy, dx), p["angle"])) > MELEE_HALF_CONE:
            continue
        target["health"] -= p["damage"]
        target["justHit"] = now
        if target["health"] <= 0 and target["alive"]:
            kill_player(target, now)
            p["kills"] += 1
            award_weapon_xp(p, WEAPON_XP_PER_PLAYER_KILL, now)

    for mid, m in list(monsters.items()):
        if not m["alive"]:
            continue
        dx, dy = m["x"] - p["x"], m["y"] - p["y"]
        dist = math.hypot(dx, dy)
        if dist > reach + SLIME_RADIUS:
            continue
        if abs(angle_diff(math.atan2(dy, dx), p["angle"])) > MELEE_HALF_CONE:
            continue
        m["health"] -= p["damage"]
        m["spawnAt"] = now  # un monstre engagé au combat ne doit jamais expirer
        if m["health"] <= 0 and m["alive"]:
            m["alive"] = False
            m["justDied"] = now
            p["kills"] += SLIME_KILL_REWARD
            award_weapon_xp(p, WEAPON_XP_PER_MONSTER_KILL, now)
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

        # Cycle de vie des slimes : expiration, nettoyage après mort, apparition aléatoire
        for mid, m in list(monsters.items()):
            if not m["alive"] and now - m["justDied"] > 0.9:
                del monsters[mid]
            elif m["alive"] and now - m["spawnAt"] > SLIME_LIFESPAN:
                del monsters[mid]
        if len(monsters) < MAX_MONSTERS and random.random() < MONSTER_SPAWN_CHANCE_PER_TICK:
            spawn_slime()

        # Déplacement erratique des slimes + collision de contact avec les joueurs
        for m in monsters.values():
            if not m["alive"]:
                continue
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
                        m["justAttacked"] = now
                        m["moveAngle"] = math.atan2(p["y"] - m["y"], p["x"] - m["x"])
                        p["health"] -= SLIME_CONTACT_DAMAGE
                        p["justHit"] = now
                        if p["health"] <= 0 and p["alive"]:
                            kill_player(p, now)

        # Apparition aléatoire des armes au sol
        if len(weapons) < MAX_WEAPONS_ON_GROUND and random.random() < WEAPON_SPAWN_CHANCE_PER_TICK:
            spawn_weapon()

        # Mouvement + tir des joueurs
        for sid, p in list(players.items()):
            if p["pendingChoice"] is not None and now - p["pendingChoiceAt"] > LEVELUP_CHOICE_TIMEOUT:
                resolve_levelup(p, 0)
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
                melee_attack(p, now)

        # Mouvement des projectiles + collisions
        for pid, proj in list(projectiles.items()):
            proj["x"] += proj["vx"] * dt
            proj["y"] += proj["vy"] * dt
            proj["traveled"] += math.hypot(proj["vx"] * dt, proj["vy"] * dt)

            if (proj["traveled"] > proj["range"] or proj["x"] < 0 or
                    proj["x"] > ARENA_W or proj["y"] < 0 or proj["y"] > ARENA_H):
                del projectiles[pid]
                continue

            # Un obstacle du décor (arbre, rocher, souche) bloque le projectile
            cx, cy = int(proj["x"] // _OBSTACLE_CELL), int(proj["y"] // _OBSTACLE_CELL)
            blocked = False
            for gx in (cx - 1, cx, cx + 1):
                for gy in (cy - 1, cy, cy + 1):
                    for ox, oy, orad in _obstacle_grid.get((gx, gy), ()):
                        if (proj["x"] - ox) ** 2 + (proj["y"] - oy) ** 2 < (orad + PROJECTILE_RADIUS) ** 2:
                            blocked = True
                            break
                    if blocked:
                        break
                if blocked:
                    break
            if blocked:
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
                    if not m["alive"]:
                        continue
                    dist = math.hypot(m["x"] - proj["x"], m["y"] - proj["y"])
                    if dist <= SLIME_RADIUS + PROJECTILE_RADIUS:
                        hit_mid = mid
                        break

            if hit_mid:
                m = monsters[hit_mid]
                m["health"] -= proj["damage"]
                if m["health"] <= 0 and m["alive"]:
                    m["alive"] = False
                    m["justDied"] = now
                    shooter = players.get(proj["owner"])
                    if shooter:
                        shooter["kills"] += SLIME_KILL_REWARD
                        award_weapon_xp(shooter, WEAPON_XP_PER_MONSTER_KILL, now)
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
                        award_weapon_xp(shooter, WEAPON_XP_PER_PLAYER_KILL, now)
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
