(() => {
  const ARENA_W = 1000;
  const ARENA_H = 700;
  const PLAYER_RADIUS = 18;
  const PROJECTILE_RADIUS = 5;

  const lobby = document.getElementById("lobby");
  const gameScreen = document.getElementById("gameScreen");
  const nameInput = document.getElementById("nameInput");
  const playBtn = document.getElementById("playBtn");
  const connStatus = document.getElementById("connStatus");
  const healthFill = document.getElementById("healthFill");
  const scoreboardEl = document.getElementById("scoreboard");
  const deathBanner = document.getElementById("deathBanner");
  const canvas = document.getElementById("arena");
  const ctx = canvas.getContext("2d");

  let selectedType = null;
  let myId = null;
  let latestState = { players: [], projectiles: [] };

  function fitCanvas() {
    const maxW = Math.min(ARENA_W, window.innerWidth - 24);
    const scale = maxW / ARENA_W;
    canvas.style.width = ARENA_W * scale + "px";
    canvas.style.height = ARENA_H * scale + "px";
    canvas.width = ARENA_W;
    canvas.height = ARENA_H;
  }
  window.addEventListener("resize", fitCanvas);
  fitCanvas();

  // ---------------- Lobby: choix du personnage ----------------
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
    requestAnimationFrame(loop);
  });

  socket.on("state", (data) => {
    latestState = data;
  });

  playBtn.addEventListener("click", () => {
    socket.emit("join", { name: nameInput.value.trim(), type: selectedType });
  });

  // ---------------- Contrôles ----------------
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

  canvas.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleY;
    const me = latestState.players.find((p) => p.id === myId);
    if (me) aimAngle = Math.atan2(my - me.y, mx - me.x);
  });
  canvas.addEventListener("mousedown", () => { shooting = true; });
  window.addEventListener("mouseup", () => { shooting = false; });

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

  // ---------------- Rendu ----------------
  function drawGrid() {
    ctx.fillStyle = "#1a1d26";
    ctx.fillRect(0, 0, ARENA_W, ARENA_H);
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 1;
    for (let x = 0; x <= ARENA_W; x += 50) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, ARENA_H); ctx.stroke();
    }
    for (let y = 0; y <= ARENA_H; y += 50) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(ARENA_W, y); ctx.stroke();
    }
  }

  function drawPlayer(p) {
    if (!p.alive) return;
    ctx.save();
    ctx.translate(p.x, p.y);

    // corps
    ctx.beginPath();
    ctx.arc(0, 0, PLAYER_RADIUS, 0, Math.PI * 2);
    ctx.fillStyle = p.color;
    ctx.fill();
    ctx.lineWidth = p.id === myId ? 3 : 2;
    ctx.strokeStyle = p.id === myId ? "#ffffff" : "rgba(255,255,255,0.4)";
    ctx.stroke();

    // direction de visée
    ctx.rotate(p.angle);
    ctx.beginPath();
    ctx.moveTo(PLAYER_RADIUS - 4, 0);
    ctx.lineTo(PLAYER_RADIUS + 12, 0);
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#ffffff";
    ctx.stroke();
    ctx.restore();

    // nom + barre de vie
    ctx.font = "12px Rubik, sans-serif";
    ctx.textAlign = "center";
    ctx.fillStyle = "#eef0f4";
    ctx.fillText(p.name, p.x, p.y - PLAYER_RADIUS - 18);

    const barW = 40;
    const ratio = Math.max(0, p.health / p.maxHealth);
    ctx.fillStyle = "#2a2e3b";
    ctx.fillRect(p.x - barW / 2, p.y - PLAYER_RADIUS - 12, barW, 5);
    ctx.fillStyle = ratio > 0.4 ? "#5DBE7C" : "#E8624F";
    ctx.fillRect(p.x - barW / 2, p.y - PLAYER_RADIUS - 12, barW * ratio, 5);
  }

  function drawProjectile(pr) {
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, PROJECTILE_RADIUS, 0, Math.PI * 2);
    ctx.fillStyle = pr.color;
    ctx.shadowColor = pr.color;
    ctx.shadowBlur = 8;
    ctx.fill();
    ctx.shadowBlur = 0;
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

  function loop() {
    drawGrid();
    latestState.projectiles.forEach(drawProjectile);
    latestState.players.forEach(drawPlayer);
    updateHud();
    requestAnimationFrame(loop);
  }
})();
