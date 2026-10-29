const PAGE = document.body.dataset.page;
let STATE = null;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function frNum(n, digits = 1) {
  return Number(n).toLocaleString("fr-FR", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 2200);
}

async function api(url, options) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error("Erreur réseau");
  return res.json();
}

function clock() {
  const el = $("#clock");
  const tick = () => {
    el.textContent = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  };
  tick();
  setInterval(tick, 1000);
}

function spark(el, series, maxHint) {
  if (!el) return;
  const max = Math.max(maxHint || 1, ...series);
  el.innerHTML = series
    .map((v) => `<i class="bar" style="height:${Math.max(8, (v / max) * 100)}%"></i>`)
    .join("");
}

function sensorCards(data) {
  const s = data.sensors;
  return [
    {
      key: "temp",
      label: "Température",
      value: `${frNum(s.temperature.value)}°`,
      detail: `Moyenne maison · ${s.temperature.updated}`,
      status: s.temperature.status,
    },
    {
      key: "rfid",
      label: "RFID",
      value: s.rfid.last_name,
      detail: `${s.rfid.last_uid} · ${s.rfid.authorized ? "autorisé" : "refusé"}`,
      status: s.rfid.authorized ? "ok" : "danger",
    },
    {
      key: "motion",
      label: "Mouvement humain",
      value: s.motion.detected ? "Détecté" : "Calme",
      detail: `Zone ${s.motion.zone} · ${s.motion.updated}`,
      status: s.motion.status,
    },
    {
      key: "smoke",
      label: "Fumée",
      value: `${s.smoke.level} %`,
      detail: s.smoke.alarm ? "Alerte incendie" : "Air sain",
      status: s.smoke.status,
    },
  ];
}

function renderSensors(data) {
  const grid = $("#sensor-grid");
  if (!grid) return;
  grid.innerHTML = sensorCards(data)
    .map(
      (c) => `<article class="sensor-card">
        <header><span>${c.label}</span><span class="status ${c.status}">${c.status}</span></header>
        <p class="sensor-value">${c.value}</p>
        <p class="muted">${c.detail}</p>
      </article>`
    )
    .join("");
}

function renderPlan(data) {
  const el = $("#floorplan");
  if (!el) return;
  const order = ["salon", "cuisine", "bureau", "chambre", "entree", "garage"];
  const map = Object.fromEntries(data.rooms.map((r) => [r.id, r]));
  el.innerHTML = order
    .map((id) => {
      const r = map[id];
      return `<div class="cell ${r.lights ? "on" : ""} ${r.occupied ? "busy" : ""}" style="${id === "salon" ? "grid-row:1/3" : ""}">
        <strong>${r.name}</strong>
        <small>${frNum(r.temperature)}° · ${r.lights ? "éclairé" : "off"}</small>
      </div>`;
    })
    .join("");
}

function renderTimeline(el, events, limit = 6) {
  if (!el) return;
  el.innerHTML = events
    .slice(0, limit)
    .map(
      (e) => `<li>
        <time>${e.time}</time>
        <div><strong>${e.title}</strong><div class="muted">${e.detail}</div></div>
      </li>`
    )
    .join("");
}

function renderRooms(data) {
  const grid = $("#room-grid");
  if (!grid) return;
  grid.innerHTML = data.rooms
    .map(
      (r) => `<article class="room-card" data-room="${r.id}">
        <header>
          <div>
            <h3>${r.name}</h3>
            <p class="meta">${r.floor} · ${frNum(r.temperature)} °C ${r.occupied ? "· présence" : ""}</p>
          </div>
          <button class="switch ${r.lights ? "on" : ""}" data-toggle-light="${r.id}" aria-label="Lumière"></button>
        </header>
        <div class="sliders">
          <label>Intensité ${r.brightness} %
            <input type="range" min="0" max="100" value="${r.brightness}" data-bright="${r.id}" />
          </label>
          <label>Volets ${r.shutters} %
            <input type="range" min="0" max="100" value="${r.shutters}" data-shutter="${r.id}" />
          </label>
        </div>
        <div class="lock-row">
          <button class="btn ghost" data-lock="${r.id}">${r.lock ? "Déverrouiller" : "Verrouiller"}</button>
        </div>
      </article>`
    )
    .join("");
}

function renderScenes(data) {
  const grid = $("#scene-grid");
  if (!grid) return;
  grid.innerHTML = data.scenes
    .map(
      (s) => `<button class="scene-card" data-scene="${s.id}">
        <h3>${s.name}</h3>
        <p>${s.desc}</p>
      </button>`
    )
    .join("");
}

function renderSecurity(data) {
  const level = data.security.level;
  const label = { serein: "Serein", vigilance: "Vigilance", alerte: "Alerte" }[level];
  const secLevel = $("#sec-level");
  if (secLevel) secLevel.textContent = label;
  const copy = $("#sec-copy");
  if (copy) {
    copy.textContent = data.house.armed
      ? "Alarme armée — les mouvements inattendus déclenchent une vigilance."
      : "Alarme désarmée — la maison accueille les occupants.";
  }
  const arm = $("#sec-arm");
  if (arm) arm.textContent = data.house.armed ? "Désarmer l’alarme" : "Armer l’alarme";

  const tiles = $("#sec-tiles");
  if (tiles) {
    tiles.innerHTML = `
      <div class="tile"><strong>${data.sensors.motion.detected ? "Présence" : "Calme"}</strong><p class="muted">Capteur mouvement · ${data.sensors.motion.zone}</p></div>
      <div class="tile"><strong>${data.sensors.smoke.alarm ? "Fumée !" : "Air sain"}</strong><p class="muted">Niveau ${data.sensors.smoke.level} %</p></div>
      <div class="tile"><strong>${data.security.door ? "Entrée close" : "Entrée ouverte"}</strong><p class="muted">Serrure connectée</p></div>
      <div class="tile"><strong>${data.security.garage ? "Garage clos" : "Garage ouvert"}</strong><p class="muted">Porte de garage</p></div>`;
  }

  const rfid = $("#rfid-card");
  if (rfid) {
    rfid.innerHTML = `<span class="muted">Dernier badge</span>
      <strong>${data.sensors.rfid.last_name}</strong>
      <span>${data.sensors.rfid.last_uid}</span>`;
  }
  const rfidStatus = $("#rfid-status");
  if (rfidStatus) rfidStatus.textContent = data.sensors.rfid.authorized ? "Accès autorisé" : "Accès refusé";

  const actions = $("#rfid-actions");
  if (actions) {
    actions.innerHTML = data.badges
      .map((b) => `<button class="btn ghost" data-sim-rfid="${b.uid}">Simuler ${b.name}</button>`)
      .join("");
  }
  const list = $("#badge-list");
  if (list) {
    list.innerHTML = data.badges
      .map(
        (b) => `<li>
          <div><strong>${b.name}</strong><div class="muted">${b.role} · ${b.uid}</div></div>
          <button class="switch ${b.active ? "on" : ""}" data-badge="${b.uid}"></button>
        </li>`
      )
      .join("");
  }
  renderTimeline($("#sec-timeline"), data.events.filter((e) => ["rfid", "motion", "smoke", "alarm", "lock"].includes(e.kind)), 10);
}

function renderClimate(data) {
  const t = $("#target-temp");
  if (t) t.textContent = `${frNum(data.climate.target)}°`;
  const c = $("#current-temp");
  if (c) c.textContent = `${frNum(data.sensors.temperature.value)} °C`;
  $$("#mode-row button").forEach((b) => b.classList.toggle("on", b.dataset.mode === data.climate.mode));
  const fan = $("#fan-range");
  if (fan && document.activeElement !== fan) fan.value = data.climate.fan;
  const temps = $("#room-temps");
  if (temps) {
    temps.innerHTML = data.rooms
      .map((r) => `<div><span>${r.name}</span><strong>${frNum(r.temperature)} °C</strong></div>`)
      .join("");
  }
  spark($("#temp-spark"), data.history.temperature, 28);
}

function renderActivity(data) {
  spark($("#hist-temp"), data.history.temperature, 28);
  spark($("#hist-smoke"), data.history.smoke, 50);
  spark($("#hist-motion"), data.history.motion, 1);
  spark($("#hist-power"), data.history.power, 3);
  renderTimeline($("#full-timeline"), data.events, 25);
}

function renderChrome(data) {
  $("#house-name").textContent = data.house.name;
  const pill = $("#presence-pill");
  pill.classList.toggle("away", !data.house.presence);
  $("#presence-label").textContent = data.house.presence ? "Maison occupée" : "Maison vide";
  const armBtn = $("#arm-btn");
  armBtn.textContent = data.house.armed ? "Désarmer" : "Armer";

  const strip = $("#alert-strip");
  const danger = data.sensors.smoke.alarm || (data.house.armed && data.sensors.motion.detected);
  strip.classList.toggle("hidden", !danger);
  if (danger) {
    $("#alert-text").textContent = data.sensors.smoke.alarm
      ? "Alerte fumée — vérifiez immédiatement la maison."
      : `Mouvement détecté (${data.sensors.motion.zone}) alors que l’alarme est armée.`;
  }

  const chip = $("#security-chip");
  if (chip) {
    chip.textContent = { serein: "Système serein", vigilance: "Vigilance", alerte: "Alerte fumée" }[data.security.level];
    chip.className = "chip " + (data.security.level === "serein" ? "" : data.security.level === "alerte" ? "danger" : "warn");
  }
}

function renderPage(data) {
  renderChrome(data);
  if (PAGE === "dashboard") {
    $("#hero-temp").textContent = `${frNum(data.sensors.temperature.value)}°`;
    $("#kpi-rooms").textContent = `${data.kpis.rooms_on}/${data.kpis.rooms_total}`;
    $("#kpi-power").textContent = `${frNum(data.house.power_kw, 2)} kW`;
    $("#kpi-hum").textContent = `${data.house.humidity} %`;
    $("#kpi-aqi").textContent = data.house.air_quality;
    renderSensors(data);
    renderPlan(data);
    renderTimeline($("#timeline"), data.events, 5);
  }
  if (PAGE === "rooms") renderRooms(data);
  if (PAGE === "security") renderSecurity(data);
  if (PAGE === "climate") renderClimate(data);
  if (PAGE === "scenes") renderScenes(data);
  if (PAGE === "activity") renderActivity(data);
  if (PAGE === "settings") {
    const input = $("#house-input");
    if (input && document.activeElement !== input) input.value = data.house.name;
  }
}

async function refresh() {
  STATE = await api("/api/status");
  renderPage(STATE);
}

async function post(url, body) {
  STATE = await api(url, { method: "POST", body: JSON.stringify(body || {}) });
  renderPage(STATE);
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

const sendBright = debounce((id, value) => post(`/api/rooms/${id}`, { brightness: Number(value), lights: Number(value) > 0 }), 180);
const sendShutter = debounce((id, value) => post(`/api/rooms/${id}`, { shutters: Number(value) }), 180);

document.addEventListener("click", async (e) => {
  const menu = e.target.closest("#menu-btn");
  if (menu) $("#sidebar").classList.toggle("open");

  const arm = e.target.closest("[data-action='arm-toggle']");
  if (arm && STATE) {
    await post("/api/house", { armed: !STATE.house.armed });
    toast(STATE.house.armed ? "Alarme armée" : "Alarme désarmée");
  }
  const ack = e.target.closest("[data-action='ack']");
  if (ack) {
    await post("/api/alerts/ack");
    toast("Capteurs réarmés");
  }
  const scene = e.target.closest("[data-scene]");
  if (scene) {
    await post(`/api/scenes/${scene.dataset.scene}`);
    toast(`Scénario « ${scene.dataset.scene} » lancé`);
  }
  const light = e.target.closest("[data-toggle-light]");
  if (light) {
    const room = STATE.rooms.find((r) => r.id === light.dataset.toggleLight);
    await post(`/api/rooms/${room.id}`, { lights: !room.lights });
  }
  const lock = e.target.closest("[data-lock]");
  if (lock) {
    const room = STATE.rooms.find((r) => r.id === lock.dataset.lock);
    await post(`/api/rooms/${room.id}`, { lock: !room.lock });
  }
  const badge = e.target.closest("[data-badge]");
  if (badge) {
    await post(`/api/badges/${badge.dataset.badge}/toggle`);
  }
  const sim = e.target.closest("[data-sim-rfid]");
  if (sim) {
    await post("/api/rfid/simulate", { uid: sim.dataset.simRfid });
    toast("Lecture RFID simulée");
  }
  const mode = e.target.closest("[data-mode]");
  if (mode) {
    await post("/api/climate", { mode: mode.dataset.mode });
  }
  const delta = e.target.closest("[data-climate-delta]");
  if (delta && STATE) {
    await post("/api/climate", { target: STATE.climate.target + Number(delta.dataset.climateDelta) });
  }
  const save = e.target.closest("#save-house");
  if (save) {
    await post("/api/house", { name: $("#house-input").value.trim() || STATE.house.name });
    toast("Nom enregistré");
  }
});

document.addEventListener("input", (e) => {
  if (e.target.dataset.bright) sendBright(e.target.dataset.bright, e.target.value);
  if (e.target.dataset.shutter) sendShutter(e.target.dataset.shutter, e.target.value);
  if (e.target.id === "fan-range") post("/api/climate", { fan: Number(e.target.value) });
});

document.addEventListener("click", (e) => {
  const sidebar = $("#sidebar");
  if (sidebar.classList.contains("open") && !e.target.closest(".sidebar") && !e.target.closest("#menu-btn")) {
    sidebar.classList.remove("open");
  }
});

let lastPointer = 0;
document.addEventListener("pointerdown", () => {
  lastPointer = Date.now();
});
document.addEventListener("input", () => {
  lastPointer = Date.now();
});

function isBusy() {
  const el = document.activeElement;
  return Date.now() - lastPointer < 2500 || (el && el.matches("input[type='range'], input[type='text']"));
}

clock();
if (window.__FOYER__) {
  STATE = window.__FOYER__;
  renderPage(STATE);
}
refresh();
setInterval(() => {
  if (isBusy()) return;
  refresh();
}, 4000);
