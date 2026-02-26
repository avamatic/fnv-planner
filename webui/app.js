const fmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });

let appState = null;
let buildPerkQuery = "";
let gearQuery = "";
let showArmor = true;
let showWeapons = true;

function h(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function n(v) {
  if (typeof v !== "number") return h(v ?? "-");
  return fmt.format(v);
}

function showMessage(text, kind = "ok") {
  const node = document.querySelector("#flash");
  if (!node) return;
  node.className = kind === "bad" ? "bad" : "ok";
  node.textContent = text || "";
}

async function fetchState() {
  const res = await fetch("/api/state", { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load /api/state (${res.status})`);
  }
  appState = await res.json();
}

async function postJson(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  let body = null;
  try {
    body = await res.json();
  } catch (_err) {
    throw new Error(`Invalid JSON from ${path}`);
  }

  if (!res.ok || !body.ok) {
    throw new Error(body?.message || `Request failed (${res.status})`);
  }
  appState = body.state;
  renderAll();
  if (body.message) {
    showMessage(body.message, "ok");
  }
}

function rowMetric(label, value) {
  return `<p class="metric"><strong>${h(label)}:</strong> ${n(value)}</p>`;
}

function perkStatusLabel(status) {
  if (status === "none") return "Not Selected";
  if (status === "red") return "Primary Conflict";
  if (status === "yellow") return "Secondary Conflict";
  return "Compatible";
}

function statsCard(title, stats) {
  return `
    <article class="card">
      <h3>${h(title)}</h3>
      ${rowMetric("HP", stats.hit_points)}
      ${rowMetric("AP", stats.action_points)}
      ${rowMetric("Carry", stats.carry_weight)}
      ${rowMetric("Crit %", stats.crit_chance)}
      ${rowMetric("Crit Dmg", stats.crit_damage_potential)}
      ${rowMetric("SP/Level", stats.skill_points_per_level)}
    </article>
  `;
}

function requestText(build, index) {
  const row = build.requests.find((r) => r.index === index);
  return row ? row.text : `Request ${index}`;
}

function drawBuildPerkPicker(build) {
  const perks = appState.library.perks;
  const q = buildPerkQuery.trim().toLowerCase();
  const filtered = q
    ? perks.filter((p) => p.name.toLowerCase().includes(q) || p.category.toLowerCase().includes(q))
    : perks;

  const body = document.querySelector("#perk-picker-body");
  const count = document.querySelector("#perk-picker-count");
  if (!body || !count) return;
  count.textContent = `${filtered.length} / ${perks.length}`;

  body.innerHTML = filtered.slice(0, 400).map((perk) => {
    const status = String(perk.request_status || "none");
    const statusLabel = perkStatusLabel(status);
    const statusReason = String(perk.request_status_reason || "");
    const rowClass = perk.selected && status !== "none" ? `perk-row perk-row--${h(status)}` : "perk-row";
    return `
      <tr class="${rowClass}" title="${h(statusReason)}">
        <td>
          <label>
            <input type="checkbox" data-perk-id="${perk.id}" ${perk.selected ? "checked" : ""} />
            ${h(perk.name)}
          </label>
        </td>
        <td>${h(perk.category)}</td>
        <td><span class="status-chip status-chip--${h(status)}">${h(statusLabel)}</span></td>
        <td>${perk.id}</td>
      </tr>
    `;
  }).join("");

  body.querySelectorAll("input[data-perk-id]").forEach((node) => {
    node.addEventListener("change", async () => {
      const perkId = Number(node.getAttribute("data-perk-id"));
      try {
        await postJson("/api/requests/perk-toggle", {
          perk_id: perkId,
          selected: node.checked,
        });
      } catch (err) {
        showMessage(err.message, "bad");
      }
    });
  });
}

function renderBuild() {
  const panel = document.querySelector("#panel-build");
  const build = appState.build;
  const requestEntries = build.request_entries;

  const requestItems = requestEntries.map((entry) => {
    return `
      <li class="request-row">
        <span>${h(requestText(build, entry.index))}</span>
        <span class="row-actions">
          <button type="button" data-request-action="up" data-index="${entry.index}">Up</button>
          <button type="button" data-request-action="down" data-index="${entry.index}">Down</button>
          <button type="button" data-request-action="remove" data-index="${entry.index}">Remove</button>
        </span>
      </li>
    `;
  }).join("");

  const selectedPerks = build.selected_perks
    .map((p) => `<span class="pill">L${p.level} ${h(p.name)} <small>${h(p.source)}</small></span>`)
    .join("");

  const actorOptions = build.request_controls.actor_values
    .map((opt) => `<option value="${opt.actor_value}" data-max="${opt.max}">${h(opt.name)} (max ${opt.max})</option>`)
    .join("");

  panel.innerHTML = `
    <section class="grid">
      ${statsCard("Current", build.now)}
      ${statsCard("Target", build.target)}
      <article class="card">
        <h3>Status</h3>
        <p class="metric ${build.valid ? "ok" : "bad"}"><strong>Valid:</strong> ${build.valid}</p>
        <p class="metric ${build.feasible ? "ok" : "bad"}"><strong>Feasible:</strong> ${build.feasible}</p>
        <p class="metric"><strong>Message:</strong> ${h(build.feasibility_message)}</p>
        <p class="metric"><strong>Books:</strong> ${build.skill_books.needed} / ${build.skill_books.available}</p>
        <p class="metric"><strong>SPECIAL:</strong> ${build.special.used}/${build.special.budget} (remaining ${build.special.remaining})</p>
      </article>
    </section>

    <article class="card" style="margin-top:12px">
      <h3>Planner Controls</h3>
      <div class="controls">
        <label><input type="checkbox" id="meta-max-skills" ${build.meta.max_skills ? "checked" : ""} /> Max Skills</label>
        <label><input type="checkbox" id="meta-max-crit" ${build.meta.max_crit ? "checked" : ""} /> Max Crit</label>
        <label><input type="checkbox" id="meta-max-crit-dmg" ${build.meta.max_crit_damage ? "checked" : ""} /> Max Crit Dmg</label>
      </div>
      <form id="actor-request-form" class="controls">
        <label>AV</label>
        <select id="actor-value-select">${actorOptions}</select>
        <select id="actor-operator">
          <option value=">=">&gt;=</option>
          <option value="=">=</option>
          <option value="<=">&lt;=</option>
        </select>
        <input id="actor-value-number" type="number" min="1" max="100" value="100" />
        <input id="actor-reason" type="text" placeholder="Reason" />
        <button type="submit">Add Skill/SPECIAL Request</button>
      </form>
      <form id="crit-dmg-form" class="controls">
        <label>Crit Dmg Potential</label>
        <select id="crit-dmg-operator">
          <option value=">=">&gt;=</option>
          <option value="=">=</option>
          <option value="<=">&lt;=</option>
        </select>
        <input id="crit-dmg-value" type="number" min="0" max="9999" value="30" />
        <input id="crit-dmg-reason" type="text" placeholder="Reason" />
        <button type="submit">Add Crit Dmg Request</button>
      </form>
    </article>

    <article class="card" style="margin-top:12px">
      <h3>Priority Requests</h3>
      <ol>${requestItems || "<li>No requests.</li>"}</ol>
    </article>

    <article class="card" style="margin-top:12px">
      <h3>Perk Menu</h3>
      <div class="perk-status-legend">
        <span><i class="legend-swatch legend-green"></i>Green (selected): compatible with primary and secondary requests</span>
        <span><i class="legend-swatch legend-yellow"></i>Yellow (selected): conflicts with secondary requests</span>
        <span><i class="legend-swatch legend-red"></i>Red (selected): contradicts primary request</span>
      </div>
      <div class="controls">
        <label for="perk-picker-search">Search</label>
        <input id="perk-picker-search" type="search" value="${h(buildPerkQuery)}" placeholder="Search perks" />
        <output id="perk-picker-count"></output>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Perk</th><th>Category</th><th>Status</th><th>ID</th></tr></thead>
          <tbody id="perk-picker-body"></tbody>
        </table>
      </div>
    </article>

    <article class="card" style="margin-top:12px">
      <h3>Selected Perks</h3>
      <div>${selectedPerks || "<small>No perks selected.</small>"}</div>
    </article>
  `;

  const actorSelect = panel.querySelector("#actor-value-select");
  const actorValueInput = panel.querySelector("#actor-value-number");
  const actorForm = panel.querySelector("#actor-request-form");
  const critForm = panel.querySelector("#crit-dmg-form");

  function syncActorMax() {
    const opt = actorSelect?.selectedOptions?.[0];
    if (!opt || !actorValueInput) return;
    const max = Number(opt.getAttribute("data-max") || "100");
    actorValueInput.max = String(max);
    if (Number(actorValueInput.value) > max) {
      actorValueInput.value = String(max);
    }
  }

  if (actorSelect) {
    actorSelect.addEventListener("change", syncActorMax);
  }
  syncActorMax();

  panel.querySelectorAll("button[data-request-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const action = btn.getAttribute("data-request-action");
      const index = Number(btn.getAttribute("data-index"));
      try {
        if (action === "remove") {
          await postJson("/api/requests/remove", { index });
        } else if (action === "up") {
          await postJson("/api/requests/move", { index, delta: -1 });
        } else if (action === "down") {
          await postJson("/api/requests/move", { index, delta: 1 });
        }
      } catch (err) {
        showMessage(err.message, "bad");
      }
    });
  });

  panel.querySelector("#meta-max-skills")?.addEventListener("change", async (ev) => {
    try {
      await postJson("/api/requests/meta", {
        kind: "max_skills",
        enabled: ev.target.checked,
      });
    } catch (err) {
      showMessage(err.message, "bad");
    }
  });

  panel.querySelector("#meta-max-crit")?.addEventListener("change", async (ev) => {
    try {
      await postJson("/api/requests/meta", {
        kind: "max_crit",
        enabled: ev.target.checked,
      });
    } catch (err) {
      showMessage(err.message, "bad");
    }
  });

  panel.querySelector("#meta-max-crit-dmg")?.addEventListener("change", async (ev) => {
    try {
      await postJson("/api/requests/meta", {
        kind: "max_crit_damage",
        enabled: ev.target.checked,
      });
    } catch (err) {
      showMessage(err.message, "bad");
    }
  });

  actorForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const payload = {
      actor_value: Number(actorSelect.value),
      operator: panel.querySelector("#actor-operator")?.value || ">=",
      value: Number(actorValueInput.value),
      reason: panel.querySelector("#actor-reason")?.value || "",
    };
    try {
      await postJson("/api/requests/actor-value", payload);
      showMessage("Added actor-value request", "ok");
    } catch (err) {
      showMessage(err.message, "bad");
    }
  });

  critForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const payload = {
      operator: panel.querySelector("#crit-dmg-operator")?.value || ">=",
      value: Number(panel.querySelector("#crit-dmg-value")?.value || "0"),
      reason: panel.querySelector("#crit-dmg-reason")?.value || "",
    };
    try {
      await postJson("/api/requests/crit-damage", payload);
      showMessage("Added crit-damage-potential request", "ok");
    } catch (err) {
      showMessage(err.message, "bad");
    }
  });

  const perkSearch = panel.querySelector("#perk-picker-search");
  perkSearch?.addEventListener("input", () => {
    buildPerkQuery = perkSearch.value;
    drawBuildPerkPicker(build);
  });
  drawBuildPerkPicker(build);
}

function renderProgression() {
  const panel = document.querySelector("#panel-progression");
  const rows = appState.progression.rows;
  const maxLevel = appState.app.target_level;

  panel.innerHTML = `
    <div class="controls">
      <label for="preview-level">Preview Level</label>
      <input id="preview-level" name="preview-level" type="range" min="1" max="${maxLevel}" value="${maxLevel}" />
      <output id="preview-level-value">${maxLevel}</output>
      <small>${h(appState.progression.skill_books_summary)}</small>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Level</th>
            <th>Perk</th>
            <th>Reason</th>
            <th>Spent</th>
            <th>Unspent</th>
            <th>Crit %</th>
            <th>Crit Dmg</th>
            <th>Skills (sample)</th>
          </tr>
        </thead>
        <tbody id="progression-body"></tbody>
      </table>
    </div>
  `;

  const body = panel.querySelector("#progression-body");
  const slider = panel.querySelector("#preview-level");
  const output = panel.querySelector("#preview-level-value");

  function draw(level) {
    output.textContent = String(level);
    const visible = rows.filter((r) => r.level <= level);
    body.innerHTML = visible
      .map((r) => {
        const skills = Object.entries(r.skills)
          .slice(0, 4)
          .map(([k, v]) => `${h(k)} ${v}`)
          .join(" | ");
        return `
          <tr>
            <td>L${r.level}</td>
            <td>${h(r.perk_label)}</td>
            <td>${h(r.perk_reason || "")}</td>
            <td>${r.spent_skill_points}</td>
            <td>${r.unspent_skill_points}</td>
            <td>${n(r.stats.crit_chance)}</td>
            <td>${n(r.stats.crit_damage_potential)}</td>
            <td>${skills}</td>
          </tr>
        `;
      })
      .join("");
  }

  slider.addEventListener("input", () => draw(Number(slider.value)));
  draw(maxLevel);
}

function renderLibrary() {
  const panel = document.querySelector("#panel-library");
  const gear = appState.library.gear;
  const equipped = appState.library.equipped;

  const equippedRows = equipped.map((item) => {
    const effects = (item.effects || []).map((x) => h(x)).join("; ");
    return `
      <tr>
        <td>${item.slot}</td>
        <td>${h(item.kind)}</td>
        <td>${h(item.name)}</td>
        <td>${effects || "-"}</td>
        <td><button type="button" data-clear-slot="${item.slot}">Clear</button></td>
      </tr>
    `;
  }).join("");

  panel.innerHTML = `
    <article class="card">
      <h3>Equipped Gear</h3>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Slot</th><th>Kind</th><th>Name</th><th>Effects</th><th>Action</th></tr></thead>
          <tbody id="equipped-body">${equippedRows || "<tr><td colspan='5'>No gear equipped.</td></tr>"}</tbody>
        </table>
      </div>
    </article>

    <article class="card" style="margin-top:12px">
      <h3>Gear Catalog</h3>
      <div class="controls">
        <label for="gear-search">Search</label>
        <input id="gear-search" type="search" value="${h(gearQuery)}" placeholder="Search gear" />
        <label><input id="gear-armor" type="checkbox" ${showArmor ? "checked" : ""} /> Armor</label>
        <label><input id="gear-weapons" type="checkbox" ${showWeapons ? "checked" : ""} /> Weapons</label>
        <output id="gear-count"></output>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Kind</th><th>Slot</th><th>Crit Dmg/Effects</th><th>Action</th></tr></thead>
          <tbody id="gear-body"></tbody>
        </table>
      </div>
    </article>
  `;

  panel.querySelectorAll("button[data-clear-slot]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await postJson("/api/equipment/clear", { slot: Number(btn.getAttribute("data-clear-slot")) });
      } catch (err) {
        showMessage(err.message, "bad");
      }
    });
  });

  const search = panel.querySelector("#gear-search");
  const armor = panel.querySelector("#gear-armor");
  const weapons = panel.querySelector("#gear-weapons");
  const body = panel.querySelector("#gear-body");
  const count = panel.querySelector("#gear-count");

  function drawGear() {
    const q = gearQuery.trim().toLowerCase();
    const filtered = gear.filter((item) => {
      if (!showArmor && item.kind === "armor") return false;
      if (!showWeapons && item.kind === "weapon") return false;
      if (q && !item.name.toLowerCase().includes(q)) return false;
      return true;
    });

    count.textContent = `${filtered.length} / ${gear.length}`;
    body.innerHTML = filtered.slice(0, 400).map((item) => {
      const details = [];
      if (item.conditional_effects > 0) {
        details.push(`${item.conditional_effects} conditional`);
      }
      if (item.excluded_conditional_effects > 0) {
        details.push(`${item.excluded_conditional_effects} excluded`);
      }
      if (details.length === 0) {
        details.push(`wt ${n(item.weight)}`);
      }
      return `
        <tr>
          <td>${h(item.name)}</td>
          <td>${h(item.kind)}</td>
          <td>${item.slot}</td>
          <td>${h(details.join(" | "))}</td>
          <td><button type="button" data-equip-id="${item.id}">${item.equipped ? "Equipped" : "Equip"}</button></td>
        </tr>
      `;
    }).join("");

    body.querySelectorAll("button[data-equip-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await postJson("/api/equipment/equip", { form_id: Number(btn.getAttribute("data-equip-id")) });
        } catch (err) {
          showMessage(err.message, "bad");
        }
      });
    });
  }

  search?.addEventListener("input", () => {
    gearQuery = search.value;
    drawGear();
  });
  armor?.addEventListener("change", () => {
    showArmor = armor.checked;
    drawGear();
  });
  weapons?.addEventListener("change", () => {
    showWeapons = weapons.checked;
    drawGear();
  });
  drawGear();
}

function renderDiagnostics() {
  const panel = document.querySelector("#panel-diagnostics");
  const rows = appState.build.diagnostics;
  if (!rows.length) {
    panel.innerHTML = `<article class="card"><h3>Diagnostics</h3><p class="ok">No diagnostics.</p></article>`;
    return;
  }
  panel.innerHTML = `
    <article class="card">
      <h3>Diagnostics</h3>
      <ul>
        ${rows.map((r) => `<li><strong>${h(r.severity)}</strong> ${h(r.code)}: ${h(r.message)}</li>`).join("")}
      </ul>
    </article>
  `;
}

function wireTabs() {
  const tabs = Array.from(document.querySelectorAll(".tab"));
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      tabs.forEach((t) => t.classList.toggle("active", t === tab));
      document.querySelectorAll(".panel").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.panel === target);
      });
    });
  });
}

function renderAll() {
  if (!appState) return;
  document.querySelector("#app-title").textContent = appState.app.banner_title || "FNV Planner";
  const badge = document.querySelector("#app-game-badge");
  if (badge) {
    badge.textContent = String(appState.app.game_variant || "fallout-nv").toUpperCase();
  }
  document.querySelector("#app-meta").textContent = `${appState.app.plugin_mode} | target L${appState.app.target_level} | generated ${appState.generated_at}`;
  renderBuild();
  renderProgression();
  renderLibrary();
  renderDiagnostics();
}

async function main() {
  wireTabs();
  await fetchState();
  renderAll();
}

main().catch((err) => {
  const panel = document.querySelector("#panel-build");
  panel.classList.add("active");
  panel.innerHTML = `<article class="card"><h3>Load Error</h3><p class="bad">${h(err.message)}</p></article>`;
});
