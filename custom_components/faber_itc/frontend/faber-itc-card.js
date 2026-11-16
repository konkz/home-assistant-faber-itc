// Faber ITC fireplace card: flame dial (off / 25-100 %), narrow <> wide, thermostat.
// Usage: type: custom:faber-itc-card (optional: device_id, name)
const FABER_CARD_VERSION = "0.6.1";

// German for a German UI language, English otherwise
const STRINGS = {
  de: {
    off: "Aus", pilot: "Zünd­flamme", flameHeight: "Flammenhöhe", narrow: "Schmal", wide: "Breit",
    room: "Raum °C", holdHint: "Gedrückt halten", holdToSwitch: "Zum Ein- oder Ausschalten gedrückt halten",
    waitIgniting: "Kamin zündet …", waitShuttingDown: "Kamin geht aus …", waiting: "Warte auf Kamin …",
    unavailable: "Nicht erreichbar", igniting: "Zündet …", shuttingDown: "Geht aus …",
    burningPilot: "Brennt mit Zündflamme", burning: "Brennt", fireplace: "Kamin",
    slow: "Der Kamin braucht etwa 40 Sekunden, bis er den neuen Zustand meldet.",
    thermoOff: "Aus – Flamme wird von Hand gestellt", thermoWaiting: "Regelt, sobald der Kamin brennt",
    thermoHeating: "Heizt auf", thermoIdle: "Ziel erreicht – Zündflamme", thermoActive: "Aktiv",
    missing: "Keine Faber-ITC-Entitäten gefunden.",
  },
  en: {
    off: "Off", pilot: "Pilot", flameHeight: "Flame height", narrow: "Narrow", wide: "Wide",
    room: "Room °C", holdHint: "Press and hold", holdToSwitch: "Press and hold to turn on or off",
    waitIgniting: "Igniting …", waitShuttingDown: "Turning off …", waiting: "Waiting for fireplace …",
    unavailable: "Unavailable", igniting: "Igniting …", shuttingDown: "Turning off …",
    burningPilot: "Burning with pilot flame", burning: "Burning", fireplace: "Fireplace",
    slow: "The fireplace takes about 40 seconds to report its new state.",
    thermoOff: "Off – flame is set by hand", thermoWaiting: "Regulates once the fireplace burns",
    thermoHeating: "Heating", thermoIdle: "Target reached – pilot flame", thermoActive: "Active",
    missing: "No Faber ITC entities found.",
  },
};

const STEPS = [0, 25, 50, 75, 100];
const ARC_START = 135; // degrees, 0 % at bottom left
const ARC_SPAN = 270; // 100 % at bottom right
const SIZE = 220, CX = 110, CY = 110, R = 84;

const point = (deg, r = R) => {
  const rad = (deg * Math.PI) / 180;
  return [CX + r * Math.cos(rad), CY + r * Math.sin(rad)];
};
const angleOf = (value) => ARC_START + (value / 100) * ARC_SPAN;
const arc = (from, to) => {
  if (to - from < 0.5) return "";
  const [x1, y1] = point(angleOf(from));
  const [x2, y2] = point(angleOf(to));
  const large = ((to - from) / 100) * ARC_SPAN > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2}`;
};
const snap = (value) => STEPS.reduce((a, b) => (Math.abs(b - value) < Math.abs(a - value) ? b : a));
const fmtTemp = (t, lang) => (t == null || isNaN(t) ? "–" : Number(t).toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 }));

class FaberItcCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._drag = null; // value while the dial is dragged
    this._targetTimer = null;
    this._target = null; // target temperature not yet sent
  }

  static getStubConfig() { return {}; }
  setConfig(config) { this.config = config || {}; }
  getCardSize() { return 7; }
  getGridOptions() { return { columns: 6, min_columns: 6, rows: "auto" }; }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._update();
  }

  // Entities of the integration, found by their translation key
  _entities() {
    const found = {};
    const byKey = { "switch:power": "power", "number:flame_height": "flame", "select:flame_width": "width", "climate:thermostat": "thermostat", "sensor:temperature": "temp" };
    for (const e of Object.values(this._hass.entities || {})) {
      if (e.platform !== "faber_itc") continue;
      if (this.config.device_id && e.device_id !== this.config.device_id) continue;
      const key = byKey[`${e.entity_id.split(".")[0]}:${e.translation_key}`];
      if (key && !found[key]) found[key] = e.entity_id;
    }
    return found;
  }

  _state(key) { const id = this._ids[key]; return id ? this._hass.states[id] : undefined; }

  _build() {
    this._built = true;
    this._lang = this._hass.locale?.language || this._hass.language || "en";
    const t = (this._t = STRINGS[this._lang.startsWith("de") ? "de" : "en"]);
    const ticks = STEPS.map((v) => {
      const [x1, y1] = point(angleOf(v), R + 12);
      const [lx, ly] = point(angleOf(v), R + 27);
      return `<circle class="tick" cx="${x1}" cy="${y1}" r="2.2"/><text class="tick-label" data-v="${v}" x="${lx}" y="${ly}">${v === 0 ? t.off : v}</text>`;
    }).join("");
    this.shadowRoot.innerHTML = `
      <style>
        :host { --fire: #ff6a2b; --fire-2: #ffb347; --muted: var(--secondary-text-color); }
        ha-card { padding: 18px 18px 16px; overflow: hidden; }
        .head { display: flex; align-items: center; gap: 12px; }
        .badge { width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; background: var(--secondary-background-color); color: var(--muted); transition: background .3s, color .3s, box-shadow .3s; flex: none; }
        .burning .badge { background: rgba(255, 106, 43, .16); color: var(--fire); box-shadow: 0 0 18px rgba(255, 106, 43, .35); }
        .busy .badge ha-icon { animation: pulse 1.2s ease-in-out infinite; }
        @keyframes pulse { 50% { opacity: .35; } }
        .title { flex: 1; min-width: 0; }
        .title b { display: block; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .title span { font-size: 13px; color: var(--muted); }
        .room { text-align: right; }
        .room b { font-size: 22px; font-weight: 600; }
        .room span { display: block; font-size: 11px; color: var(--muted); }
        .dial-wrap { position: relative; width: ${SIZE}px; max-width: 100%; margin: 6px auto 0; }
        svg { width: 100%; height: auto; display: block; touch-action: none; user-select: none; overflow: visible; }
        .track { fill: none; stroke: var(--divider-color, rgba(127,127,127,.25)); stroke-width: 14; stroke-linecap: round; }
        .value { fill: none; stroke: url(#flame); stroke-width: 14; stroke-linecap: round; }
        .tick { fill: var(--muted); opacity: .6; }
        .tick-label { fill: var(--muted); font-size: 11px; text-anchor: middle; dominant-baseline: middle; cursor: pointer; }
        .tick-label.active { fill: var(--primary-text-color); font-weight: 700; }
        .knob { fill: var(--card-background-color, #fff); stroke: var(--fire); stroke-width: 4; cursor: grab; filter: drop-shadow(0 1px 3px rgba(0,0,0,.35)); }
        .off .knob { stroke: var(--muted); }
        .dial-hit { fill: transparent; cursor: pointer; }
        .center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; transform: translateY(8%); }
        .center b { font-size: 38px; font-weight: 700; line-height: 1; }
        .center span { margin-top: 2px; font-size: 12px; color: var(--muted); }
        .spinner { fill: none; stroke: var(--fire); stroke-width: 3; stroke-linecap: round; stroke-dasharray: 70 383; opacity: 0; transition: opacity .3s; transform-box: view-box; transform-origin: ${CX}px ${CY}px; }
        .waiting .spinner { opacity: .85; animation: spin 1.1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .seg button.wait { animation: pulse 1.2s ease-in-out infinite; }
        .row { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
        .seg { flex: 1; display: grid; grid-template-columns: 1fr 1fr; background: var(--secondary-background-color); border-radius: 12px; padding: 3px; }
        .seg button { border: 0; background: transparent; color: var(--primary-text-color); font: inherit; font-size: 14px; padding: 9px 0; border-radius: 9px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; }
        .seg button.on { background: var(--card-background-color, #fff); box-shadow: 0 1px 4px rgba(0,0,0,.18); color: var(--fire); font-weight: 600; }
        .seg button:disabled { cursor: default; opacity: .45; }
        .power { position: relative; width: 52px; height: 52px; border-radius: 50%; border: 0; cursor: pointer; background: var(--secondary-background-color); color: var(--primary-text-color); flex: none; overflow: hidden; }
        .power ha-icon { position: relative; }
        .power .fill { position: absolute; inset: 0; background: var(--fire); transform: scaleY(0); transform-origin: bottom; }
        .power.holding .fill { transform: scaleY(1); transition: transform 1s linear; }
        .burning .power { color: var(--fire); }
        .hint { font-size: 11px; color: var(--muted); text-align: center; margin-top: 4px; min-height: 14px; }
        .thermo { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--divider-color, rgba(127,127,127,.2)); display: flex; align-items: center; gap: 10px; }
        .thermo .info { flex: 1; min-width: 0; }
        .thermo .info b { display: block; font-size: 14px; }
        .thermo .info span { font-size: 12px; color: var(--muted); }
        .target { display: flex; align-items: center; gap: 4px; }
        .target button { width: 34px; height: 34px; border-radius: 50%; border: 0; background: var(--secondary-background-color); color: var(--primary-text-color); font-size: 18px; cursor: pointer; }
        .target b { min-width: 62px; text-align: center; font-size: 17px; }
        .thermo.inactive .target { opacity: .5; }
        .thermo-switch { flex: none; width: 46px; height: 26px; padding: 0; border: 0; border-radius: 13px; background: rgba(127,127,127,.35); position: relative; cursor: pointer; transition: background .2s; }
        .thermo-switch::after { content: ""; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.35); transition: transform .2s; }
        .thermo-switch[aria-checked="true"] { background: var(--fire, #ff6a2b); }
        .thermo-switch[aria-checked="true"]::after { transform: translateX(20px); }
        .error { color: var(--error-color, #db4437); font-size: 12px; margin-top: 8px; min-height: 0; }
        .missing { padding: 16px; color: var(--muted); }
      </style>
      <ha-card>
        <div class="card">
          <div class="head">
            <div class="badge"><ha-icon icon="mdi:fireplace"></ha-icon></div>
            <div class="title"><b class="name"></b><span class="status"></span></div>
            <div class="room"><b class="room-temp">–</b><span>${t.room}</span></div>
          </div>
          <div class="dial-wrap">
            <svg viewBox="-20 -14 ${SIZE + 40} ${SIZE + 4}">
              <defs><linearGradient id="flame" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#ffb347"/><stop offset="1" stop-color="#ff4e1f"/></linearGradient></defs>
              <circle class="dial-hit" cx="${CX}" cy="${CY}" r="${R + 22}"/>
              <path class="track" d="${arc(0, 100)}"/>
              <path class="value" d=""/>
              <circle class="spinner" cx="${CX}" cy="${CY}" r="72"/>
              ${ticks}
              <circle class="knob" r="11" cx="0" cy="0"/>
            </svg>
            <div class="center"><b class="flame-text">–</b><span class="flame-sub">${t.flameHeight}</span></div>
          </div>
          <div class="row">
            <button class="power" title="${t.holdHint}"><span class="fill"></span><ha-icon icon="mdi:power"></ha-icon></button>
            <div class="seg">
              <button data-width="narrow"><ha-icon icon="mdi:arrow-collapse-horizontal"></ha-icon>${t.narrow}</button>
              <button data-width="wide"><ha-icon icon="mdi:arrow-expand-horizontal"></ha-icon>${t.wide}</button>
            </div>
          </div>
          <div class="hint"></div>
          <div class="thermo">
            <ha-icon icon="mdi:thermostat"></ha-icon>
            <div class="info"><b>Thermostat</b><span class="thermo-status"></span></div>
            <div class="target"><button data-step="-1">−</button><b class="target-text">–</b><button data-step="1">+</button></div>
            <button class="thermo-switch" role="switch" aria-checked="false" aria-label="Thermostat"></button>
          </div>
          <div class="error"></div>
        </div>
        <div class="missing" hidden>${t.missing}</div>
      </ha-card>`;
    const $ = (s) => this.shadowRoot.querySelector(s);
    this._el = {
      card: $(".card"), missing: $(".missing"), name: $(".name"), status: $(".status"), roomTemp: $(".room-temp"),
      svg: $("svg"), value: $(".value"), knob: $(".knob"), flameText: $(".flame-text"), flameSub: $(".flame-sub"),
      power: $(".power"), hint: $(".hint"), thermo: $(".thermo"), thermoStatus: $(".thermo-status"),
      targetText: $(".target-text"), thermoSwitch: $(".thermo-switch"), error: $(".error"),
      labels: [...this.shadowRoot.querySelectorAll(".tick-label")], widths: [...this.shadowRoot.querySelectorAll("[data-width]")],
    };
    this._bindDial();
    this._bindPower();
    this._el.widths.forEach((b) => b.addEventListener("click", () => this._setWidth(b.dataset.width)));
    this._el.labels.forEach((l) => l.addEventListener("click", (ev) => { ev.stopPropagation(); this._setFlame(Number(l.dataset.v)); }));
    this.shadowRoot.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => this._stepTarget(Number(b.dataset.step))));
    // Own toggle instead of ha-switch: the frontend only loads ha-switch when a built-in card needs it
    this._el.thermoSwitch.addEventListener("click", () => {
      const on = this._el.thermoSwitch.getAttribute("aria-checked") !== "true";
      this._el.thermoSwitch.setAttribute("aria-checked", String(on));
      this._call("climate", "set_hvac_mode", this._ids.thermostat, { hvac_mode: on ? "heat" : "off" });
    });
  }

  _bindDial() {
    const svg = this._el.svg;
    const valueAt = (ev) => {
      const box = svg.getBoundingClientRect();
      const vb = svg.viewBox.baseVal;
      const x = vb.x + ((ev.clientX - box.left) / box.width) * vb.width;
      const y = vb.y + ((ev.clientY - box.top) / box.height) * vb.height;
      let rel = (((Math.atan2(y - CY, x - CX) * 180) / Math.PI - ARC_START) % 360 + 360) % 360;
      if (rel > ARC_SPAN) rel = rel < ARC_SPAN + (360 - ARC_SPAN) / 2 ? ARC_SPAN : 0;
      return (rel / ARC_SPAN) * 100;
    };
    svg.addEventListener("pointerdown", (ev) => {
      if (ev.target.classList.contains("tick-label")) return;
      svg.setPointerCapture(ev.pointerId);
      this._drag = valueAt(ev);
      this._renderDial();
    });
    svg.addEventListener("pointermove", (ev) => {
      if (this._drag == null) return;
      this._drag = valueAt(ev);
      this._renderDial();
    });
    const end = () => {
      if (this._drag == null) return;
      const value = snap(this._drag);
      this._drag = null;
      if (value !== this._flameValue()) this._setFlame(value);
      else this._renderDial();
    };
    svg.addEventListener("pointerup", end);
    svg.addEventListener("pointercancel", () => { this._drag = null; this._renderDial(); });
  }

  _bindPower() {
    const btn = this._el.power;
    let timer = null;
    const cancel = () => { clearTimeout(timer); timer = null; btn.classList.remove("holding"); };
    btn.addEventListener("pointerdown", () => {
      btn.classList.add("holding");
      timer = setTimeout(() => {
        cancel();
        const on = this._state("power")?.state === "on";
        this._call("switch", on ? "turn_off" : "turn_on", this._ids.power);
      }, 1000);
    });
    ["pointerup", "pointerleave", "pointercancel"].forEach((e) => btn.addEventListener(e, cancel));
    btn.addEventListener("click", () => { if (!timer) this._hint(this._t.holdToSwitch); });
  }

  // The requested value stays on screen until the entity shows it (the
  // integration holds it until the fireplace confirms), so nothing jumps back.
  _setFlame(value) {
    this._pendingFlame = { value, until: Infinity };
    this._update();
    this._call("number", "set_value", this._ids.flame, { value })
      .then((ok) => { this._pendingFlame = ok && this._pendingFlame ? { value, until: Date.now() + 3000 } : null; this._update(); });
  }

  _setWidth(option) {
    if (option === this._state("width")?.state) return;
    this._pendingWidth = { value: option, until: Infinity };
    this._update();
    this._call("select", "select_option", this._ids.width, { option })
      .then((ok) => { this._pendingWidth = ok && this._pendingWidth ? { value: option, until: Date.now() + 3000 } : null; this._update(); });
  }

  // Drop a local pending value once the entity shows it, or once it timed out
  // and the integration is not waiting for the fireplace anymore
  _settle(pending, current, integrationWaiting) {
    if (!pending || pending.value === current) return null;
    return Date.now() > pending.until && !integrationWaiting ? null : pending;
  }

  _stepTarget(dir) {
    const t = this._state("thermostat");
    if (!t) return;
    const step = t.attributes.target_temp_step || 0.5;
    const current = this._target ?? t.attributes.temperature ?? 21;
    this._target = Math.min(t.attributes.max_temp ?? 28, Math.max(t.attributes.min_temp ?? 15, current + dir * step));
    this._update();
    clearTimeout(this._targetTimer);
    this._targetTimer = setTimeout(() => {
      const temperature = this._target;
      this._call("climate", "set_temperature", this._ids.thermostat, { temperature }).finally(() => { this._target = null; this._update(); });
    }, 700);
  }

  _call(domain, service, entity_id, data = {}) {
    if (!entity_id) return Promise.resolve();
    return this._hass.callService(domain, service, { entity_id, ...data }).then(() => true, (err) => {
      this._el.error.textContent = err?.message || String(err);
      clearTimeout(this._errTimer);
      this._errTimer = setTimeout(() => { this._el.error.textContent = ""; }, 6000);
      return false;
    });
  }

  _hint(text) {
    this._tempHint = text;
    this._tempHintUntil = Date.now() + 2500;
    this._update();
    clearTimeout(this._hintTimer);
    this._hintTimer = setTimeout(() => this._update(), 2600);
  }

  _status() { return this._state("power")?.attributes?.status || (this._state("power")?.state === "on" ? "on" : "off"); }

  _flameValue() {
    const n = Number(this._state("flame")?.state);
    return isNaN(n) ? 0 : snap(n);
  }

  _waiting() {
    const status = this._status();
    return !!this._pendingFlame || !!this._state("flame")?.attributes?.pending || status === "igniting" || status === "shutting_down";
  }

  _renderDial() {
    const status = this._status();
    const burning = status === "on" || status === "igniting";
    const waiting = this._drag == null && this._waiting();
    const shown = this._drag != null ? this._drag : this._pendingFlame?.value ?? this._flameValue();
    const snapped = snap(shown);
    this._el.value.setAttribute("d", arc(0, shown));
    const [kx, ky] = point(angleOf(shown));
    this._el.knob.setAttribute("cx", kx);
    this._el.knob.setAttribute("cy", ky);
    this._el.svg.classList.toggle("off", snapped === 0);
    this._el.labels.forEach((l) => l.classList.toggle("active", Number(l.dataset.v) === snapped));
    const t = this._t;
    let text = snapped === 0 ? t.off : `${snapped} %`;
    let sub = t.flameHeight;
    if (snapped === 0 && burning && this._drag == null && !this._pendingFlame) { text = t.pilot; sub = "0 %"; }
    if (waiting) sub = status === "igniting" ? t.waitIgniting : status === "shutting_down" ? t.waitShuttingDown : t.waiting;
    this._el.svg.closest(".dial-wrap").classList.toggle("waiting", waiting);
    this._el.flameText.textContent = text;
    this._el.flameText.style.fontSize = text.length > 6 ? "24px" : "";
    this._el.flameSub.textContent = sub;
  }

  _update() {
    if (!this._hass || !this._built) return;
    this._ids = this._entities();
    const ok = !!this._ids.power;
    this._el.card.hidden = !ok;
    this._el.missing.hidden = ok;
    if (!ok) return;

    const s = this._t;
    const power = this._state("power");
    const status = this._status();
    const burning = status === "on" || status === "igniting";
    const busy = status === "igniting" || status === "shutting_down";
    const unavailable = !power || power.state === "unavailable";
    this._el.card.classList.toggle("burning", burning);
    this._el.card.classList.toggle("busy", busy);

    const dev = power && this._hass.devices?.[this._hass.entities[this._ids.power]?.device_id];
    this._el.name.textContent = this.config.name || dev?.name_by_user || dev?.name || s.fireplace;
    this._pendingFlame = this._settle(this._pendingFlame, this._flameValue(), this._state("flame")?.attributes?.pending);
    this._pendingWidth = this._settle(this._pendingWidth, this._state("width")?.state, this._state("width")?.attributes?.pending);
    const flame = this._pendingFlame?.value ?? this._flameValue();
    this._el.status.textContent = unavailable ? s.unavailable
      : status === "igniting" ? s.igniting
      : status === "shutting_down" ? s.shuttingDown
      : status === "on" ? (flame === 0 ? s.burningPilot : `${s.burning} · ${flame} %`)
      : s.off;
    const temp = this._state("temp")?.state;
    this._el.roomTemp.textContent = fmtTemp(parseFloat(temp), this._lang);

    if (this._drag == null) this._renderDial();

    const widthState = this._state("width");
    const width = this._pendingWidth?.value ?? widthState?.state;
    const widthWaiting = !!this._pendingWidth || !!widthState?.attributes?.pending;
    this._el.widths.forEach((b) => {
      b.classList.toggle("on", b.dataset.width === width);
      b.classList.toggle("wait", widthWaiting && b.dataset.width === width);
      b.disabled = !burning || status === "igniting";
    });

    this._el.hint.textContent = busy ? s.slow
      : Date.now() < this._tempHintUntil ? this._tempHint : "";

    const t = this._state("thermostat");
    this._el.thermo.hidden = !t;
    if (t) {
      const active = t.state === "heat";
      this._el.thermo.classList.toggle("inactive", !active);
      this._el.thermoSwitch.setAttribute("aria-checked", String(active));
      this._el.targetText.textContent = `${fmtTemp(this._target ?? t.attributes.temperature, this._lang)} °C`;
      const action = t.attributes.hvac_action;
      this._el.thermoStatus.textContent = !active ? s.thermoOff
        : !burning ? s.thermoWaiting
        : action === "heating" ? s.thermoHeating
        : action === "idle" ? s.thermoIdle
        : s.thermoActive;
    }
  }
}

if (!customElements.get("faber-itc-card")) {
  customElements.define("faber-itc-card", FaberItcCard);
  window.customCards = window.customCards || [];
  window.customCards.push({ type: "faber-itc-card", name: "Faber ITC", description: "Flame height dial, narrow/wide and thermostat", preview: false });
  console.info(`%c FABER-ITC-CARD %c ${FABER_CARD_VERSION} `, "color:#fff;background:#ff6a2b", "");
}
