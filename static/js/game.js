(() => {
  const ARENA_W = 1000;
  const ARENA_H = 700;

  const lobby = document.getElementById("lobby");
  const gameScreen = document.getElementById("gameScreen");
  const nameInput = document.getElementById("nameInput");
  const playBtn = document.getElementById("playBtn");
  const connStatus = document.getElementById("connStatus");
  const healthFill = document.getElementById("healthFill");
  const scoreboardEl = document.getElementById("scoreboard");
  const deathBanner = document.getElementById("deathBanner");

  let selectedType = null;
  let myId = null;
  let latestState = { players: [], projectiles: [], monsters: [] };

  // ---------------- Lobby : choix du personnage ----------------
  document.querySelectorAll(".char-card").forEach((card) => {
    card.addEventListener("click", () => {
      document.querySelectorAll(".char-card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      selectedType = card.dataset.type;
      updatePlayEnabled();
    });
  });

  nameInput.addEventListener("input", updatePlayEnabled);

  function updatePlayEnabled() {
    playBtn.disabled = !(selectedType && nameInput.value.trim().length > 0 && socket.connected);
  }

  // ---------------- Connexion Socket.IO ----------------
  const socket = io();

  socket.on("connect", () => {
    connStatus.textContent = "Connecté — choisis ton combattant";
    updatePlayEnabled();
  });

  socket.on("disconnect", () => {
    connStatus.textContent = "Déconnecté du serveur…";
  });

  socket.on("joined", (data) => {
    myId = data.id;
    lobby.classList.add("hidden");
    gameScreen.classList.remove("hidden");
    startPhaser();
  });

  socket.on("state", (data) => {
    latestState = data;
  });

  playBtn.addEventListener("click", () => {
    socket.emit("join", { name: nameInput.value.trim(), type: selectedType });
  });

  // ---------------- Contrôles clavier (mouvement) ----------------
  const keys = { up: false, down: false, left: false, right: false };
  let shooting = false;
  let aimAngle = 0;

  window.addEventListener("keydown", (e) => setKey(e.code, true));
  window.addEventListener("keyup", (e) => setKey(e.code, false));

  function setKey(code, val) {
    if (code === "KeyW" || code === "ArrowUp") keys.up = val;
    if (code === "KeyS" || code === "ArrowDown") keys.down = val;
    if (code === "KeyA" || code === "ArrowLeft") keys.left = val;
    if (code === "KeyD" || code === "ArrowRight") keys.right = val;
  }

  // Envoi des entrées au serveur ~20x / seconde
  setInterval(() => {
    if (!socket.connected || !myId) return;
    let dx = 0, dy = 0;
    if (keys.up) dy -= 1;
    if (keys.down) dy += 1;
    if (keys.left) dx -= 1;
    if (keys.right) dx += 1;
    socket.emit("input", { dx, dy, angle: aimAngle, shooting });
  }, 50);

  // ---------------- Phaser : rendu du jeu ----------------
  const SPRITE_KEYS = ["forestier", "paysan"];
  const DIRS = ["down", "left", "right", "up"]; // ordre des lignes dans les feuilles composées
  const WALK_FRAMES = 6;
  const ATTACK_FRAMES = 4;

  let phaserStarted = false;
  let scene = null;
  const entities = {}; // id -> { container, sprite, hpFill, nameText, currentAnim, dying }
  const lastHitStamp = {};
  const lastDeathStamp = {};
  const lastShotStamp = {};

  function startPhaser() {
    if (phaserStarted) return;
    phaserStarted = true;

    const config = {
      type: Phaser.AUTO,
      parent: "arena-container",
      width: ARENA_W,
      height: ARENA_H,
      backgroundColor: "#1a1d26",
      pixelArt: true,
      scale: {
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH,
        width: ARENA_W,
        height: ARENA_H,
      },
      scene: { preload, create, update },
    };
    new Phaser.Game(config);
  }

  function preload() {
    this.load.image("bg_arena", "static/assets/bg/arena.jpg");
    SPRITE_KEYS.forEach((key) => {
      this.load.spritesheet(`${key}_idle`, `static/assets/${key}/idle.png`, { frameWidth: 64, frameHeight: 64 });
      this.load.spritesheet(`${key}_walk`, `static/assets/${key}/walk.png`, { frameWidth: 64, frameHeight: 64 });
      this.load.spritesheet(`${key}_attack`, `static/assets/${key}/attack.png`, { frameWidth: 64, frameHeight: 64 });
    });
  }

  function create() {
    scene = this;

    this.add.image(ARENA_W / 2, ARENA_H / 2, "bg_arena").setDisplaySize(ARENA_W, ARENA_H);

    SPRITE_KEYS.forEach((key) => {
      DIRS.forEach((dir, i) => {
        this.anims.create({
          key: `${key}_idle_${dir}`,
          frames: [{ key: `${key}_idle`, frame: i }],
          frameRate: 1,
          repeat: -1,
        });
        this.anims.create({
          key: `${key}_walk_${dir}`,
          frames: this.anims.generateFrameNumbers(`${key}_walk`, {
            start: i * WALK_FRAMES, end: i * WALK_FRAMES + WALK_FRAMES - 1,
          }),
          frameRate: 11,
          repeat: -1,
        });
        this.anims.create({
          key: `${key}_attack_${dir}`,
          frames: this.anims.generateFrameNumbers(`${key}_attack`, {
            start: i * ATTACK_FRAMES, end: i * ATTACK_FRAMES + ATTACK_FRAMES - 1,
          }),
          frameRate: 14,
          repeat: 0,
        });
      });
    });

    this.projGraphics = this.add.graphics().setDepth(5);
    this.monsterGraphics = this.add.graphics().setDepth(3);

    this.input.on("pointermove", (pointer) => {
      const me = entities[myId];
      if (me) {
        aimAngle = Phaser.Math.Angle.Between(me.container.x, me.container.y, pointer.worldX, pointer.worldY);
      }
    });
    this.input.on("pointerdown", () => { shooting = true; });
    this.input.on("pointerup", () => { shooting = false; });
  }

  function angleToDir(angle) {
    const deg = Phaser.Math.RadToDeg(angle);
    if (deg >= -45 && deg < 45) return "right";
    if (deg >= 45 && deg < 135) return "down";
    if (deg >= -135 && deg < -45) return "up";
    return "left";
  }

  function ensureEntity(p) {
    if (entities[p.id]) return entities[p.id];

    const container = scene.add.container(p.x, p.y).setDepth(2);
    const shadow = scene.add.ellipse(0, 20, 24, 9, 0x000000, 0.45);
    const sprite = scene.add.sprite(0, 0, `${p.sprite}_idle`, 0).setOrigin(0.5, 0.8).setScale(1.0);
    if (p.tint) sprite.setTint(parseInt(p.tint, 16));

    const nameText = scene.add.text(0, -54, p.name, {
      fontFamily: "Rubik, sans-serif",
      fontSize: "12px",
      color: p.id === myId ? "#ffffff" : "#c7cbd6",
    }).setOrigin(0.5);

    const hpBg = scene.add.rectangle(0, -42, 40, 5, 0x2a2e3b).setOrigin(0.5);
    const hpFill = scene.add.rectangle(-20, -42, 40, 5, 0x5dbe7c).setOrigin(0, 0.5);

    container.add([shadow, sprite, hpBg, hpFill, nameText]);

    const entity = { container, sprite, hpFill, nameText, currentAnim: "idle_down", dying: false };
    entities[p.id] = entity;
    return entity;
  }

  function playAnim(entity, spriteKey, animName, dir, restart) {
    const full = `${animName}_${dir}`;
    if (entity.currentAnim === full && !restart) return;
    entity.currentAnim = full;
    entity.sprite.play(`${spriteKey}_${full}`);
  }

  function syncEntities() {
    const seenIds = new Set();

    latestState.players.forEach((p) => {
      seenIds.add(p.id);
      const entity = ensureEntity(p);
      entity.container.setPosition(p.x, p.y);
      const dir = angleToDir(p.angle);

      const ratio = Math.max(0, p.health / p.maxHealth);
      entity.hpFill.width = 40 * ratio;
      entity.hpFill.fillColor = ratio > 0.4 ? 0x5dbe7c : 0xe8624f;

      if (p.justHit && p.justHit !== lastHitStamp[p.id]) {
        lastHitStamp[p.id] = p.justHit;
        if (p.alive) {
          entity.sprite.setTintFill(0xffffff);
          scene.time.delayedCall(90, () => {
            if (p.tint) entity.sprite.setTint(parseInt(p.tint, 16));
            else entity.sprite.clearTint();
          });
        }
      }

      if (!p.alive) {
        entity.hpFill.visible = false;
        entity.nameText.visible = false;
        if (p.justDied && p.justDied !== lastDeathStamp[p.id]) {
          lastDeathStamp[p.id] = p.justDied;
          entity.dying = true;
          scene.tweens.add({
            targets: entity.container,
            alpha: 0.3,
            angle: 90,
            duration: 350,
            ease: "Quad.easeOut",
          });
        }
      } else {
        if (entity.dying) {
          entity.dying = false;
          entity.container.setAlpha(1);
          entity.container.angle = 0;
        }
        entity.hpFill.visible = true;
        entity.nameText.visible = true;

        const isAttackAnim = entity.currentAnim === `attack_${dir}`;
        const attackStillPlaying = isAttackAnim && entity.sprite.anims.isPlaying;
        const newShot = p.shooting && p.lastShot !== lastShotStamp[p.id];

        if (newShot) {
          lastShotStamp[p.id] = p.lastShot;
          playAnim(entity, p.sprite, "attack", dir, true);
        } else if (attackStillPlaying) {
          // laisser l'animation d'attaque se terminer
        } else if (p.moving) {
          playAnim(entity, p.sprite, "walk", dir);
        } else {
          playAnim(entity, p.sprite, "idle", dir);
        }
      }
    });

    Object.keys(entities).forEach((id) => {
      if (!seenIds.has(id)) {
        entities[id].container.destroy();
        delete entities[id];
        delete lastHitStamp[id];
        delete lastDeathStamp[id];
        delete lastShotStamp[id];
      }
    });
  }

  function drawProjectiles() {
    if (!scene) return;
    scene.projGraphics.clear();
    latestState.projectiles.forEach((pr) => {
      const color = parseInt((pr.color || "#ffffff").replace("#", "0x"));
      scene.projGraphics.fillStyle(color, 1);
      scene.projGraphics.fillCircle(pr.x, pr.y, 5);
    });
  }

  function drawMonsters() {
    if (!scene) return;
    scene.monsterGraphics.clear();
    const t = scene.time.now / 1000;

    latestState.monsters.forEach((m) => {
      const jiggle = 1 + Math.sin(t * 6 + m.x) * 0.08;
      const w = 22 * jiggle;
      const h = 16 / jiggle;

      // corps gélatineux
      scene.monsterGraphics.fillStyle(0x5dbe7c, 0.9);
      scene.monsterGraphics.fillEllipse(m.x, m.y, w, h);
      scene.monsterGraphics.lineStyle(2, 0x2f7a45, 1);
      scene.monsterGraphics.strokeEllipse(m.x, m.y, w, h);

      // reflet
      scene.monsterGraphics.fillStyle(0xaef0c0, 0.6);
      scene.monsterGraphics.fillEllipse(m.x - w * 0.2, m.y - h * 0.25, w * 0.35, h * 0.3);

      // yeux
      scene.monsterGraphics.fillStyle(0x1a1d26, 1);
      scene.monsterGraphics.fillCircle(m.x - 5, m.y - 2, 1.6);
      scene.monsterGraphics.fillCircle(m.x + 5, m.y - 2, 1.6);

      // barre de vie
      const ratio = Math.max(0, m.health / m.maxHealth);
      scene.monsterGraphics.fillStyle(0x2a2e3b, 1);
      scene.monsterGraphics.fillRect(m.x - 16, m.y - h - 10, 32, 4);
      scene.monsterGraphics.fillStyle(0x5dbe7c, 1);
      scene.monsterGraphics.fillRect(m.x - 16, m.y - h - 10, 32 * ratio, 4);
    });
  }

  function updateHud() {
    const me = latestState.players.find((p) => p.id === myId);
    if (me) {
      healthFill.style.width = Math.max(0, (me.health / me.maxHealth) * 100) + "%";
      deathBanner.classList.toggle("hidden", me.alive);
    }
    const sorted = [...latestState.players].sort((a, b) => b.kills - a.kills).slice(0, 6);
    scoreboardEl.innerHTML = sorted
      .map((p) => `<div class="row ${p.id === myId ? "me" : ""}"><span>${escapeHtml(p.name)}</span><span>${p.kills}</span></div>`)
      .join("");
  }

  function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function update() {
    if (!scene) return;
    syncEntities();
    drawMonsters();
    drawProjectiles();
    updateHud();
  }
})();
