/* Vaidyx-TB workflow atlas: rendering and interaction. Marks and comments go to the local server (POST /api/notes,
   stored in notes.json); if the server cannot be reached they are kept in this browser and sent on the next load. */
(() => {
  const A = window.ATLAS;
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = { get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
                  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} } };
  const S = { notes: { items: {}, general: {} }, online: false, viewAs: store.get("atlas-viewas", ""), section: "overview",
              showMissing: store.get("atlas-missing", true), gapCat: "", gapSev: "", gapText: "", gapMine: false, mxStage: "", openStep: null };
  const roleById = Object.fromEntries(A.roles.map((r) => [r.id, r]));
  const gapById = Object.fromEntries(A.gaps.map((g) => [g.id, g]));
  const ideaById = Object.fromEntries(A.ideas.map((i) => [i.id, i]));
  const stageById = Object.fromEntries(A.stages.map((s) => [s.id, s]));
  const engChip = (e) => `<span class="chip eng ${esc(e)}" title="${esc(A.engines[e]?.note)}">${esc(A.engines[e]?.label || e)}</span>`;
  const statusChip = (s) => `<span class="chip ${s}">${{ built: "Built", partial: "Partly built", missing: "Not in the code" }[s]}</span>`;
  const sevChip = (s) => `<span class="chip ${s}">${{ high: "High", medium: "Medium", low: "Low" }[s]}</span>`;

  /* ------------------------------------------------------------ notes */
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("show"), 2200); }
  function setSaved() {
    const el = $("#saved"); const n = Object.keys(S.notes.items).length + Object.keys(S.notes.general).length;
    el.classList.toggle("off", !S.online);
    el.textContent = S.online ? `Notes saved on the server · ${n}` : `Server not reachable: notes kept in this browser · ${n}`;
    el.title = S.online ? "Saved to docs/ui/workflow/notes.json on the H200; Claude can read it" : "They will be sent when the page reaches its server again";
    const c = document.querySelector('.rail a[data-sec="notes"] .n'); if (c) c.textContent = n;
  }
  async function loadNotes() {
    try {
      const r = await fetch("/api/notes", { cache: "no-store" }); if (!r.ok) throw new Error(r.status);
      S.notes = await r.json(); S.notes.items ||= {}; S.notes.general ||= {}; S.online = true;
      const pending = store.get("atlas-pending", []);
      if (pending.length) { for (const p of pending) await post(p, true); store.set("atlas-pending", []); toast(`${pending.length} offline note(s) sent`); }
    } catch (e) { S.online = false; S.notes = store.get("atlas-notes", { items: {}, general: {} }); }
    setSaved();
  }
  async function post(body, quiet) {
    try {
      const r = await fetch("/api/notes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
      const j = await r.json(); S.online = true; if (!quiet) toast("Saved"); return j.saved;
    } catch (e) {
      S.online = false; const p = store.get("atlas-pending", []); p.push(body); store.set("atlas-pending", p);
      if (!quiet) toast("Server not reachable: kept in this browser"); return null;
    } finally { store.set("atlas-notes", S.notes); setSaved(); }
  }
  async function saveItem(id, patch) {
    const cur = S.notes.items[id] || {}; const next = { ...cur, ...patch };
    if (!next.mark && !(next.comment || "").trim()) delete S.notes.items[id]; else S.notes.items[id] = next;
    const stamp = await post({ id, title: next.title || cur.title || id, section: next.section || cur.section || S.section, mark: next.mark || null, comment: next.comment || "" });
    if (stamp && S.notes.items[id]) S.notes.items[id].updated = stamp;
    refreshMarks(id);
  }
  const markHTML = (id, title, section) => {
    const n = S.notes.items[id] || {};
    const b = (k, l) => `<button class="m ${k} ${n.mark === k ? "on" : ""}" data-mark="${k}" aria-pressed="${n.mark === k}">${l}</button>`;
    return `<div class="mk" data-mk="${esc(id)}" data-title="${esc(title)}" data-section="${esc(section)}">
      ${b("keep", "Keep")}${b("change", "Change")}${b("discuss", "Discuss")}
      <button class="m cm ${n.comment ? "has" : ""}" data-cm aria-expanded="false">${n.comment ? "Comment (1)" : "Comment"}</button>
      <span class="stamp">${n.updated ? "saved " + esc(n.updated.slice(5, 16)) : ""}</span>
      <div class="cbox" hidden><textarea id="c-${esc(id)}" aria-label="Comment on ${esc(title)}" placeholder="What should change, what is wrong, what you mean...">${esc(n.comment || "")}</textarea>
        <div class="row"><button class="btn sm primary" data-savecm>Save comment</button><button class="btn sm" data-cmcancel>Close</button><span class="small muted">Ctrl + Enter saves</span></div></div></div>`;
  };
  function refreshMarks(id) {
    document.querySelectorAll(`.mk[data-mk="${CSS.escape(id)}"]`).forEach((el) => {
      const n = S.notes.items[id] || {};
      el.querySelectorAll("button[data-mark]").forEach((b) => { const on = n.mark === b.dataset.mark; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
      const cm = el.querySelector("[data-cm]"); cm.classList.toggle("has", !!n.comment); cm.textContent = n.comment ? "Comment (1)" : "Comment";
      el.querySelector(".stamp").textContent = n.updated ? "saved " + n.updated.slice(5, 16) : "";
    });
    if (S.section === "notes") render();
  }
  const generalHTML = (key, label) => {
    const g = S.notes.general[key];
    return `<div class="gnote"><h4>Your notes on ${esc(label)}</h4>
      <textarea id="g-${esc(key)}" aria-label="Your notes on ${esc(label)}" placeholder="Anything about this section: what is wrong, what is missing, what you want instead.">${esc(g?.text || "")}</textarea>
      <div class="row"><button class="btn sm primary" data-gsave="${esc(key)}">Save notes</button><span class="small muted">${g?.updated ? "saved " + esc(g.updated) : ""}</span></div></div>`;
  };

  /* ------------------------------------------------------------ navigation */
  const SECTIONS = [
    { grp: "Understand" },
    { id: "overview", label: "Overview" }, { id: "roles", label: "Roles" }, { id: "workflow", label: "Workflow by stage" },
    { id: "specialties", label: "Specialties" }, { id: "journeys", label: "Click paths today" },
    { grp: "Detail" },
    { id: "matrix", label: "Who can do what" }, { id: "ai", label: "AI and human checks" }, { id: "notifications", label: "Notifications" }, { id: "screens", label: "Screens today" },
    { grp: "Discuss" },
    { id: "doctors", label: "Doctors' inputs", n: () => (A.doctors?.points.length || 0) + (A.doctors?.asks.length || 0) },
    { id: "gaps", label: "Gaps", n: () => A.gaps.length }, { id: "ideas", label: "Ideas (not decided)", n: () => A.ideas.length },
    { id: "research", label: "Research" }, { id: "glossary", label: "Glossary and docs" },
    { id: "notes", label: "My notes", n: () => Object.keys(S.notes.items).length + Object.keys(S.notes.general).length }
  ];
  function rail() {
    $("#rail").innerHTML = SECTIONS.map((s) => s.grp ? `<div class="grp">${esc(s.grp)}</div>` :
      `<a href="#${s.id}" data-sec="${s.id}" class="${S.section === s.id ? "on" : ""}" ${S.section === s.id ? 'aria-current="page"' : ""}>${esc(s.label)}${s.n ? `<span class="n">${s.n()}</span>` : ""}</a>`).join("");
  }
  function go(sec, opts = {}) {
    if (opts.role !== undefined) setViewAs(opts.role, false);
    S.section = sec; if (location.hash.slice(1) !== sec) history.replaceState(null, "", "#" + sec);
    rail(); render(); window.scrollTo({ top: 0 });
    if (opts.anchor) setTimeout(() => document.getElementById(opts.anchor)?.scrollIntoView({ block: "start" }), 30);
  }
  function setViewAs(id, rerender = true) { S.viewAs = id; store.set("atlas-viewas", id); $("#viewas").value = id; if (rerender) render(); }

  /* ------------------------------------------------------------ sections */
  const R = {};
  R.overview = () => {
    const built = A.roles.filter((r) => r.status !== "missing"), missing = A.roles.filter((r) => r.status === "missing");
    const cnt = (st) => A.steps.filter((s) => s.stage === st).length;
    const castChip = (r) => `<button class="chip link ${r.status}" data-role="${r.id}" data-go="roles">${esc(r.name)}</button>`;
    return `<div class="lede"><div class="eyebrow">Vaidyx-TB · AI support for the Tumour Board</div>
      <h2>Who does what, at each stage of the board</h2>
      <p>${esc(A.meta.scope)}</p>
      <p class="small muted">Built ${esc(A.meta.built)} from the code on ${esc(A.meta.branch)}, the team's plans and Eswar's prompts, plus outside research. It describes what exists; ideas are kept separate and nothing in them is decided.</p></div>
    <div class="howto"><b>How to use this page</b>
      <p>Pick a role in <b>View as</b> to follow one person end to end: the role page, the workflow lanes and the permission table all focus on it.
      On any item press <b>Keep</b>, <b>Change</b> or <b>Discuss</b>, and <b>Comment</b> to write what you think. Every section ends with a notes box.
      Everything is saved to <code>docs/ui/workflow/notes.json</code> on the server, so I can read it back; <b>My notes</b> lists all of it.</p></div>
    <div class="stages">${A.stages.map((s) => `<button class="stagecard ${s.id}" data-go="workflow" data-anchor="stage-${s.id}">
      <span class="stg ${s.id}">${esc(s.label)}</span><span class="small">${esc(s.line)}</span><span class="cnt">${cnt(s.id)} steps</span></button>`).join("")}</div>
    <div class="card"><h3>The cast</h3>
      <p class="small">Green: built. Amber: partly built. Dashed: real boards have this role, the code does not. Click one to open it.</p>
      <div class="cast">${built.map(castChip).join("")}</div><div class="cast">${missing.map(castChip).join("")}</div></div>
    <div class="card"><h3>The flow in one paragraph</h3>
      <p>A treating doctor creates the Case File from the patient's UHID; Vaidyx fetches every report from the hospital system and reads it; the Pre-Authorization check shows what is missing, not final or not signed; the doctor sends the suggested requests to the departments; they sign in their own systems and send Done; the doctor re-fetches; once every check is met the summary is compiled and the Case File is marked ready. The MDT Coordinator builds the session from ready Case Files, records attendance, and the agents of absent heads stand in with cited briefs; the coordinator records the board's decision; checks run on the record and actions go to the departments' inboxes.</p></div>
    <div class="card"><h3>What the research says about Indian boards</h3><div class="tiles">
      ${A.research.india.slice(0, 6).map((x) => `<div class="tile"><b>${esc(x.k)}</b><span>${esc(x.t)}</span><i>Source ${x.src}</i></div>`).join("")}</div>
      <p class="small"><a href="#research" data-go="research">All research and sources</a></p></div>
    <div class="tiles">
      <div class="tile"><b>${A.roles.filter((r) => r.status !== "missing").length}</b><span>roles in the code</span></div>
      <div class="tile"><b>${missing.length}</b><span>real-world roles not in the code</span></div>
      <div class="tile"><b>${A.steps.length}</b><span>workflow steps across 4 stages</span></div>
      <div class="tile"><b>${A.gaps.length}</b><span>gaps found (${A.gaps.filter((g) => g.sev === "high").length} high)</span></div></div>
    ${generalHTML("overview", "the overview")}`;
  };

  R.roles = () => {
    const groups = [...new Set(A.roles.map((r) => r.group))];
    const pick = `<div class="picker">${groups.map((g) => `<span class="lbl">${esc(g)}</span>` + A.roles.filter((r) => r.group === g).map((r) =>
      `<button class="${S.viewAs === r.id ? "on" : ""} ${r.status === "missing" ? "missing" : ""}" data-role="${r.id}">${esc(r.name)}</button>`).join("")).join("")}</div>`;
    const r = roleById[S.viewAs];
    if (!r) return `<div class="lede"><div class="eyebrow">Roles</div><h2>Pick a role</h2><p>Each role page shows who the person is, how the login is made, what they do before, during and after the board, what they cannot do, what they need (from research), the screens, notifications and the gaps that touch them.</p></div><div class="card">${pick}</div>`;
    const stageBlock = (st) => { const items = r.stages[st] || []; if (!items.length) return "";
      return `<div class="stagecol ${st}"><span class="stg ${st}">${esc(stageById[st].label)}</span><ul class="plain">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`; };
    const steps = A.steps.filter((s) => (s.actors || []).includes(r.lane) || (s.involved || []).includes(r.lane));
    const gl = (ids, map, sec) => ids.filter((i) => map[i]).map((i) => `<button class="chip link" data-go="${sec}" data-anchor="it-${i}">${esc(i)} ${esc(map[i].title)}</button>`).join(" ");
    return `<div class="card flat">${pick}</div>
    <div class="card band ${r.status === "missing" ? "" : "before"}" id="it-${r.id}">
      <div class="profile-head"><div><div class="eyebrow">${esc(r.group)}</div><h2>${esc(r.name)}</h2></div>${statusChip(r.status)}</div>
      <p>${esc(r.who)}</p>
      ${r.eswar ? `<blockquote>${esc(r.eswar)}</blockquote>` : ""}
      <dl class="kv"><dt>How the login is made</dt><dd>${esc(r.assigned)}</dd>
        ${r.home ? `<dt>Home today</dt><dd>${esc(r.home)}</dd>` : ""}
        ${r.devices?.length ? `<dt>Devices</dt><dd>${r.devices.map((d) => `<span class="chip">${esc(d)}</span>`).join(" ")}</dd>` : ""}
        ${r.screens?.length ? `<dt>Screens used</dt><dd>${r.screens.map((d) => `<span class="chip">${esc(d)}</span>`).join(" ")}</dd>` : ""}
        ${r.notifications?.length ? `<dt>Notifications</dt><dd>${r.notifications.map((d) => `<span class="chip eng">${esc(d)}</span>`).join(" ")}</dd>` : ""}</dl>
      ${markHTML("role-" + r.id, "Role: " + r.name, "roles")}</div>
    <div class="stagecols">${["setup", "before", "during", "after"].map(stageBlock).join("")}</div>
    <div class="grid two">
      ${r.cannot?.length ? `<div class="card"><h3>Cannot do (today)</h3><ul class="plain">${r.cannot.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
      ${r.needs?.length ? `<div class="card"><h3>What this person needs</h3><ul class="plain">${r.needs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}</div>
    ${steps.length ? `<div class="card"><h3>Workflow steps with this role</h3><div class="row">${steps.map((s) => `<button class="chip link" data-go="workflow" data-step="${s.id}"><span class="stg ${s.stage}">${esc(s.id)}</span> ${esc(s.title)}</button>`).join("")}</div></div>` : ""}
    ${r.gaps?.length ? `<div class="card"><h3>Gaps that touch this role</h3><div class="row">${gl(r.gaps, gapById, "gaps")}</div></div>` : ""}
    ${r.ideas?.length ? `<div class="card"><h3>Ideas for this role (not decided)</h3><div class="row">${gl(r.ideas, ideaById, "ideas")}</div></div>` : ""}
    ${generalHTML("role-" + r.id, "the " + r.name + " role")}`;
  };

  R.workflow = () => {
    const role = roleById[S.viewAs]; const lane = role?.lane;
    const lanes = A.lanes.filter((l) => S.showMissing || !l.missing);
    const legend = `<div class="legend"><span><span class="dot do"></span> does it</span><span><span class="dot in"></span> involved</span><span><span class="dot miss"></span> a role the code does not have</span>
      <label class="row"><input type="checkbox" id="showMissing" ${S.showMissing ? "checked" : ""}> Show missing roles</label>
      ${role ? `<span>Focus: <b>${esc(role.name)}</b> <button class="btn sm" data-role="">Clear</button></span>` : `<span>Pick a role in View as to focus one lane.</span>`}</div>`;
    const table = (st) => {
      const steps = A.steps.filter((s) => s.stage === st.id);
      const head = `<tr><th>Step</th>${lanes.map((l) => `<th class="lane ${l.missing ? "miss" : ""} ${l.id === lane ? "hl" : ""}">${esc(l.label)}</th>`).join("")}</tr>`;
      const rows = steps.map((s) => {
        const inv = new Set([...(s.actors || []), ...(s.involved || [])]); const dim = lane && !inv.has(lane);
        const cells = lanes.map((l) => { const a = (s.actors || []).includes(l.id), i = (s.involved || []).includes(l.id);
          const d = a || i ? `<span class="dot ${l.missing ? "miss" : a ? "do" : "in"}" title="${esc(l.label)}: ${a ? "does it" : "involved"}"></span>` : "";
          return `<td class="cell ${l.id === lane ? "hl" : ""}">${d}</td>`; }).join("");
        const open = S.openStep === s.id;
        const det = open ? `<tr class="detail"><td colspan="${lanes.length + 1}"><div class="detailbox" id="it-${s.id}">
          <p>${esc(s.what)}</p>
          <div class="row">${(s.engine || []).map(engChip).join("")}${s.time ? `<span class="chip">${esc(s.time)}</span>` : ""}</div>
          ${s.screen ? `<div class="small"><b>Screen today:</b> ${esc(s.screen)}</div>` : ""}
          ${s.checkpoint ? `<div class="small"><b>Human check:</b> ${esc(s.checkpoint)}</div>` : ""}
          ${s.gaps?.length ? `<div class="row small"><b>Gaps:</b> ${s.gaps.filter((g) => gapById[g]).map((g) => `<button class="chip link" data-go="gaps" data-anchor="it-${g}">${g} ${esc(gapById[g].title)}</button>`).join(" ")}</div>` : ""}
          ${markHTML("step-" + s.id, "Step " + s.id + ": " + s.title, "workflow")}</div></td></tr>` : "";
        return `<tr class="srow ${dim ? "dim" : ""}" data-step="${s.id}" tabindex="0" aria-expanded="${open}"><td class="step"><span class="sid">${s.id}</span><b>${esc(s.title)}</b>${S.notes.items["step-" + s.id] ? ' <span class="chip">noted</span>' : ""}</td>${cells}</tr>${det}`;
      }).join("");
      return `<div class="card band ${st.id}" id="stage-${st.id}"><div class="row"><h3 class="stg ${st.id}">${esc(st.label)}</h3><span class="small muted">${esc(st.line)}</span></div>
        <div class="scroll"><table class="t swim"><thead>${head}</thead><tbody>${rows}</tbody></table></div></div>`;
    };
    return `<div class="lede"><div class="eyebrow">Workflow</div><h2>The workflow, step by step</h2>
      <p>One table per stage. Rows are steps in order; columns are lanes (who). Click a step to see what happens, which engine runs it, the screen it uses today, the human check and the gaps. Dashed lanes show where research says a missing role would act.</p></div>
      ${legend}${A.stages.map(table).join("")}${generalHTML("workflow", "the workflow")}`;
  };

  R.specialties = () => `<div class="lede"><div class="eyebrow">Specialties</div><h2>The main team and supporting staff</h2>
    <p>Every department in the code is either treating (owns Case Files) or supporting (reports and answers requests). Four are board heads. This table shows what each brings to the board, what it is asked for, and what its AI agent looks for.</p></div>
    <div class="scroll"><table class="t"><thead><tr><th>Specialty</th><th>Group</th><th>Board head</th><th>AI agent</th><th>Produces</th><th>Asked for (protocols)</th><th>In real boards</th><th>Agent looks for</th></tr></thead><tbody>
    ${A.specialties.map((s, i) => `<tr id="it-sp${i}"><td><b>${esc(s.name)}</b>${markHTML("spec-" + i, "Specialty: " + s.name, "specialties")}</td><td>${esc(s.group)}</td><td>${s.head ? '<span class="chip built">Head</span>' : ""}</td><td>${esc(s.agent)}</td><td>${esc(s.produces)}</td><td>${esc(s.asked)}</td><td>${esc(s.real)}</td><td class="small">${esc(s.skill)}</td></tr>`).join("")}
    </tbody></table></div>${generalHTML("specialties", "the specialties")}`;

  R.journeys = () => {
    const js = A.journeys.filter((j) => !S.viewAs || j.role === S.viewAs || roleById[S.viewAs]?.lane === j.role);
    return `<div class="lede"><div class="eyebrow">Click paths</div><h2>How each person moves through today's screens</h2>
      <p>${S.viewAs ? `Showing paths for <b>${esc(roleById[S.viewAs]?.name)}</b>.` : "All roles."} The friction lines are what slows the person down today.</p></div>
      ${js.length ? js.map((j) => `<div class="card" id="it-${j.id}"><div class="row"><span class="sid">${j.id}</span><h3>${esc(j.title)}</h3><span class="chip">${esc(roleById[j.role]?.name)}</span></div>
        <ol class="plain">${j.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
        <div><h4>Friction</h4><ul class="plain">${j.friction.map((f) => `<li>${esc(f)}</li>`).join("")}</ul></div>
        ${markHTML("journey-" + j.id, "Path " + j.id + ": " + j.title, "journeys")}</div>`).join("") : `<div class="card">No click path is written for this role. <button class="btn sm" data-role="">Show all</button></div>`}
      ${generalHTML("journeys", "the click paths")}`;
  };

  const ROLE_COLS = { vaidyxadmin: ["vx"], root: ["root"], deptadmin: ["da"], coordinator: ["co"], treating: ["to", "tx"], supporting: ["sa", "sx"], participant: ["pa"] };
  R.matrix = () => {
    const hl = new Set(ROLE_COLS[S.viewAs] || []);
    const rows = A.matrix.filter((m) => !S.mxStage || m.stage === S.mxStage);
    const stageBtns = [["", "All"], ...A.stages.map((s) => [s.id, s.label])].map(([k, l]) => `<button class="${S.mxStage === k ? "on" : ""}" data-mxstage="${k}">${esc(l)}</button>`).join("");
    return `<div class="lede"><div class="eyebrow">Permissions</div><h2>Who can do what (from the code)</h2>
      <p>Read from <code>org.py</code> (ACTIONS, can), <code>access.py</code> (per Case File) and the routes, 16 Oct 2026. A Vaidyx admin may do everything. Hover a cell for its meaning.</p></div>
      <div class="filters">${stageBtns}</div>
      <div class="legend">${Object.entries(A.matrixCodes).map(([k, v]) => `<span><span class="code ${k === "-" ? "dash" : k}">${esc(k)}</span> ${esc(v)}</span>`).join("")}</div>
      <div class="scroll"><table class="t mx"><thead><tr><th>Action</th>${A.matrixCols.map((c) => `<th class="c ${hl.has(c.id) ? "hl" : ""}">${esc(c.label)}</th>`).join("")}</tr></thead><tbody>
      ${rows.map((m, i) => { const cells = m.cells.split(" ");
        return `<tr id="it-mx-${m.key}"><td><span class="stg ${m.stage}">${esc(stageById[m.stage].label)}</span><br><b>${esc(m.action)}</b> <code class="muted">${esc(m.key)}</code>${m.note ? `<div class="note">${esc(m.note)}</div>` : ""}${markHTML("mx-" + m.key, "Permission: " + m.action, "matrix")}</td>
        ${cells.map((c, j) => `<td class="c ${hl.has(A.matrixCols[j].id) ? "hl" : ""}"><span class="code ${c === "-" ? "dash" : c}" title="${esc(A.matrixCols[j].label)}: ${esc(A.matrixCodes[c])}">${esc(c)}</span></td>`).join("")}</tr>`; }).join("")}
      </tbody></table></div>${generalHTML("matrix", "the permissions")}`;
  };

  R.ai = () => `<div class="lede"><div class="eyebrow">AI and human checks</div><h2>What the AI does, and where a person must act</h2>
    <p>Every value or sentence shown as fact needs a verified verbatim quote; unverified ones are dropped or sent for review. Confirmations by clinicians beat model output and survive a re-process.</p></div>
    <div class="row">${Object.keys(A.engines).map(engChip).join("")}</div>
    <div class="scroll"><table class="t"><thead><tr><th>Stage</th><th>What</th><th>Engine</th><th>Output</th><th>What the user sees</th></tr></thead><tbody>
    ${A.ai.map((x, i) => `<tr><td><span class="stg ${x.stage}">${esc(stageById[x.stage].label)}</span></td><td><b>${esc(x.what)}</b>${markHTML("ai-" + i, "AI: " + x.what, "ai")}</td><td>${engChip(x.engine)}</td><td>${esc(x.out)}</td><td>${esc(x.user)}</td></tr>`).join("")}
    </tbody></table></div>
    <div class="card"><h3>Human checkpoints</h3><div class="scroll"><table class="t"><thead><tr><th>Checkpoint</th><th>Who</th><th>When</th><th>Reason needed</th></tr></thead><tbody>
    ${A.checkpoints.map((c, i) => `<tr><td><b>${esc(c.name)}</b>${markHTML("cp-" + i, "Checkpoint: " + c.name, "ai")}</td><td>${esc(c.who)}</td><td>${esc(c.when)}</td><td>${c.reason ? "Yes" : "No"}</td></tr>`).join("")}
    </tbody></table></div></div>
    <div class="card"><h3>Scope refusals (wording today)</h3><ul class="plain">
      <li>Treatment: "I can't recommend or choose treatment. Treatment decisions belong to the Tumour Board..."</li>
      <li>Diagnosis: "I can't make or suggest a diagnosis. I can show the diagnosis exactly as recorded..."</li>
      <li>Images: "I don't interpret images or scans. I can show what the signed imaging reports record, with quotes."</li>
      <li>Stage: "I don't derive or assign stage. I can show the stage exactly as recorded..."</li>
      <li>Nothing verifiable: "Not documented in the Case File."</li></ul></div>
    ${generalHTML("ai", "AI and human checks")}`;

  R.notifications = () => `<div class="lede"><div class="eyebrow">Notifications</div><h2>Who hears what, and when</h2>
    <p>In-app only (the bell). A department's notification reaches its doctors and heads; department and root admins never receive any. Overdue is worked out on display and never notified.</p></div>
    <div class="scroll"><table class="t"><thead><tr><th>Kind</th><th>Goes to</th><th>When</th></tr></thead><tbody>
    ${A.notifications.map((n, i) => `<tr><td><code>${esc(n.kind)}</code>${markHTML("nt-" + i, "Notification: " + n.kind, "notifications")}</td><td>${esc(n.to)}</td><td>${esc(n.when)}</td></tr>`).join("")}
    </tbody></table></div>${generalHTML("notifications", "notifications")}`;

  R.screens = () => `<div class="lede"><div class="eyebrow">Screens today</div><h2>What exists in the interface now</h2>
    <p>One page app at <code>/tb</code> (static/tb: index.html, tb.js 376 KB, tb.css). Top bar groups: Start, Board, Admin, About the AI. The Case File has seven tabs.</p></div>
    <div class="scroll"><table class="t"><thead><tr><th>Screen</th><th>Who</th><th>What is on it</th></tr></thead><tbody>
    ${A.screens.map((s, i) => `<tr><td><b>${esc(s.name)}</b>${markHTML("scr-" + i, "Screen: " + s.name, "screens")}</td><td>${esc(s.who)}</td><td>${esc(s.what)}</td></tr>`).join("")}
    </tbody></table></div>${generalHTML("screens", "the screens")}`;

  R.gaps = () => {
    const role = roleById[S.viewAs]; const t = S.gapText.toLowerCase();
    const list = A.gaps.filter((g) => (!S.gapCat || g.cat === S.gapCat) && (!S.gapSev || g.sev === S.gapSev)
      && (!S.gapMine || !role || g.roles.includes(role.id) || (role.gaps || []).includes(g.id))
      && (!t || (g.id + g.title + g.detail + g.where).toLowerCase().includes(t)));
    const catBtns = [["", "All"], ...A.gapCats.map((c) => [c, c])].map(([k, l]) => `<button class="${S.gapCat === k ? "on" : ""}" data-gapcat="${esc(k)}">${esc(l)}</button>`).join("");
    const sevBtns = [["", "Any"], ["high", "High"], ["medium", "Medium"], ["low", "Low"]].map(([k, l]) => `<button class="${S.gapSev === k ? "on" : ""}" data-gapsev="${k}">${l}</button>`).join("");
    return `<div class="lede"><div class="eyebrow">Gaps</div><h2>What is missing or wrong today</h2>
      <p>Found in the code, the screens and against the research. Severity is my first reading for discussion. Mark each one.</p></div>
      <div class="filters">${catBtns}</div><div class="filters">${sevBtns}
        <input type="search" id="gapText" placeholder="Search gaps" value="${esc(S.gapText)}" aria-label="Search gaps">
        ${role ? `<label class="row small"><input type="checkbox" id="gapMine" ${S.gapMine ? "checked" : ""}> Only for ${esc(role.name)}</label>` : ""}
        <span class="small muted">${list.length} of ${A.gaps.length}</span></div>
      <div class="grid two">${list.map((g) => `<div class="item sev-${g.sev}" id="it-${g.id}"><h3><span class="sid">${g.id}</span>${esc(g.title)} ${sevChip(g.sev)}</h3>
        <p class="small">${esc(g.detail)}</p>${g.where ? `<div class="where">${esc(g.where)}</div>` : ""}
        <div class="row">${g.roles.filter((r) => roleById[r]).map((r) => `<button class="chip link" data-role="${r}" data-go="roles">${esc(roleById[r].name)}</button>`).join("")}<span class="chip">${esc(g.cat)}</span></div>
        ${markHTML("gap-" + g.id, g.id + ": " + g.title, "gaps")}</div>`).join("")}</div>
      ${generalHTML("gaps", "the gaps")}`;
  };

  R.doctors = () => {
    const D = A.doctors; if (!D) return "<p>Not loaded.</p>";
    const st = { done: ["built", "Done"], partial: ["partial", "Partly"], missing: ["missing", "Not built"] };
    const tone = { held: "built", partial: "partial", paid: "high", licence: "high", terms: "medium", browser: "medium", notneeded: "low", nottaken: "low" };
    const all = D.lists.flatMap((l) => l.rows.map((r) => r[1]));
    const counts = Object.keys(D.statusLabel).map((k) => [k, all.filter((x) => x === k).length]).filter(([, n]) => n);
    const f = S.docStatus || "";
    const R2 = D.research;
    return `<div class="lede"><div class="eyebrow">Doctors' inputs</div><h2>What the doctors shared, and what the system does with it</h2>
      <p>${esc(D.who)} Checked against the code on the-ui, the guideline library on the server, every chat and every branch (GitHub has only main and vaidyx-theOG, both the same; no other fork or branch holds Vaidyx work).</p></div>
    <div class="grid two">${D.points.map((p) => `<div class="item ${p.status === "missing" ? "sev-high" : p.status === "partial" ? "sev-medium" : "sev-low"}" id="it-${p.id}">
      <h3><span class="sid">${p.id}</span>${esc(p.title)} <span class="chip ${st[p.status][0]}">${st[p.status][1]}</span></h3>
      <div class="small"><b>What we have:</b> ${esc(p.have)}</div><div class="small"><b>Missing:</b> ${esc(p.missing)}</div>
      ${p.where ? `<div class="where">${esc(p.where)}</div>` : ""}${markHTML("doc-" + p.id, p.id + ": " + p.title, "doctors")}</div>`).join("")}</div>

    <div class="card band before"><h3>The WhatsApp discussion, ask by ask</h3><div class="scroll"><table class="t"><thead><tr><th>Ask</th><th>Who</th><th>Today</th><th>What is needed</th></tr></thead><tbody>
      ${D.asks.map((w) => `<tr id="it-${w.id}"><td><span class="sid">${w.id}</span><b>${esc(w.ask)}</b>${markHTML("ask-" + w.id, w.id + ": " + w.ask, "doctors")}</td><td>${esc(w.who)}</td><td class="small">${esc(w.today)}</td><td class="small">${esc(w.gap)}</td></tr>`).join("")}
    </tbody></table></div></div>

    <div class="card"><h3>The five reading lists, entry by entry (${all.length} entries)</h3>
      <div class="filters"><button class="${!f ? "on" : ""}" data-docstatus="">All</button>${counts.map(([k, n]) => `<button class="${f === k ? "on" : ""}" data-docstatus="${k}">${esc(D.statusLabel[k])} (${n})</button>`).join("")}</div>
      ${D.lists.map((l) => { const rows = l.rows.filter((r) => !f || r[1] === f); if (!rows.length) return "";
        return `<h4>${esc(l.title)} <span class="mono">${esc(l.file)}</span></h4><div class="scroll"><table class="t"><thead><tr><th>Entry</th><th>Status</th><th>What we hold</th><th>Used by</th></tr></thead><tbody>
        ${rows.map((r) => `<tr><td><b>${esc(r[0])}</b></td><td><span class="chip ${tone[r[1]]}">${esc(D.statusLabel[r[1]])}</span></td><td class="small">${esc(r[2])}</td><td class="small">${esc(r[3] || "Nothing")}</td></tr>`).join("")}
        </tbody></table></div>`; }).join("")}
      ${markHTML("doc-lists", "The five reading lists", "doctors")}</div>

    <div class="card"><h3>How the guideline library is wired today</h3>
      <p class="small">Search weight boosts Indian sources. 'Agents' = which specialty agents read the source for briefs and live answers. 'Dose lines' = rows in the after-board dose and radiotherapy reference table (301 rows). Everything below is also in the general guideline search (Summary tab references, Ask).</p>
      <div class="scroll"><table class="t"><thead><tr><th>Source</th><th>Weight</th><th>Agents</th><th>Dose lines</th><th>Other use</th></tr></thead><tbody>
      ${D.wiring.map((w) => `<tr><td><b>${esc(w[0])}</b></td><td class="mono">${esc(w[1])}</td><td class="small">${esc(w[2])}</td><td class="small">${esc(w[3])}</td><td class="small">${esc(w[4])}</td></tr>`).join("")}
      </tbody></table></div>${markHTML("doc-wiring", "Guideline library wiring", "doctors")}</div>

    ${R2 ? `<div class="card band during"><h3>Research: which cancers to list</h3><p class="small">${esc(R2.top10.note)}</p>
      <div class="scroll"><table class="t"><thead><tr><th>#</th><th>India, both sexes</th><th>NCRP 2020</th><th>GLOBOCAN 2024</th></tr></thead><tbody>
      ${R2.top10.overall.map((r, i) => `<tr><td class="mono">${i + 1}</td><td><b>${esc(r[0])}</b></td><td class="mono">${esc(r[1])}</td><td class="mono">${esc(r[2])}</td></tr>`).join("")}</tbody></table></div>
      <dl class="kv"><dt>Men</dt><dd>${esc(R2.top10.men)}</dd><dt>Women</dt><dd>${esc(R2.top10.women)}</dd><dt>Children</dt><dd>${esc(R2.top10.children)}</dd><dt>Adolescents</dt><dd>${esc(R2.top10.adolescents)}</dd></dl>
      <h4>A list design that answers all three asks (idea, not decided)</h4><ul class="plain">${R2.design.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>
      <div class="small"><b>Next cancers by frequency:</b> ${esc(R2.nextCancers)}</div>${markHTML("doc-cancerlist", "Cancer list design", "doctors")}</div>

    <div class="card band after"><h3>Research: Cancer of Unknown Primary</h3><p class="small">${esc(R2.cup.freq)}</p>
      <div class="scroll"><table class="t"><thead><tr><th>Stage (NICE CG104)</th><th>Meaning</th></tr></thead><tbody>${R2.cup.stages.map((s) => `<tr><td><b>${esc(s[0])}</b></td><td class="small">${esc(s[1])}</td></tr>`).join("")}</tbody></table></div>
      <p class="small">${esc(R2.cup.team)}</p>
      <h4>Records a CUP Pre-Authorization could check (completeness only, never a diagnostic path)</h4><ul class="plain">${R2.cup.records.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      <p class="small"><b>For the doctors:</b> ${esc(R2.cup.conflict)} ${esc(R2.cup.india)}</p>${markHTML("doc-cup", "Cancer of Unknown Primary", "doctors")}</div>

    <div class="card"><h3>Research: the new departments</h3><dl class="kv">${R2.newDepts.map((d) => `<dt><b>${esc(d[0])}</b></dt><dd class="small">${esc(d[1])}</dd>`).join("")}</dl>${markHTML("doc-depts", "New departments", "doctors")}</div>

    <div class="card"><h3>Possible questions for the doctors (meeting 19 Oct)</h3><ol class="plain">${D.questions.map((q, i) => `<li>${esc(q)}${markHTML("doc-q" + i, "Question: " + q, "doctors")}</li>`).join("")}</ol></div>

    <div class="card"><h3>Sources</h3><ol class="plain">${R2.sources.map((s) => `<li><a href="${esc(s[1])}" target="_blank" rel="noopener">${esc(s[0])}</a></li>`).join("")}</ol></div>` : ""}
    ${generalHTML("doctors", "the doctors' inputs")}`;
  };

  R.ideas = () => {
    const order = ["before", "during", "after", "throughout"];
    return `<div class="lede"><div class="eyebrow">Ideas</div><h2>Ideas to discuss</h2>
      <p>Drawn from the research and the gaps. They are separate from what exists so they do not mix with the team's design.</p></div>
      <div class="ideas-banner">Ideas only. Nothing here is decided or built.</div>
      ${order.map((st) => { const xs = A.ideas.filter((i) => i.stage === st); if (!xs.length) return "";
        const label = stageById[st]?.label || "Throughout";
        return `<div class="card band ${st}"><h3 class="stg ${st}">${esc(label)}</h3><div class="grid two">${xs.map((i) => `<div class="item" id="it-${i.id}"><h3><span class="sid">${i.id}</span>${esc(i.title)}</h3>
          <p class="small">${esc(i.detail)}</p><div class="small muted">From: ${esc(i.from)}</div>${markHTML("idea-" + i.id, i.id + ": " + i.title, "ideas")}</div>`).join("")}</div></div>`; }).join("")}
      ${generalHTML("ideas", "the ideas")}`;
  };

  R.research = () => {
    const src = (n) => { const s = A.research.sources.find((x) => x.n === n); return s ? `<a href="${esc(s.u)}" target="_blank" rel="noopener">[${n}]</a>` : ""; };
    return `<div class="lede"><div class="eyebrow">Research</div><h2>How real Tumour Boards work</h2>
      <p>India first, then international standards, products and usability studies. Numbers come from the cited sources; things I could not verify are listed at the end.</p></div>
      <div class="card"><h3>India</h3><div class="tiles">${A.research.india.map((x) => `<div class="tile"><b>${esc(x.k)}</b><span>${esc(x.t)}</span><i>${src(x.src)}</i></div>`).join("")}</div></div>
      <div class="grid two">
        <div class="card"><h3>International standards</h3><ul class="plain">${A.research.intl.map((x) => `<li>${esc(x.t)} ${src(x.src)}</li>`).join("")}</ul></div>
        <div class="card"><h3>Where boards fail</h3><ul class="plain">${A.research.failures.map((x) => `<li>${esc(x.t)} ${src(x.src)}</li>`).join("")}</ul></div>
        <div class="card"><h3>Products and their patterns</h3><ul class="plain">${A.research.products.map((x) => `<li><b>${esc(x.name)}:</b> ${esc(x.t)}</li>`).join("")}</ul></div>
        <div class="card"><h3>Usability studies</h3><ul class="plain">${A.research.ux.map((x) => `<li>${esc(x.t)} ${src(x.src)}</li>`).join("")}</ul></div></div>
      <div class="card"><h3>Could not verify</h3><ul class="plain">${A.research.unverified.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <div class="card"><h3>Sources</h3><ol class="plain">${A.research.sources.map((s) => `<li><a href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t)}</a></li>`).join("")}</ol></div>
      ${generalHTML("research", "the research")}`;
  };

  R.glossary = () => `<div class="lede"><div class="eyebrow">Glossary and docs</div><h2>Words used here, and where things are written</h2></div>
    <div class="grid two"><div class="card"><h3>Glossary</h3><dl class="kv">${A.glossary.map(([k, v]) => `<dt><b>${esc(k)}</b></dt><dd>${esc(v)}</dd>`).join("")}</dl></div>
    <div class="card"><h3>Team documents (in the repo)</h3><ul class="plain">${A.docs.map((d) => `<li>${esc(d.t)}: <code>${esc(d.p)}</code></li>`).join("")}</ul></div></div>
    ${generalHTML("glossary", "the glossary")}`;

  R.notes = () => {
    const items = Object.entries(S.notes.items).sort((a, b) => (b[1].updated || "").localeCompare(a[1].updated || ""));
    const gen = Object.entries(S.notes.general);
    const by = (m) => items.filter(([, n]) => (n.mark || "") === m);
    const list = (xs) => xs.map(([id, n]) => `<div class="item"><h3>${esc(n.title || id)} ${n.mark ? `<span class="chip">${esc(n.mark)}</span>` : ""}</h3>
      ${n.comment ? `<p class="small">${esc(n.comment)}</p>` : ""}<div class="small muted">${esc(n.section || "")} · ${esc(n.updated || "")}</div></div>`).join("");
    return `<div class="lede"><div class="eyebrow">My notes</div><h2>Everything you marked or wrote</h2>
      <p>${S.online ? "Saved on the server in docs/ui/workflow/notes.json." : "The server is not reachable: these are kept in this browser and will be sent later."}</p></div>
      <div class="row"><button class="btn" id="copyNotes">Copy all as text</button></div>
      ${!items.length && !gen.length ? `<div class="card"><p>Nothing yet. Press Keep, Change, Discuss or Comment on any item, or write in a section's notes box.</p></div>` : ""}
      ${[["change", "Change"], ["discuss", "Discuss"], ["keep", "Keep"], ["", "Comment only"]].map(([m, l]) => { const xs = by(m); return xs.length ? `<div class="card"><h3>${l} (${xs.length})</h3><div class="grid two">${list(xs)}</div></div>` : ""; }).join("")}
      ${gen.length ? `<div class="card"><h3>Section notes</h3>${gen.map(([k, g]) => `<div class="item"><h3>${esc(k)}</h3><p class="small" style="white-space:pre-wrap">${esc(g.text)}</p><div class="small muted">${esc(g.updated || "")}</div></div>`).join("")}</div>` : ""}`;
  };

  function render() {
    $("#main").innerHTML = `<section class="view" id="sec-${S.section}">${(R[S.section] || R.overview)()}</section>`;
    document.title = "Vaidyx-TB Workflow Atlas";
  }

  /* ------------------------------------------------------------ events */
  document.addEventListener("click", async (e) => {
    const t = e.target.closest("button, a, tr.srow"); if (!t) return;
    if (t.matches(".rail a")) { e.preventDefault(); return go(t.dataset.sec); }
    const mk = t.closest(".mk");
    if (mk && t.dataset.mark) { const id = mk.dataset.mk, cur = S.notes.items[id]?.mark;
      return saveItem(id, { mark: cur === t.dataset.mark ? null : t.dataset.mark, title: mk.dataset.title, section: mk.dataset.section }); }
    if (mk && t.hasAttribute("data-cm")) { const box = mk.querySelector(".cbox"); box.hidden = !box.hidden; t.setAttribute("aria-expanded", !box.hidden); if (!box.hidden) box.querySelector("textarea").focus(); return; }
    if (mk && t.hasAttribute("data-cmcancel")) { mk.querySelector(".cbox").hidden = true; return; }
    if (mk && t.hasAttribute("data-savecm")) { const id = mk.dataset.mk; await saveItem(id, { comment: mk.querySelector("textarea").value, title: mk.dataset.title, section: mk.dataset.section }); return; }
    if (t.dataset.gsave) { const k = t.dataset.gsave, text = document.getElementById("g-" + k).value;
      if (text.trim()) S.notes.general[k] = { text, updated: "" }; else delete S.notes.general[k];
      const stamp = await post({ general: { section: k, text } }); if (stamp && S.notes.general[k]) S.notes.general[k].updated = stamp;
      t.nextElementSibling.textContent = stamp ? "saved " + stamp : "kept in this browser"; return; }
    if (t.id === "copyNotes") { const txt = [...Object.values(S.notes.items).map((n) => `[${n.mark || "comment"}] ${n.title}${n.comment ? "\n  " + n.comment : ""}`),
        ...Object.entries(S.notes.general).map(([k, g]) => `[section ${k}]\n  ${g.text}`)].join("\n\n");
      try { await navigator.clipboard.writeText(txt); toast("Copied"); } catch (err) { toast("Copy failed: select the text instead"); } return; }
    if (t.matches("tr.srow")) { S.openStep = S.openStep === t.dataset.step ? null : t.dataset.step; render(); return; }
    if (t.dataset.mxstage !== undefined) { S.mxStage = t.dataset.mxstage; return render(); }
    if (t.dataset.gapcat !== undefined) { S.gapCat = t.dataset.gapcat; return render(); }
    if (t.dataset.gapsev !== undefined) { S.gapSev = t.dataset.gapsev; return render(); }
    if (t.dataset.docstatus !== undefined) { S.docStatus = t.dataset.docstatus; return render(); }
    if (t.id === "theme") { const r = document.documentElement, dark = r.dataset.theme ? r.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      r.dataset.theme = dark ? "light" : "dark"; store.set("atlas-theme", r.dataset.theme); return; }
    if (t.dataset.step && t.dataset.go === "workflow") { S.openStep = t.dataset.step; return go("workflow", { anchor: "it-" + t.dataset.step }); }
    if (t.dataset.role !== undefined && !t.dataset.go) { setViewAs(t.dataset.role); return; }
    if (t.dataset.go) { e.preventDefault(); return go(t.dataset.go, { role: t.dataset.role, anchor: t.dataset.anchor }); }
  });
  document.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches("tr.srow")) { e.preventDefault(); e.target.click(); }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && e.target.matches(".cbox textarea")) e.target.closest(".mk").querySelector("[data-savecm]").click();
  });
  document.addEventListener("change", (e) => {
    if (e.target.id === "viewas") setViewAs(e.target.value);
    if (e.target.id === "showMissing") { S.showMissing = e.target.checked; store.set("atlas-missing", S.showMissing); render(); }
    if (e.target.id === "gapMine") { S.gapMine = e.target.checked; render(); }
  });
  document.addEventListener("input", (e) => {
    if (e.target.id === "gapText") { S.gapText = e.target.value; clearTimeout(S.gt); S.gt = setTimeout(() => { render(); const i = $("#gapText"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }, 250); }
  });
  window.addEventListener("hashchange", () => { const h = location.hash.slice(1); if (R[h] && h !== S.section) go(h); });

  /* ------------------------------------------------------------ boot */
  const th = store.get("atlas-theme", ""); if (th) document.documentElement.dataset.theme = th;
  $("#viewas").innerHTML = `<option value="">All roles</option>` + [...new Set(A.roles.map((r) => r.group))].map((g) =>
    `<optgroup label="${esc(g)}">${A.roles.filter((r) => r.group === g).map((r) => `<option value="${r.id}">${esc(r.name)}</option>`).join("")}</optgroup>`).join("");
  $("#viewas").value = roleById[S.viewAs] ? S.viewAs : "";
  const h = location.hash.slice(1); if (R[h]) S.section = h;
  rail(); render();
  loadNotes().then(() => { rail(); if (S.section === "notes") render(); });
})();
