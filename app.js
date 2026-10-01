const TEAM = [
  { name: "Raivis Vīlips", role: "Sales Manager", phone: "+371 25446662", email: "raivis.vilips@trimentractors.com" },
  { name: "Mārtiņš Marauska", role: "Sales Manager", phone: "+371 28666822", email: "martins.marauska@trimentractors.com" },
  { name: "Mareks Zeiliņš", role: "Work Tool Manager", phone: "+371 25608555", email: "mareks.zeilins@trimentractors.com" },
  { name: "Gints Timoško", role: "Director", phone: "+371 26688444", email: "gints.timosko@trimentractors.com" },
];
const WORK_TOOLS = new Set(["Excavation buckets", "Ditch cleaning buckets", "Wheel loader buckets", "Quick couplers",
  "Shears, Hammers, Grapples", "Miscellaneous work tools"]);
const PAGE = 24;

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const priceNum = (p) => Number(String(p).replace(/[^\d]/g, "")) || 0;
const fmt = (n) => n.toLocaleString("en-US");
// Listing photos come in size variants: /upload/catalog/5<name> (large), 3<name> (medium), <name> (thumb)
const medium = (url) => url.replace("/upload/catalog/5", "/upload/catalog/3");
const thumb = (url) => url.replace("/upload/catalog/5", "/upload/catalog/");
const tel = (p) => "tel:" + p.replace(/\s/g, "");
const spec = (it, key) => (it.specs.find(([k]) => k === key) || [])[1];
const realYear = (it) => (/^(19[5-9]\d|20[0-4]\d)$/.test(it.year) && !WORK_TOOLS.has(it.category) ? it.year : "");
const title = (it) => [it.make === "Other" ? "" : it.make, it.model].filter(Boolean).join(" ") || it.category;

let DATA, items, newestRank, shown = PAGE;
const state = { q: "", cat: "", make: "", sort: "new", view: "grid" };

fetch("data/stock.json")
  .then((r) => r.json())
  .then((d) => {
    DATA = d;
    items = d.items;
    newestRank = new Map(d.newest.map((id, i) => [id, i]));
    init();
  })
  .catch(() => ($("#grid").innerHTML = '<p class="empty">Stock list could not be loaded.</p>'));

function init() {
  $("#yr").textContent = new Date().getFullYear();
  const counts = items.reduce((m, it) => m.set(it.category, (m.get(it.category) || 0) + 1), new Map());
  const machines = items.filter((it) => !WORK_TOOLS.has(it.category)).length;

  $("#stats").innerHTML = [
    [items.length, "listings in stock"],
    [machines, "machines & vehicles"],
    [items.length - machines, "work tools & attachments"],
    [counts.size, "categories"],
  ].map(([n, l]) => `<div><dt>${n}</dt><dd>${l}</dd></div>`).join("");

  $("#catGrid").innerHTML = DATA.categories
    .filter((c) => counts.has(c.name))
    .map((c) => `<button class="cat" data-cat="${esc(c.name)}"><img loading="lazy" src="${esc(c.image)}" alt="" /><span>${esc(c.name)}</span><small>${counts.get(c.name)} in stock</small></button>`)
    .join("");
  $("#catGrid").addEventListener("click", (e) => {
    const b = e.target.closest(".cat");
    if (!b) return;
    state.cat = $("#fCat").value = b.dataset.cat;
    refresh();
    $("#stock").scrollIntoView();
  });

  const newest = DATA.newest.map((id) => items.find((it) => it.id === id)).filter(Boolean)
    .filter((it) => !WORK_TOOLS.has(it.category)).slice(0, 10);
  $("#newRail").innerHTML = newest.map(card).join("");

  const opts = (vals) => vals.map((v) => `<option>${esc(v)}</option>`).join("");
  $("#fCat").insertAdjacentHTML("beforeend", opts([...counts.keys()]));
  $("#fMake").insertAdjacentHTML("beforeend", opts([...new Set(items.map((i) => i.make))].sort()));

  $("#q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); refresh(); });
  $("#fCat").addEventListener("change", (e) => { state.cat = e.target.value; refresh(); });
  $("#fMake").addEventListener("change", (e) => { state.make = e.target.value; refresh(); });
  $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; refresh(); });
  document.querySelectorAll(".view-toggle button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".view-toggle button").forEach((x) => x.classList.toggle("active", x === b));
    state.view = b.dataset.view;
    $("#grid").classList.toggle("list", state.view === "list");
  }));
  $("#more").addEventListener("click", () => { shown += PAGE; render(); });

  document.addEventListener("click", (e) => {
    const c = e.target.closest(".card");
    if (c) location.hash = "id=" + c.dataset.id;
  });

  $("#team").innerHTML = TEAM.map((m) => `
    <div class="member">
      <div class="avatar">${esc(m.name.split(" ").map((w) => w[0]).join(""))}</div>
      <h3>${esc(m.name)}</h3><p class="role">${esc(m.role)}</p>
      <a href="${tel(m.phone)}">${esc(m.phone)}</a>
      <a href="mailto:${esc(m.email)}">${esc(m.email)}</a>
    </div>`).join("");

  const menu = $("#menuBtn"), nav = $("#nav");
  menu.addEventListener("click", () => menu.setAttribute("aria-expanded", nav.classList.toggle("open")));
  nav.addEventListener("click", (e) => { if (e.target.closest("a")) { nav.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); } });

  setupDetail();
  refresh();
}

function card(it) {
  const year = realYear(it);
  const stockNo = spec(it, "Stock number");
  const meta = [it.category, year, stockNo && "Stock " + stockNo].filter(Boolean).join(" · ");
  const img = it.images[0] ? `<img loading="lazy" src="${esc(medium(it.images[0]))}" alt="${esc(title(it))}" />` : "";
  return `<button class="card" data-id="${it.id}">
    <div class="ph">${img}<span class="badge">${esc(it.category)}</span>${it.images.length > 1 ? `<span class="pics">${it.images.length} photos</span>` : ""}</div>
    <div class="body"><h3>${esc(title(it))}</h3><div class="meta">${esc(meta)}</div>
    <div class="price">${it.price ? esc(it.price.replace(" EUR", "")) + " € <small>+ VAT</small>" : "Price on request"}</div></div>
  </button>`;
}

function filtered() {
  const { q, cat, make, sort } = state;
  const list = items.filter((it) =>
    (!cat || it.category === cat) &&
    (!make || it.make === make) &&
    (!q || [it.make, it.model, it.category, it.year, it.extra, ...it.specs.map((s) => s[1])].join(" ").toLowerCase().includes(q)));
  const by = {
    new: (a, b) => (newestRank.get(a.id) ?? 1e6) - (newestRank.get(b.id) ?? 1e6) || b.id - a.id,
    priceAsc: (a, b) => priceNum(a.price) - priceNum(b.price),
    priceDesc: (a, b) => priceNum(b.price) - priceNum(a.price),
    yearDesc: (a, b) => (Number(realYear(b)) || 0) - (Number(realYear(a)) || 0),
    make: (a, b) => a.make.localeCompare(b.make) || a.model.localeCompare(b.model),
  }[sort];
  return list.sort(by);
}

function refresh() { shown = PAGE; render(); }

function render() {
  const list = filtered();
  $("#resultCount").textContent = `${list.length} of ${items.length} listings${state.cat ? " in " + state.cat : ""}`;
  $("#grid").innerHTML = list.length ? list.slice(0, shown).map(card).join("") : '<p class="empty">No listings match your search.</p>';
  $("#more").hidden = list.length <= shown;
}

function setupDetail() {
  const dlg = $("#detail");
  let cur, idx = 0;

  const show = (i) => {
    idx = (i + cur.images.length) % cur.images.length;
    $("#dImg").src = cur.images[idx];
    $("#dCount").textContent = `${idx + 1} / ${cur.images.length}`;
    $("#dThumbs").querySelectorAll("button").forEach((b, j) => b.classList.toggle("active", j === idx));
    $("#dThumbs").children[idx]?.scrollIntoView({ block: "nearest", inline: "nearest" });
  };

  const open = (id) => {
    cur = items.find((it) => it.id === id);
    if (!cur) return;
    $("#dCat").textContent = cur.category;
    $("#dTitle").textContent = title(cur);
    const gross = spec(cur, "Price EUR Brutto (VAT 21%)");
    $("#dPrice").innerHTML = cur.price
      ? `${esc(cur.price.replace(" EUR", ""))} € <small>net${gross ? ` · ${esc(gross)} € incl. 21% VAT` : ""}</small>`
      : "Price on request";
    $("#dSpecs").innerHTML = cur.specs.filter(([k]) => !k.startsWith("Price"))
      .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("");
    $("#dExtra").textContent = cur.extra;
    const c = cur.contact || TEAM[0];
    const subject = encodeURIComponent(`Enquiry: ${title(cur)} (ID ${cur.id})`);
    $("#dContact").innerHTML = `<strong>${esc(c.name)}</strong>
      <a href="${tel(c.phone)}">${esc(c.phone)}</a><a href="mailto:${esc(c.email)}">${esc(c.email)}</a>
      <div class="row"><a class="btn btn-sm" href="mailto:${esc(c.email)}?subject=${subject}">Send enquiry</a><a class="btn btn-sm btn-ghost" href="${tel(c.phone)}">Call</a></div>`;
    const many = cur.images.length > 1;
    $("#dPrev").hidden = $("#dNext").hidden = $("#dCount").hidden = !many;
    $("#dThumbs").innerHTML = many ? cur.images.map((u, j) => `<button data-i="${j}" aria-label="Photo ${j + 1}"><img loading="lazy" src="${esc(thumb(u))}" alt="" /></button>`).join("") : "";
    $("#dImg").alt = title(cur);
    if (cur.images.length) show(0); else $("#dImg").removeAttribute("src");
    if (!dlg.open) dlg.showModal();
  };

  const fromHash = () => {
    const m = location.hash.match(/^#id=(\d+)$/);
    if (m) open(Number(m[1]));
    else if (dlg.open) dlg.close();
  };

  $("#dPrev").addEventListener("click", () => show(idx - 1));
  $("#dNext").addEventListener("click", () => show(idx + 1));
  $("#dThumbs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) show(Number(b.dataset.i)); });
  $("#dClose").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") show(idx - 1);
    if (e.key === "ArrowRight") show(idx + 1);
  });
  dlg.addEventListener("close", () => {
    if (location.hash.startsWith("#id=")) history.replaceState(null, "", location.pathname + location.search);
  });
  window.addEventListener("hashchange", fromHash);
  fromHash();
}
