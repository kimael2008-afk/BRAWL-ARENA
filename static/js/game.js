(() => {
  const VIEWPORT_W = 1000;
  const VIEWPORT_H = 700;
  let worldW = VIEWPORT_W;
  let worldH = VIEWPORT_H;
  let worldObstacles = [];

  const lobby = document.getElementById("lobby");
  const gameScreen = document.getElementById("gameScreen");
  const nameInput = document.getElementById("nameInput");
  const playBtn = document.getElementById("playBtn");
  const connStatus = document.getElementById("connStatus");
  const healthFill = document.getElementById("healthFill");
  const weaponLabelEl = document.getElementById("weaponLabel");
  const weaponXpFillEl = document.getElementById("weaponXpFill");
  const levelupOverlay = document.getElementById("levelupOverlay");
  const levelupTitle = document.getElementById("levelupTitle");
  const levelupOptions = document.getElementById("levelupOptions");
  const scoreboardEl = document.getElementById("scoreboard");
  const deathBanner = document.getElementById("deathBanner");

  let selectedType = null;
  let myId = null;
  let latestState = { players: [], projectiles: [], monsters: [], weapons: [] };

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
    if (data.arena) {
      worldW = data.arena.w;
      worldH = data.arena.h;
    }
    if (data.obstacles) worldObstacles = data.obstacles;
    lobby.classList.add("hidden");
    gameScreen.classList.remove("hidden");
    startPhaser();
  });

  socket.on("state", (data) => {
    latestState = data;
  });

  socket.on("levelup", (data) => {
    showLevelupChoice(data);
  });

  function showLevelupChoice(data) {
    if (!levelupOverlay) return;
    levelupTitle.textContent = `Niveau ${data.level} — choisis un bonus`;
    levelupOptions.innerHTML = "";
    data.options.forEach((opt, i) => {
      const btn = document.createElement("button");
      btn.className = "levelup-option";
      btn.innerHTML = `<span class="lvl-label">${opt.label}</span><span class="lvl-desc">${opt.desc}</span>`;
      btn.addEventListener("click", () => {
        socket.emit("choose_bonus", { index: i });
        levelupOverlay.classList.add("hidden");
      });
      levelupOptions.appendChild(btn);
    });
    levelupOverlay.classList.remove("hidden");
  }

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
  const ATTACK_VARIANTS = ["attack", "attack_thrust", "attack_slash2"];
  const WEAPON_ATTACK_ANIM = {
    fists: "attack_thrust",
    axe: "attack_thrust",
    sword: "attack",
    mace: "attack_slash2",
  };

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
      width: VIEWPORT_W,
      height: VIEWPORT_H,
      backgroundColor: "#1a1d26",
      pixelArt: true,
      scale: {
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH,
        width: VIEWPORT_W,
        height: VIEWPORT_H,
      },
      scene: { preload, create, update },
    };
    new Phaser.Game(config);
  }

  function preload() {
    this.load.image("grass_tile", "static/assets/bg/grass_tile.png");
    this.load.image("deco_tree", "static/assets/bg/tree_big.png");
    this.load.image("deco_rock", "static/assets/bg/rock.png");
    this.load.image("deco_stump", "static/assets/bg/stump.png");
    this.load.image("wpn_sword", "static/assets/weapons/sword.png");
    this.load.image("wpn_axe", "static/assets/weapons/axe.png");
    this.load.image("wpn_mace", "static/assets/weapons/mace.png");
    this.load.spritesheet("monster_idle", "static/assets/monster/idle.png", { frameWidth: 100, frameHeight: 100 });
    this.load.spritesheet("monster_walk", "static/assets/monster/walk.png", { frameWidth: 100, frameHeight: 100 });
    this.load.spritesheet("monster_attack", "static/assets/monster/attack.png", { frameWidth: 100, frameHeight: 100 });
    this.load.spritesheet("monster_hurt", "static/assets/monster/hurt.png", { frameWidth: 100, frameHeight: 100 });
    this.load.spritesheet("monster_death", "static/assets/monster/death.png", { frameWidth: 100, frameHeight: 100 });
    SPRITE_KEYS.forEach((key) => {
      this.load.spritesheet(`${key}_idle`, `static/assets/${key}/idle.png`, { frameWidth: 64, frameHeight: 64 });
      this.load.spritesheet(`${key}_walk`, `static/assets/${key}/walk.png`, { frameWidth: 64, frameHeight: 64 });
      ATTACK_VARIANTS.forEach((variant) => {
        this.load.spritesheet(`${key}_${variant}`, `static/assets/${key}/${variant}.png`, { frameWidth: 64, frameHeight: 64 });
      });
    });
  }

  function create() {
    scene = this;

    this.add.tileSprite(0, 0, worldW, worldH, "grass_tile").setOrigin(0, 0).setDepth(-10);
    this.cameras.main.setBounds(0, 0, worldW, worldH);

    worldObstacles.forEach((o) => {
      if (o.kind === "tree") {
        this.add.image(o.x, o.y + 14, "deco_tree").setOrigin(0.5, 0.92).setScale(0.5).setDepth(o.y);
      } else if (o.kind === "rock") {
        this.add.image(o.x, o.y, "deco_rock").setOrigin(0.5, 0.75).setScale(0.55).setDepth(-5);
      } else if (o.kind === "stump") {
        this.add.image(o.x, o.y, "deco_stump").setOrigin(0.5, 0.8).setScale(0.55).setDepth(-5);
      }
    });

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
        ATTACK_VARIANTS.forEach((variant) => {
          this.anims.create({
            key: `${key}_${variant}_${dir}`,
            frames: this.anims.generateFrameNumbers(`${key}_${variant}`, {
              start: i * ATTACK_FRAMES, end: i * ATTACK_FRAMES + ATTACK_FRAMES - 1,
            }),
            frameRate: 14,
            repeat: 0,
          });
        });
      });
    });

    this.anims.create({ key: "monster_idle", frames: this.anims.generateFrameNumbers("monster_idle", { start: 0, end: 5 }), frameRate: 6, repeat: -1 });
    this.anims.create({ key: "monster_walk", frames: this.anims.generateFrameNumbers("monster_walk", { start: 0, end: 7 }), frameRate: 9, repeat: -1 });
    this.anims.create({ key: "monster_attack", frames: this.anims.generateFrameNumbers("monster_attack", { start: 0, end: 5 }), frameRate: 12, repeat: 0 });
    this.anims.create({ key: "monster_hurt", frames: this.anims.generateFrameNumbers("monster_hurt", { start: 0, end: 3 }), frameRate: 10, repeat: 0 });
    this.anims.create({ key: "monster_death", frames: this.anims.generateFrameNumbers("monster_death", { start: 0, end: 3 }), frameRate: 7, repeat: 0 });

    this.projGraphics = this.add.graphics().setDepth(1000);
    this.monsterGraphics = this.add.graphics().setDepth(999);
    this.weaponGraphics = this.add.graphics().setDepth(998);

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
    const shadow = scene.add.ellipse(0, 2, 20, 7, 0x000000, 0.5);
    const sprite = scene.add.sprite(0, 8, `${p.sprite}_idle`, 0).setOrigin(0.484, 0.703).setScale(1.2);
    if (p.tint) sprite.setTint(parseInt(p.tint, 16));

    const weaponIcon = scene.add.image(14, 6, "wpn_sword").setOrigin(0.5, 0.8).setScale(2.4).setVisible(false).setDepth(3);

    const nameText = scene.add.text(0, -46, p.name, {
      fontFamily: "Rubik, sans-serif",
      fontSize: "12px",
      color: p.id === myId ? "#ffffff" : "#c7cbd6",
    }).setOrigin(0.5);

    const hpBg = scene.add.rectangle(0, -35, 40, 5, 0x2a2e3b).setOrigin(0.5);
    const hpFill = scene.add.rectangle(-20, -35, 40, 5, 0x5dbe7c).setOrigin(0, 0.5);

    container.add([shadow, sprite, weaponIcon, hpBg, hpFill, nameText]);

    const entity = { container, sprite, weaponIcon, hpFill, nameText, currentAnim: "idle_down", dying: false };
    entities[p.id] = entity;

    if (p.id === myId) {
      scene.cameras.main.startFollow(container, true, 0.12, 0.12);
    }

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
      entity.container.setDepth(p.y);
      const dir = angleToDir(p.facingAngle != null ? p.facingAngle : p.angle);
      const aimDir = angleToDir(p.angle);

      // Icône d'arme tenue en main : position fixe par direction (pas d'orbite continue)
      if (p.weapon && p.weapon !== "fists" && p.alive) {
        const texKey = `wpn_${p.weapon}`;
        if (entity.weaponIcon.texture.key !== texKey) entity.weaponIcon.setTexture(texKey);
        entity.weaponIcon.setVisible(true);
        const slot = HAND_OFFSETS[aimDir];
        entity.weaponIcon.setPosition(slot.x, slot.y);
        entity.weaponIcon.setRotation(slot.rot);
        entity.weaponIcon.setFlipX(aimDir === "left");
      } else {
        entity.weaponIcon.setVisible(false);
      }

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

        const attackAnimName = WEAPON_ATTACK_ANIM[p.weapon] || "attack";
        const isAttackAnim = entity.currentAnim === `${attackAnimName}_${aimDir}`;
        const attackStillPlaying = isAttackAnim && entity.sprite.anims.isPlaying;
        const newShot = p.shooting && p.lastShot !== lastShotStamp[p.id];

        if (newShot) {
          lastShotStamp[p.id] = p.lastShot;
          playAnim(entity, p.sprite, attackAnimName, aimDir, true);
          spawnSlashEffect(p);
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
      const angle = pr.angle || 0;
      scene.projGraphics.fillStyle(color, 1);
      scene.projGraphics.lineStyle(1.5, 0xffffff, 0.8);

      if (pr.weapon === "axe") {
        // flèche fine orientée dans le sens du tir
        const cos = Math.cos(angle), sin = Math.sin(angle);
        const tip = { x: pr.x + cos * 9, y: pr.y + sin * 9 };
        const tail = { x: pr.x - cos * 9, y: pr.y - sin * 9 };
        const perp = { x: -sin * 2.5, y: cos * 2.5 };
        scene.projGraphics.beginPath();
        scene.projGraphics.moveTo(tip.x, tip.y);
        scene.projGraphics.lineTo(tail.x + perp.x, tail.y + perp.y);
        scene.projGraphics.lineTo(tail.x - perp.x, tail.y - perp.y);
        scene.projGraphics.closePath();
        scene.projGraphics.fillPath();
      } else if (pr.weapon === "sword") {
        // petite lame allongée
        const cos = Math.cos(angle), sin = Math.sin(angle);
        const tip = { x: pr.x + cos * 8, y: pr.y + sin * 8 };
        const tail = { x: pr.x - cos * 8, y: pr.y - sin * 8 };
        scene.projGraphics.lineStyle(3, color, 1);
        scene.projGraphics.lineBetween(tail.x, tail.y, tip.x, tip.y);
      } else if (pr.weapon === "mace") {
        // boule lourde
        scene.projGraphics.fillCircle(pr.x, pr.y, 7);
        scene.projGraphics.strokeCircle(pr.x, pr.y, 7);
      } else {
        // poings : petit point
        scene.projGraphics.fillCircle(pr.x, pr.y, 4);
      }
    });
  }

  const monsterEntities = {}; // id -> { container, sprite, hpFill, currentAnim }
  const lastMonsterHealth = {};
  const lastMonsterAttack = {};
  const lastMonsterDeath = {};

  function ensureMonsterEntity(m) {
    if (monsterEntities[m.id]) return monsterEntities[m.id];
    const container = scene.add.container(m.x, m.y).setDepth(500);
    const shadow = scene.add.ellipse(0, 16, 22, 8, 0x000000, 0.4);
    const sprite = scene.add.sprite(0, 0, "monster_idle", 0).setOrigin(0.5, 0.62).setScale(0.55);
    const hpBg = scene.add.rectangle(0, -30, 34, 5, 0x2a2e3b).setOrigin(0.5);
    const hpFill = scene.add.rectangle(-17, -30, 34, 5, 0x5dbe7c).setOrigin(0, 0.5);
    container.add([shadow, sprite, hpBg, hpFill]);
    const entity = { container, sprite, hpFill, currentAnim: "idle" };
    monsterEntities[m.id] = entity;
    return entity;
  }

  function playMonsterAnim(entity, name, restart) {
    if (entity.currentAnim === name && !restart) return;
    entity.currentAnim = name;
    entity.sprite.play(`monster_${name}`);
  }

  function drawMonsters() {
    if (!scene) return;
    const seen = new Set();

    latestState.monsters.forEach((m) => {
      seen.add(m.id);
      const entity = ensureMonsterEntity(m);
      entity.container.setPosition(m.x, m.y);
      entity.sprite.setFlipX(Math.cos(m.moveAngle || 0) < 0);

      const ratio = Math.max(0, m.health / m.maxHealth);
      entity.hpFill.width = 34 * ratio;

      if (!m.alive) {
        entity.hpFill.visible = false;
        if (m.justDied && m.justDied !== lastMonsterDeath[m.id]) {
          lastMonsterDeath[m.id] = m.justDied;
          playMonsterAnim(entity, "death", true);
        }
        return;
      }
      entity.hpFill.visible = true;

      const attackAnimPlaying = entity.currentAnim === "attack" && entity.sprite.anims.isPlaying;
      const hurtAnimPlaying = entity.currentAnim === "hurt" && entity.sprite.anims.isPlaying;
      const newAttack = m.justAttacked && m.justAttacked !== lastMonsterAttack[m.id];
      const tookDamage = lastMonsterHealth[m.id] !== undefined && m.health < lastMonsterHealth[m.id];
      lastMonsterHealth[m.id] = m.health;

      if (newAttack) {
        lastMonsterAttack[m.id] = m.justAttacked;
        playMonsterAnim(entity, "attack", true);
      } else if (attackAnimPlaying) {
        // laisser l'attaque se terminer
      } else if (tookDamage) {
        playMonsterAnim(entity, "hurt", true);
      } else if (hurtAnimPlaying) {
        // laisser la réaction se terminer
      } else {
        playMonsterAnim(entity, "walk");
      }
    });

    Object.keys(monsterEntities).forEach((id) => {
      if (!seen.has(id)) {
        monsterEntities[id].container.destroy();
        delete monsterEntities[id];
        delete lastMonsterHealth[id];
        delete lastMonsterAttack[id];
        delete lastMonsterDeath[id];
      }
    });
  }

  const WEAPON_REACH = { fists: 180, sword: 300, axe: 480, mace: 220 };

  function spawnSlashEffect(p) {
    const reach = WEAPON_REACH[p.weapon] || 180;
    const color = parseInt((WEAPON_COLORS[p.weapon] || "#ffffff").replace("#", "0x"));
    const g = scene.add.graphics().setDepth(997);
    g.lineStyle(4, color, 0.9);
    g.beginPath();
    g.arc(p.x, p.y, reach * 0.75, p.angle - 0.6, p.angle + 0.6, false);
    g.strokePath();
    scene.tweens.add({
      targets: g,
      alpha: 0,
      duration: 180,
      onComplete: () => g.destroy(),
    });
  }

  const WEAPON_LABELS = { fists: "Poings", sword: "Épée", axe: "Hache", mace: "Masse" };
  const WEAPON_COLORS = { sword: "#4FA8E8", axe: "#5DBE7C", mace: "#E8624F" };
  const HAND_OFFSETS = {
    down: { x: 12, y: 10, rot: Math.PI * 0.35 },
    up: { x: -8, y: -8, rot: Math.PI * 1.1 },
    left: { x: -14, y: 6, rot: -Math.PI * 0.35 },
    right: { x: 14, y: 6, rot: Math.PI * 0.35 },
  };

  function drawWeapons() {
    if (!scene) return;
    scene.weaponGraphics.clear();
    const t = scene.time.now / 1000;

    latestState.weapons.forEach((w) => {
      const color = parseInt((w.color || "#ffffff").replace("#", "0x"));

      // halo lumineux pulsant (pas d'ombre sombre pour éviter tout artefact visuel)
      const pulse = 24 + Math.sin(t * 4 + w.x) * 4;
      scene.weaponGraphics.fillStyle(color, 0.22);
      scene.weaponGraphics.fillCircle(w.x, w.y, pulse);
      scene.weaponGraphics.fillStyle(0xffffff, 0.1);
      scene.weaponGraphics.fillCircle(w.x, w.y, pulse * 0.55);
    });

    syncWeaponSprites();
    syncWeaponLabels();
  }

  const weaponIconSprites = {}; // id -> Phaser.Image

  function syncWeaponSprites() {
    const seen = new Set();
    const t = scene.time.now / 1000;
    latestState.weapons.forEach((w) => {
      seen.add(w.id);
      const bob = Math.sin(t * 3 + w.x) * 4;
      if (!weaponIconSprites[w.id]) {
        weaponIconSprites[w.id] = scene.add.image(w.x, w.y + bob, `wpn_${w.type}`)
          .setScale(3.2).setDepth(998);
      } else {
        weaponIconSprites[w.id].setPosition(w.x, w.y + bob);
      }
    });
    Object.keys(weaponIconSprites).forEach((id) => {
      if (!seen.has(id)) {
        weaponIconSprites[id].destroy();
        delete weaponIconSprites[id];
      }
    });
  }

  const weaponLabelTexts = {}; // id -> Phaser.Text

  function syncWeaponLabels() {
    const seen = new Set();
    latestState.weapons.forEach((w) => {
      seen.add(w.id);
      if (!weaponLabelTexts[w.id]) {
        weaponLabelTexts[w.id] = scene.add.text(w.x, w.y - 30, WEAPON_LABELS[w.type] || w.type, {
          fontFamily: "Rubik, sans-serif",
          fontSize: "11px",
          fontStyle: "600",
          color: "#ffffff",
          stroke: "#14161c",
          strokeThickness: 2,
        }).setOrigin(0.5).setDepth(998);
      } else {
        weaponLabelTexts[w.id].setPosition(w.x, w.y - 30);
      }
    });
    Object.keys(weaponLabelTexts).forEach((id) => {
      if (!seen.has(id)) {
        weaponLabelTexts[id].destroy();
        delete weaponLabelTexts[id];
      }
    });
  }

  function updateHud() {
    const me = latestState.players.find((p) => p.id === myId);
    if (me) {
      healthFill.style.width = Math.max(0, (me.health / me.maxHealth) * 100) + "%";
      deathBanner.classList.toggle("hidden", me.alive);
      if (weaponLabelEl) {
        weaponLabelEl.textContent = `${WEAPON_LABELS[me.weapon] || me.weapon} · Nv.${me.weaponLevel}`;
      }
      if (weaponXpFillEl && me.weaponXPNext) {
        weaponXpFillEl.style.width = Math.min(100, (me.weaponXP / me.weaponXPNext) * 100) + "%";
      }
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
    drawWeapons();
    drawMonsters();
    drawProjectiles();
    updateHud();
  }
})();
