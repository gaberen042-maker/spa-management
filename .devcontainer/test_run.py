"""SPA Hockey Management Dashboard (single file).

Run with:  streamlit run spa_hockey_dashboard.py

* Drag players between lines / pairs on the Roster tab (custom component, written next to this file on first run).
* Click a player to edit their details, stats and private notes (a 📝 marks players who have notes).
* Everything saves automatically to  spa_data/roster.json  (next to this file).
* Printable Line Sheet matches the SPA lineup card (stats and notes are never printed).
"""
import base64
import hashlib
import io
import json
import os
import shutil
import tempfile
import uuid
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="SPA Hockey Dashboard", page_icon="🏒", layout="wide")

BASE_DIR = Path(__file__).resolve().parent


def _writable_dir(path):
    """Use `path` if we can write there, otherwise fall back to a temp folder."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / ("spa_hockey_" + path.name)
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


DATA_DIR = _writable_dir(BASE_DIR / "spa_data")
DATA_FILE = DATA_DIR / "roster.json"
COMP_DIR = _writable_dir(BASE_DIR / "spa_board_component")
LOGO_FILE = BASE_DIR / "spa_logo.png"  # optional: drop your logo here, or upload it in the Team tab

# ---------------------------------------------------------------------------
# Drag-and-drop board (plain HTML/JS component, no extra packages needed)
# ---------------------------------------------------------------------------
BOARD_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: transparent; font-family: Arial, Helvetica, sans-serif; color: #111; }
#root { padding: 2px; }
.paper { background: #fff; border: 1px solid #d0d0d0; border-radius: 8px; padding: 14px 18px 18px; max-width: 980px; margin: 0 auto; }
.logo { text-align: center; margin-bottom: 4px; }
.logo img { max-height: 90px; max-width: 100%; }
.logotext { font-weight: 900; font-size: 46px; letter-spacing: 3px; color: #C92A2A; text-shadow: 1px 1px 0 #111; }
.sec { text-align: center; font-weight: 700; font-size: 15px; letter-spacing: .6px; margin: 12px 0 8px; }
.tip { text-align: center; font-size: 11px; color: #777; margin: 0 0 6px; }
.rowwrap { display: grid; grid-template-columns: 68px minmax(0, 1fr); gap: 6px; margin-bottom: 6px; align-items: stretch; }
.rowlabel { font-size: 9.5px; font-weight: 700; color: #888; text-transform: uppercase; display: flex; align-items: center; }
.zone { display: grid; gap: 6px; min-height: 64px; padding: 4px; border: 1px dashed #cfcfcf; border-radius: 6px; align-content: start; transition: background .1s, border-color .1s; }
.zone.c3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.zone.c2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.zone.c1 { grid-template-columns: minmax(0, 1fr); }
.zone.pool { background: #fafafa; border-color: #b9b9b9; }
.zone.hot { border-color: #C92A2A; background: #fff3f3; }
.zone:empty::before { content: "drop here"; grid-column: 1 / -1; color: #bbb; font-size: 11px; padding: 6px; }
.card { position: relative; display: flex; gap: 8px; align-items: flex-start; padding: 6px 22px 6px 6px; border-radius: 6px; border: 1px solid transparent; background: #fff; cursor: grab; user-select: none; -webkit-user-select: none; min-width: 0; }
.card:hover { border-color: #d9d9d9; background: #fafafa; }
.card.sel { border-color: #C92A2A; background: #fff5f5; }
.card.dragging { display: none; }
.no { font-size: 18px; min-width: 28px; text-align: right; line-height: 1.1; }
.tx { min-width: 0; }
.nm { font-weight: 700; font-size: 12px; text-transform: uppercase; letter-spacing: .2px; overflow-wrap: anywhere; }
.noteico { font-size: 11px; margin-left: 4px; text-transform: none; vertical-align: 1px; }
.sm { font-size: 9.5px; color: #222; margin-top: 3px; }
.tag { font-size: 8.5px; font-weight: 700; color: #C92A2A; margin-top: 3px; letter-spacing: .5px; }
.grip { position: absolute; right: 3px; top: 3px; font-size: 13px; line-height: 1; color: #bbb; padding: 3px 3px; touch-action: none; cursor: grab; }
.ph { border: 2px dashed #C92A2A; border-radius: 6px; background: #fff0f0; min-height: 50px; }
.ghost { position: fixed; z-index: 9999; pointer-events: none; opacity: .92; box-shadow: 0 8px 22px rgba(0,0,0,.28); background: #fff; border: 1px solid #C92A2A; border-radius: 6px; }
.bottom { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 18px; }
.coaches { display: flex; justify-content: center; gap: 44px; flex-wrap: wrap; margin-top: 18px; padding-top: 12px; border-top: 1px solid #eee; text-align: center; }
.cn { font-weight: 700; font-size: 11px; text-transform: uppercase; }
.ct { font-size: 8.5px; text-transform: uppercase; margin: 5px 0 6px; }
.cc { font-size: 8.5px; }
@media (max-width: 640px) { .bottom { grid-template-columns: 1fr; } .zone.c3 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
</head>
<body>
<div id="root"></div>
<script>
(function () {
  var A = null, layout = {}, selected = null, drag = null, lastSig = null, lastH = 0;
  var root = document.getElementById("root");

  function send(type, extra) {
    var m = { isStreamlitMessage: true, type: type };
    for (var k in extra) { m[k] = extra[k]; }
    window.parent.postMessage(m, "*");
  }
  function setHeight() {
    var h = Math.ceil(root.getBoundingClientRect().height) + 6;
    if (h !== lastH) { lastH = h; send("streamlit:setFrameHeight", { height: h }); }
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function clone(o) { return JSON.parse(JSON.stringify(o || {})); }
  function emit(kind, id) {
    send("streamlit:setComponentValue", {
      value: { event: String(Date.now()) + Math.random().toString(36).slice(2, 8), kind: kind, id: id, layout: layout, selected: selected },
      dataType: "json"
    });
  }

  function cardHTML(id, idx, zone) {
    var p = A.players[id];
    if (!p) return "";
    var tag = "";
    if (zone.section === "G" && idx === 0) tag = '<div class="tag">STARTER</div>';
    if (zone.section === "G" && idx === 1) tag = '<div class="tag">BACKUP</div>';
    var hand = (zone.section === "G" ? "Catch: " : "Shot ") + esc(p.shot || "");
    var note = p.note ? '<span class="noteico" title="Has notes">&#128221;</span>' : "";
    return '<div class="card' + (id === selected ? " sel" : "") + '" data-id="' + esc(id) + '" data-group="' + esc(p.pos) + '">' +
      '<div class="no">' + esc(p.no) + '</div>' +
      '<div class="tx"><div class="nm">' + esc(p.name) + note + '</div>' +
      '<div class="sm">H: ' + esc(p.h) + ' W: ' + esc(p.w) + ' ' + hand + '</div>' +
      '<div class="sm">' + esc(p.hometown) + (p.year ? " " + esc(p.year) : "") + '</div>' + tag + '</div>' +
      '<div class="grip" title="Drag">&#8942;&#8942;</div></div>';
  }
  function zoneHTML(z) {
    var ids = layout[z.id] || [];
    var cols = z.section === "F" ? "c3" : (z.section === "D" ? "c2" : "c1");
    var inner = ids.map(function (id, i) { return cardHTML(id, i, z); }).join("");
    var zone = '<div class="zone ' + cols + (z.pool ? " pool" : "") + '" data-zone="' + esc(z.id) + '" data-group="' + esc(z.group) + '">' + inner + '</div>';
    if (z.section === "G") return zone;
    return '<div class="rowwrap"><div class="rowlabel">' + esc(z.label) + '</div>' + zone + '</div>';
  }
  function section(name) {
    return A.zones.filter(function (z) { return z.section === name; }).map(zoneHTML).join("");
  }
  function logoHTML() {
    return '<div class="logo">' + (A.logo ? '<img src="' + esc(A.logo) + '" alt="logo">' : '<span class="logotext">SPA</span>') + '</div>';
  }
  function coachesHTML() {
    var cs = A.coaches || [];
    if (!cs.length) return "";
    return '<div class="coaches">' + cs.map(function (c) {
      return '<div><div class="cn">' + esc(c.name) + '</div><div class="ct">' + esc(c.title) + '</div>' +
        (c.phone ? '<div class="cc">' + esc(c.phone) + '</div>' : "") +
        (c.email ? '<div class="cc">' + esc(c.email) + '</div>' : "") + '</div>';
    }).join("") + '</div>';
  }
  function render() {
    if (!A) return;
    root.innerHTML = '<div class="paper">' + logoHTML() +
      '<div class="tip">Drag a player (or the &#8942;&#8942; grip on touch screens) to another line. Click a player to edit details and notes below. &#128221; = has notes.</div>' +
      '<div class="sec">FORWARDS</div>' + section("F") +
      '<div class="bottom"><div><div class="sec">DEFENSEMEN</div>' + section("D") + '</div>' +
      '<div><div class="sec">GOALTENDERS</div>' + section("G") + '</div></div>' + coachesHTML() + '</div>';
    setHeight();
  }

  // ---------- drag and drop (pointer events: mouse, pen, touch via grip) ----------
  function zoneAt(x, y) {
    var el = document.elementFromPoint(x, y);
    return el && el.closest ? el.closest(".zone") : null;
  }
  function removePH() { var p = document.querySelector(".ph"); if (p && p.parentNode) p.parentNode.removeChild(p); }
  function indexIn(zone, x, y) {
    var cards = Array.prototype.slice.call(zone.querySelectorAll(".card:not(.dragging)"));
    for (var i = 0; i < cards.length; i++) {
      var r = cards[i].getBoundingClientRect();
      if (y < r.top || (y <= r.bottom && x < r.left + r.width / 2)) return i;
    }
    return cards.length;
  }
  function updateTarget(x, y) {
    removePH();
    var hot = document.querySelectorAll(".zone.hot");
    for (var i = 0; i < hot.length; i++) hot[i].classList.remove("hot");
    var zone = zoneAt(x, y);
    if (!zone || zone.getAttribute("data-group") !== drag.group) { drag.target = null; return; }
    var idx = indexIn(zone, x, y);
    var cards = zone.querySelectorAll(".card:not(.dragging)");
    var ph = document.createElement("div");
    ph.className = "ph";
    if (idx < cards.length) zone.insertBefore(ph, cards[idx]); else zone.appendChild(ph);
    zone.classList.add("hot");
    drag.target = zone.getAttribute("data-zone");
    drag.idx = idx;
  }
  function cleanup() {
    if (drag && drag.ghost && drag.ghost.parentNode) drag.ghost.parentNode.removeChild(drag.ghost);
    removePH();
    var hot = document.querySelectorAll(".zone.hot");
    for (var i = 0; i < hot.length; i++) hot[i].classList.remove("hot");
    if (drag && drag.card) drag.card.classList.remove("dragging");
    drag = null;
  }
  function onDown(e) {
    var card = e.target.closest ? e.target.closest(".card") : null;
    if (!card) return;
    if (e.pointerType === "touch" && !(e.target.closest && e.target.closest(".grip"))) return;
    if (e.button > 0) return;
    var r = card.getBoundingClientRect();
    drag = { id: card.getAttribute("data-id"), group: card.getAttribute("data-group"), card: card,
             x0: e.clientX, y0: e.clientY, offX: e.clientX - r.left, offY: e.clientY - r.top,
             w: r.width, active: false, ghost: null, target: null, idx: 0 };
    e.preventDefault();
  }
  function onMove(e) {
    if (!drag) return;
    if (!drag.active) {
      if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 5) return;
      drag.active = true;
      var g = drag.card.cloneNode(true);
      g.className = "card ghost";
      g.style.width = drag.w + "px";
      document.body.appendChild(g);
      drag.ghost = g;
      drag.card.classList.add("dragging");
    }
    drag.ghost.style.left = (e.clientX - drag.offX) + "px";
    drag.ghost.style.top = (e.clientY - drag.offY) + "px";
    updateTarget(e.clientX, e.clientY);
    e.preventDefault();
  }
  function onUp(e) {
    if (!drag) return;
    var d = drag;
    if (!d.active) {                       // plain click: select this player
      cleanup();
      selected = d.id;
      render();
      emit("select", d.id);
      return;
    }
    var target = d.target, idx = d.idx;
    cleanup();
    if (target) {
      for (var z in layout) {
        layout[z] = (layout[z] || []).filter(function (i) { return i !== d.id; });
      }
      layout[target] = layout[target] || [];
      layout[target].splice(Math.min(idx, layout[target].length), 0, d.id);
      selected = d.id;
      render();
      emit("move", d.id);
    }
  }
  document.addEventListener("pointerdown", onDown);
  window.addEventListener("pointermove", onMove, { passive: false });
  window.addEventListener("pointerup", onUp);
  window.addEventListener("pointercancel", function () { if (drag) cleanup(); });
  document.documentElement.addEventListener("pointerleave", function () { if (drag && drag.active) cleanup(); });

  // ---------- Streamlit component protocol ----------
  window.addEventListener("message", function (ev) {
    var d = ev.data;
    if (!d || d.type !== "streamlit:render") return;
    var args = d.args || {};
    var sig = JSON.stringify(args);
    if (sig === lastSig) return;           // same data as last time: keep local (possibly newer) state
    lastSig = sig;
    A = args;
    layout = clone(args.layout);
    selected = args.selected || null;
    if (!drag) render();
  });
  if (window.ResizeObserver) new ResizeObserver(setHeight).observe(root);
  send("streamlit:componentReady", { apiVersion: 1 });
})();
</script>
</body>
</html>
"""

try:
    _index = COMP_DIR / "index.html"
    if not _index.exists() or _index.read_text(encoding="utf-8") != BOARD_HTML:
        _index.write_text(BOARD_HTML, encoding="utf-8")
except OSError as _exc:
    st.error(f"Could not write the drag-and-drop component: {_exc}")

lineup_board = components.declare_component("spa_lineup_board", path=str(COMP_DIR))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ZONES = [
    {"id": "F1", "label": "Line 1", "group": "F", "section": "F"},
    {"id": "F2", "label": "Line 2", "group": "F", "section": "F"},
    {"id": "F3", "label": "Line 3", "group": "F", "section": "F"},
    {"id": "F4", "label": "Line 4", "group": "F", "section": "F"},
    {"id": "FP", "label": "Scratches", "group": "F", "section": "F", "pool": True},
    {"id": "D1", "label": "Pair 1", "group": "D", "section": "D"},
    {"id": "D2", "label": "Pair 2", "group": "D", "section": "D"},
    {"id": "D3", "label": "Pair 3", "group": "D", "section": "D"},
    {"id": "DP", "label": "Scratches", "group": "D", "section": "D", "pool": True},
    {"id": "G", "label": "Goalies", "group": "G", "section": "G"},
]
ZONE_GROUP = {z["id"]: z["group"] for z in ZONES}
POOL_FOR = {"F": "FP", "D": "DP", "G": "G"}
POS_LABELS = {"Forward": "F", "Defenseman": "D", "Goaltender": "G"}
POS_NAMES = {"F": "Forward", "D": "Defenseman", "G": "Goaltender"}
POS_ORDER = {"F": 0, "D": 1, "G": 2}

PP_FORMATIONS = ["1-3-1", "Overload"]
PK_FORMATIONS = ["Box", "Diamond", "Coat Hanger"]
UNITS = [("PP1", PP_FORMATIONS), ("PP2", PP_FORMATIONS), ("PK1", PK_FORMATIONS), ("PK2", PK_FORMATIONS)]
# Each formation is rows of cells; None = empty column.  (slot key, label)
FORMATIONS = {
    "Box": [[("b1", "Top Left Fwd"), ("b2", "Top Right Fwd")],
            [("b3", "Bottom Left Def"), ("b4", "Bottom Right Def")]],
    "Diamond": [[None, ("d1", "Top Point"), None],
                [("d2", "Left Wing"), None, ("d3", "Right Wing")],
                [None, ("d4", "Safety Depth"), None]],
    "Coat Hanger": [[None, ("ch1", "Top Apex"), None],
                    [None, ("ch2", "Mid Stack"), None],
                    [("ch3", "Base Left"), ("ch4", "Base Right"), None]],
    "1-3-1": [[None, ("t", "Point (1)"), None],
              [("m1", "Left Wing (3)"), ("m2", "Slot Man (3)"), ("m3", "Right Wing (3)")],
              [None, ("b", "Net Front (1)"), None]],
    "Overload": [[("ov1", "Top Left"), None, ("ov2", "Top Right")],
                 [None, ("ov3", "Center Slot"), None],
                 [("ov4", "Low Left"), None, ("ov5", "Low Right")]],
}

# (id, pos, no, name, height, weight, shot/catch, hometown, birth year, starting zone)
DEFAULT_ROSTER = [
    ("f21", "F", 21, "Vojtech Svoboda", "6'2", "200", "L", "Plzen, CZE", 2009, "F1"),
    ("f18", "F", 18, "Shawn Cronin", "6'0", "187", "R", "Jacksonville, FL", 2008, "F1"),
    ("f14", "F", 14, "Kolton Mussman", "5'7", "160", "R", "Kankakee, IL", 2009, "F1"),
    ("f19", "F", 19, "Coulter Bower", "6'2", "175", "L", "McKinney, TX", 2008, "F2"),
    ("f44", "F", 44, "Ayden Giardina", "5'10", "175", "L", "Waltham, MA", 2009, "F2"),
    ("f56", "F", 56, "Eddie Sweenor", "5'10", "170", "L", "Plattsburgh, NY", 2009, "F2"),
    ("f10", "F", 10, "Ronin Fogarty", "5'7", "160", "L", "Baltimore, MD", 2008, "F3"),
    ("f8", "F", 8, "Braden Gunderson", "5'10", "155", "L", "Littleton, CO", 2009, "F3"),
    ("d9", "D", 9, "Kris Brosseau", "5'9", "155", "R", "Drummondville, QC", 2009, "D1"),
    ("d4", "D", 4, "Carter White", "6'0", "165", "R", "Erie, PA", 2009, "D1"),
    ("d78", "D", 78, "Gabriel Vezina", "6'0", "190", "R", "Coral Springs, FL", 2009, "D2"),
    ("d2", "D", 2, "Jeremy Caldwell", "5'11", "195", "R", "Pittsburgh, PA", 2008, "D2"),
    ("d34", "D", 34, "Lief Musclow", "6'4", "205", "L", "Jackson, WY", 2009, "D3"),
    ("g1", "G", 1, "Collin Dyer", "6'3", "185", "L", "South Hampton, NH", 2009, "G"),
    ("g38", "G", 38, "Nikodem Piask", "6'0", "175", "L", "Gdansk, PO", 2009, "G"),
]
DEFAULT_COACHES = [
    ("c1", "Anthony Matarazzo", "Head Coach", "862-432-5687", "coachmazzo@gmail.com"),
    ("c2", "Brandon Golub", "Assistant Coach", "732-309-4783", ""),
    ("c3", "John DeGregorio", "Assistant Coach", "", ""),
]


# ---------------------------------------------------------------------------
# Data layer: clean / load / save
# ---------------------------------------------------------------------------
def to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def new_id():
    return uuid.uuid4().hex[:8]


def make_player(src):
    """Build a complete, type-safe player record from any partial dict."""
    pos = src.get("pos") if src.get("pos") in ("F", "D", "G") else "F"
    shot = "R" if str(src.get("shot", "L")).strip().upper().startswith("R") else "L"
    return {
        "id": str(src.get("id") or new_id()), "pos": pos,
        "no": max(0, to_int(src.get("no"))),
        "name": str(src.get("name") or "").strip() or "Unnamed",
        "h": str(src.get("h") or "").strip(), "w": str(src.get("w") or "").strip(),
        "shot": shot, "hometown": str(src.get("hometown") or "").strip(),
        "year": max(0, to_int(src.get("year"))),
        "g": max(0, to_int(src.get("g"))), "a": max(0, to_int(src.get("a"))), "pm": to_int(src.get("pm")),
        "ga": max(0, to_int(src.get("ga"))),
        "sv": min(1.0, max(0.0, to_float(src.get("sv"), 0.0))),
        "wins": max(0, to_int(src.get("wins"))), "losses": max(0, to_int(src.get("losses"))),
        "notes": str(src.get("notes") or "").rstrip(),
    }


def has_note(p):
    return bool(str(p.get("notes") or "").strip())


def make_coach(src):
    return {"id": str(src.get("id") or new_id()), "name": str(src.get("name") or "").strip(),
            "title": str(src.get("title") or "").strip(), "phone": str(src.get("phone") or "").strip(),
            "email": str(src.get("email") or "").strip()}


def normalize_layout(d):
    """Every player appears exactly once, in a zone that matches their position."""
    pmap = {p["id"]: p for p in d["players"]}
    layout = {z["id"]: [] for z in ZONES}
    seen = set()
    for zid, ids in (d.get("layout") or {}).items():
        if zid not in layout or not isinstance(ids, list):
            continue
        for pid in ids:
            p = pmap.get(pid)
            if p is not None and pid not in seen and p["pos"] == ZONE_GROUP[zid]:
                layout[zid].append(pid)
                seen.add(pid)
    for p in d["players"]:
        if p["id"] not in seen:
            layout[POOL_FOR[p["pos"]]].append(p["id"])
    d["layout"] = layout


def default_data():
    players, layout = [], {z["id"]: [] for z in ZONES}
    for pid, pos, no, name, h, w, shot, town, year, zone in DEFAULT_ROSTER:
        players.append(make_player({"id": pid, "pos": pos, "no": no, "name": name, "h": h, "w": w,
                                    "shot": shot, "hometown": town, "year": year,
                                    "sv": 0.910 if pid == "g1" else (0.905 if pid == "g38" else 0.0)}))
        layout[zone].append(pid)
    coaches = [make_coach({"id": c[0], "name": c[1], "title": c[2], "phone": c[3], "email": c[4]})
               for c in DEFAULT_COACHES]
    return {"version": 2, "players": players, "layout": layout, "coaches": coaches,
            "special": {"types": {}, "slots": {}}, "logo": ""}


def clean_data(raw):
    """Accepts anything json-ish (older saves, hand-edited files) and returns valid data."""
    if not isinstance(raw, dict):
        raise ValueError("not a roster file")
    players, seen = [], set()
    for item in raw.get("players") or []:
        if isinstance(item, dict):
            p = make_player(item)
            while p["id"] in seen:
                p["id"] = new_id()
            seen.add(p["id"])
            players.append(p)
    coaches = [make_coach(c) for c in (raw.get("coaches") or []) if isinstance(c, dict)]
    special = raw.get("special") if isinstance(raw.get("special"), dict) else {}
    d = {"version": 2, "players": players, "layout": raw.get("layout") or {}, "coaches": coaches,
         "special": {"types": dict(special.get("types") or {}), "slots": dict(special.get("slots") or {})},
         "logo": raw.get("logo") if isinstance(raw.get("logo"), str) else ""}
    normalize_layout(d)
    return d


def load_data():
    if DATA_FILE.exists():
        try:
            return clean_data(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            try:
                shutil.copy(DATA_FILE, DATA_FILE.with_suffix(".broken.json"))
            except OSError:
                pass
            st.session_state["load_warning"] = (
                f"Your saved file could not be read ({exc}). A copy was kept as roster.broken.json "
                "and the sample roster was loaded.")
    return default_data()


def save_data(d):
    try:
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        if DATA_FILE.exists():
            shutil.copy(DATA_FILE, DATA_FILE.with_suffix(".bak"))
        os.replace(tmp, DATA_FILE)
        st.session_state.pop("save_error", None)
        return True
    except OSError as exc:
        st.session_state["save_error"] = str(exc)
        return False


def persist():
    """Write to disk, but only when something actually changed."""
    blob = json.dumps(data, sort_keys=True)
    if blob != st.session_state.get("saved_blob"):
        if save_data(data):
            st.session_state["saved_blob"] = blob


def rerun():
    (getattr(st, "rerun", None) or st.experimental_rerun)()


def seed(key, value):
    """Give a widget its starting value once (the key then owns the value)."""
    if key not in st.session_state:
        st.session_state[key] = value


def clear_widget_state(prefix):
    """Queue widget keys for removal; they are deleted at the start of the next run (before any widget exists)."""
    st.session_state.setdefault("_purge", []).append(prefix)


def run_purge():
    for prefix in st.session_state.pop("_purge", []):
        for key in [k for k in list(st.session_state.keys()) if isinstance(k, str) and k.startswith(prefix)]:
            del st.session_state[key]


# Session start: load saved data (after the purge helper exists, before any widget is created)
if "data" not in st.session_state:
    st.session_state["data"] = load_data()
    st.session_state["saved_blob"] = (
        json.dumps(st.session_state["data"], sort_keys=True) if DATA_FILE.exists() else "")
run_purge()
data = st.session_state["data"]


def player_map():
    return {p["id"]: p for p in data["players"]}


def board_sig():
    """Fingerprint of everything the drag-and-drop board displays. The note TEXT is left out on
    purpose (the board only shows whether a player has a note), so typing notes never redraws it."""
    players = []
    for p in data["players"]:
        q = {k: v for k, v in p.items() if k != "notes"}
        q["has_note"] = has_note(p)
        players.append(q)
    blob = json.dumps([players, data["layout"], data["coaches"], data["logo"],
                       st.session_state.get("selected")], sort_keys=True)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


def get_logo():
    if data["logo"]:
        return data["logo"]
    try:
        if LOGO_FILE.exists():
            return "data:image/png;base64," + base64.b64encode(LOGO_FILE.read_bytes()).decode("ascii")
    except OSError:
        pass
    return ""


def logo_from_upload(raw_bytes):
    """Shrink an uploaded image so it stays small in the save file."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw_bytes))
        img.thumbnail((900, 300))
        out = io.BytesIO()
        img.convert("RGBA").save(out, format="PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return "data:image/png;base64," + base64.b64encode(raw_bytes).decode("ascii")


def delete_player(pid):
    data["players"] = [p for p in data["players"] if p["id"] != pid]
    for zid in data["layout"]:
        data["layout"][zid] = [i for i in data["layout"][zid] if i != pid]
    if st.session_state.get("selected") == pid:
        st.session_state["selected"] = None
    clear_widget_state(f"edit_{pid}_")


def apply_move(new_layout):
    """Accept a layout from the drag-and-drop board only if it is fully valid."""
    pmap = player_map()
    if not isinstance(new_layout, dict):
        return False
    cleaned, seen = {z["id"]: [] for z in ZONES}, set()
    for zid, ids in new_layout.items():
        if zid not in ZONE_GROUP or not isinstance(ids, list):
            return False
        for pid in ids:
            if pid not in pmap or pid in seen or pmap[pid]["pos"] != ZONE_GROUP[zid]:
                return False
            seen.add(pid)
            cleaned[zid].append(pid)
    if seen != set(pmap):
        return False
    data["layout"] = cleaned
    return True


# ---------------------------------------------------------------------------
# Styling (page + printable sheet). Printing hides everything except the sheet.
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
.ps-sheet, .ps-sheet * { color: #000 !important; }
.ps-sheet { background: #fff; font-family: Arial, Helvetica, sans-serif; padding: 18px 30px 26px;
            border: 1px solid #ccc; border-radius: 6px; max-width: 860px; margin: 8px auto; }
.ps-sheet .ps-logo { text-align: center; margin-bottom: 6px; }
.ps-sheet .ps-logo img { max-height: 110px; max-width: 100%; }
.ps-sheet .ps-logotext { font-weight: 900; font-size: 50px; letter-spacing: 3px; color: #C92A2A !important; }
.ps-sheet .ps-h { text-align: center; font-weight: 700; font-size: 17px; margin: 14px 0 12px; }
.ps-sheet .ps-grid3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px 10px; margin-bottom: 12px; }
.ps-sheet .ps-grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 10px; margin-bottom: 12px; }
.ps-sheet .ps-grid1 { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px 10px; margin-bottom: 12px; }
.ps-sheet .ps-card { display: flex; gap: 12px; align-items: flex-start; padding: 2px 4px; }
.ps-sheet .ps-no { font-size: 20px; min-width: 30px; text-align: right; line-height: 1.1; }
.ps-sheet .ps-nm { font-weight: 700; font-size: 12.5px; text-transform: uppercase; }
.ps-sheet .ps-sm { font-size: 9.5px; margin-top: 5px; }
.ps-sheet .ps-bottom { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 22px; }
.ps-sheet .ps-coaches { display: flex; justify-content: center; gap: 56px; flex-wrap: wrap; margin-top: 36px; text-align: center; }
.ps-sheet .ps-cn { font-weight: 700; font-size: 11.5px; text-transform: uppercase; }
.ps-sheet .ps-ct { font-size: 8.5px; text-transform: uppercase; margin: 6px 0 8px; }
.ps-sheet .ps-cc { font-size: 8.5px; }
@page { margin: 0.4in; }
@media print {
    header, [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stSidebar"],
    [data-baseweb="tab-list"], .stButton, button, h1, .stAlert, iframe {
        display: none !important;
    }
    .stApp, .main, .block-container { background: #fff !important; }
    .block-container { max-width: 100% !important; padding: 0 !important; }
    .ps-sheet { border: none !important; max-width: 100% !important; margin: 0 !important; padding: 0 !important; }
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Print sheet HTML (one compact string: no blank lines / indentation, so Markdown leaves it alone)
# ---------------------------------------------------------------------------
def sheet_card(p):
    hand = f"Catch: {p['shot']}" if p["pos"] == "G" else f"Shot {p['shot']}"
    size = " ".join(x for x in (f"H: {p['h']}" if p["h"] else "", f"W: {p['w']}" if p["w"] else "", hand) if x)
    town = " ".join(x for x in (p["hometown"], str(p["year"]) if p["year"] else "") if x)
    return (f"<div class='ps-card'><div class='ps-no'>{p['no']}</div><div>"
            f"<div class='ps-nm'>{escape(p['name'])}</div>"
            f"<div class='ps-sm'>{escape(size)}</div><div class='ps-sm'>{escape(town)}</div></div></div>")


def sheet_rows(section, grid):
    pmap = player_map()
    out = []
    for z in ZONES:
        if z["section"] != section or z.get("pool"):
            continue
        cards = "".join(sheet_card(pmap[i]) for i in data["layout"][z["id"]] if i in pmap)
        if cards:
            out.append(f"<div class='{grid}'>{cards}</div>")
    return "".join(out) or "<div class='ps-sm'>No players assigned</div>"


def sheet_html():
    logo = get_logo()
    logo_html = f"<img src='{logo}' alt='logo'>" if logo else "<span class='ps-logotext'>SPA</span>"
    coaches = "".join(
        f"<div><div class='ps-cn'>{escape(c['name'])}</div><div class='ps-ct'>{escape(c['title'])}</div>"
        + (f"<div class='ps-cc'>{escape(c['phone'])}</div>" if c["phone"] else "")
        + (f"<div class='ps-cc'>{escape(c['email'])}</div>" if c["email"] else "") + "</div>"
        for c in data["coaches"] if c["name"])
    return (f"<div class='ps-sheet'><div class='ps-logo'>{logo_html}</div>"
            f"<div class='ps-h'>FORWARDS</div>{sheet_rows('F', 'ps-grid3')}"
            f"<div class='ps-bottom'><div><div class='ps-h'>DEFENSEMEN</div>{sheet_rows('D', 'ps-grid2')}</div>"
            f"<div><div class='ps-h'>GOALTENDERS</div>{sheet_rows('G', 'ps-grid1')}</div></div>"
            + (f"<div class='ps-coaches'>{coaches}</div>" if coaches else "") + "</div>")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.title("🏒 SPA Hockey Management Dashboard")
st.caption(f"💾 Changes save automatically to {DATA_FILE}")
if st.session_state.get("load_warning"):
    st.warning(st.session_state["load_warning"])
if st.session_state.get("save_error"):
    st.error(f"Could not save to disk: {st.session_state['save_error']}. Use the backup download in the Team tab.")

tab_roster, tab_special, tab_team, tab_print = st.tabs(
    ["📊 Roster & Lines", "🎯 Special Teams", "👥 Team & Coaches", "🖨️ Printable Line Sheet"])

pmap = player_map()
if st.session_state.get("selected") not in pmap:
    st.session_state["selected"] = None

# --- TAB 1: ROSTER BOARD (drag and drop) + player editor + notes overview + add player ---
with tab_roster:
    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    event = lineup_board(
        zones=ZONES,
        players={p["id"]: {"pos": p["pos"], "no": p["no"], "name": p["name"], "h": p["h"], "w": p["w"],
                           "shot": p["shot"], "hometown": p["hometown"], "year": p["year"] or "",
                           "note": has_note(p)}
                 for p in data["players"]},
        layout=data["layout"], logo=get_logo(), selected=st.session_state.get("selected"),
        coaches=[{k: c[k] for k in ("name", "title", "phone", "email")} for c in data["coaches"] if c["name"]],
        nonce=st.session_state.get("board_nonce", 0), key="lineup_board", default=None)

    if isinstance(event, dict) and event.get("event") and event["event"] != st.session_state.get("last_event"):
        st.session_state["last_event"] = event["event"]
        if event.get("selected") in pmap:
            st.session_state["selected"] = event["selected"]
        if event.get("kind") == "move":
            if apply_move(event.get("layout")):
                persist()
            else:  # board was out of date: make it redraw from the saved data
                st.session_state["board_nonce"] = st.session_state.get("board_nonce", 0) + 1
                rerun()
    sig_after_board = board_sig()
    pmap = player_map()

    # ---- selected player editor ----
    st.markdown("---")
    p = pmap.get(st.session_state.get("selected"))
    if p is None:
        st.info("Click a player on the board to edit their details, stats and notes, or delete them.")
    else:
        pid, is_g = p["id"], p["pos"] == "G"

        def k(field):
            return f"edit_{pid}_{field}"

        st.markdown(f"### ✏️ {p['name']}  ·  #{p['no']}  ·  {POS_NAMES[p['pos']]}")
        for field in ("no", "name", "h", "w", "shot", "hometown", "year"):
            seed(k(field), p[field])
        seed(k("notes"), p.get("notes", ""))   # .get: a session opened before notes existed has no key yet
        c = st.columns([0.8, 2.2, 1, 1, 1, 2, 1])
        p["no"] = int(c[0].number_input("Number", min_value=0, max_value=99, step=1, key=k("no")))
        p["name"] = c[1].text_input("Name", key=k("name")).strip() or p["name"]
        p["h"] = c[2].text_input("Height", key=k("h"), placeholder="6'2").strip()
        p["w"] = c[3].text_input("Weight", key=k("w"), placeholder="185").strip()
        p["shot"] = c[4].selectbox("Catches" if is_g else "Shoots", ["L", "R"], key=k("shot"))
        p["hometown"] = c[5].text_input("Hometown", key=k("hometown"), placeholder="City, ST").strip()
        p["year"] = int(c[6].number_input("Birth year", min_value=0, max_value=2100, step=1, key=k("year")))

        if is_g:
            for field in ("wins", "losses", "ga", "sv"):
                seed(k(field), p[field])
            s = st.columns(4)
            p["wins"] = int(s[0].number_input("Wins", min_value=0, step=1, key=k("wins")))
            p["losses"] = int(s[1].number_input("Losses", min_value=0, step=1, key=k("losses")))
            p["ga"] = int(s[2].number_input("Goals against (GA)", min_value=0, step=1, key=k("ga")))
            p["sv"] = float(s[3].number_input("Save % (SV%)", min_value=0.0, max_value=1.0, step=0.001,
                                              format="%.3f", key=k("sv")))
        else:
            for field in ("g", "a", "pm"):
                seed(k(field), p[field])
            s = st.columns(3)
            p["g"] = int(s[0].number_input("Goals", min_value=0, step=1, key=k("g")))
            p["a"] = int(s[1].number_input("Assists", min_value=0, step=1, key=k("a")))
            p["pm"] = int(s[2].number_input("Plus/Minus (+/-)", min_value=-99, max_value=99, step=1, key=k("pm")))

        p["notes"] = st.text_area(
            "📝 Notes", key=k("notes"), height=150,
            placeholder="Coaching notes, injuries, things to work on...",
            help="Saved when you click outside the box or press Ctrl+Enter. Notes are never printed.").rstrip()

        d1, d2 = st.columns([1, 3])
        confirm = d1.checkbox("Confirm delete", key=k("del_ok"))
        if d2.button(f"🗑 Delete {p['name']}", key=k("del")):
            if confirm:
                st.session_state["flash"] = f"Deleted {p['name']}."
                delete_player(pid)
            else:
                st.warning("Tick “Confirm delete” first.")

    # ---- all notes at a glance (read-only; "Edit" just selects the player above) ----
    noted = sorted((q for q in data["players"] if has_note(q)), key=lambda q: (POS_ORDER[q["pos"]], q["no"]))
    with st.expander(f"📝 All player notes ({len(noted)})"):
        if not noted:
            st.caption("No notes yet. Click a player, then write in the Notes box under their stats.")
        for q in noted:
            left, right = st.columns([6, 1])
            left.markdown(
                f"<div style='margin-bottom:8px'><b>#{q['no']} {escape(q['name'])}</b> "
                f"<span style='color:#888;font-size:12px'>{POS_NAMES[q['pos']]}</span>"
                f"<div style='white-space:pre-wrap;font-size:14px'>{escape(q['notes'])}</div></div>",
                unsafe_allow_html=True)
            if right.button("Edit", key=f"notes_edit_{q['id']}"):
                st.session_state["selected"] = q["id"]
                rerun()

    # ---- add player ----
    with st.expander("➕ Add a player"):
        with st.form("add_player", clear_on_submit=True):
            a = st.columns([1.3, 0.8, 2.2, 1, 1, 1])
            pos_label = a[0].selectbox("Position", list(POS_LABELS))
            a_no = a[1].number_input("Number", min_value=0, max_value=99, step=1, value=0)
            a_name = a[2].text_input("Name")
            a_h = a[3].text_input("Height", placeholder="6'2")
            a_w = a[4].text_input("Weight", placeholder="185")
            a_shot = a[5].selectbox("Shoots / catches", ["L", "R"])
            b = st.columns([3, 1])
            a_town = b[0].text_input("Hometown", placeholder="City, ST")
            a_year = b[1].number_input("Birth year", min_value=0, max_value=2100, step=1, value=2009)
            added = st.form_submit_button("Add player")
        if added:
            if not a_name.strip():
                st.warning("Enter a name first.")
            else:
                newp = make_player({"pos": POS_LABELS[pos_label], "no": a_no, "name": a_name, "h": a_h, "w": a_w,
                                    "shot": a_shot, "hometown": a_town, "year": a_year})
                data["players"].append(newp)
                data["layout"][POOL_FOR[newp["pos"]]].append(newp["id"])
                st.session_state["selected"] = newp["id"]
                st.session_state["flash"] = (f"Added {newp['name']}. They start in "
                                             f"{'the goalie list' if newp['pos'] == 'G' else 'Scratches'}: "
                                             "drag them onto a line.")

# --- TAB 2: SPECIAL TEAMS ---
with tab_special:
    st.subheader("Tactical Special Teams Formations")
    special = data["special"]

    def render_formation(unit, form_type):
        st.caption(f"Formation layout: {form_type}")
        for row in FORMATIONS[form_type]:
            for col, cell in zip(st.columns(len(row)), row):
                if cell is None:
                    continue
                slot, label = cell
                skey = f"{unit}_{form_type}_{slot}"
                wkey = f"spec_{skey}"
                seed(wkey, special["slots"].get(skey, ""))
                special["slots"][skey] = col.text_input(label, key=wkey)

    left, right = st.columns(2)
    for i, (unit, options) in enumerate(UNITS):
        with (left if unit.startswith("PP") else right):
            if unit in ("PP1", "PK1"):
                st.markdown("### 🔴 Power Play Units" if unit == "PP1" else "### 🟢 Penalty Kill Units")
            tkey = f"spec_type_{unit}"
            saved = special["types"].get(unit)
            seed(tkey, saved if saved in options else options[0])
            choice = st.radio(f"{unit} Setup", options, key=tkey, horizontal=True)
            special["types"][unit] = choice
            render_formation(unit, choice)

# --- TAB 3: TEAM, COACHES, LOGO, BACKUP ---
with tab_team:
    st.subheader("Coaching staff (shown on the line sheet)")
    for c in list(data["coaches"]):
        cid = c["id"]
        for field in ("name", "title", "phone", "email"):
            seed(f"coach_{cid}_{field}", c[field])
        cols = st.columns([2, 1.5, 1.3, 2, 0.8])
        c["name"] = cols[0].text_input("Name", key=f"coach_{cid}_name").strip()
        c["title"] = cols[1].text_input("Title", key=f"coach_{cid}_title").strip()
        c["phone"] = cols[2].text_input("Phone", key=f"coach_{cid}_phone").strip()
        c["email"] = cols[3].text_input("Email", key=f"coach_{cid}_email").strip()
        cols[4].markdown("&nbsp;")
        if cols[4].button("🗑", key=f"coach_{cid}_del", help="Remove this coach"):
            data["coaches"] = [x for x in data["coaches"] if x["id"] != cid]
            clear_widget_state(f"coach_{cid}_")
            rerun()
    if st.button("➕ Add coach", key="coach_add"):
        data["coaches"].append(make_coach({"name": "New Coach", "title": "Assistant Coach"}))
        rerun()

    st.markdown("---")
    st.subheader("Team logo")
    logo_now = get_logo()
    if logo_now:
        st.markdown(f"<img src='{logo_now}' style='max-width:220px;max-height:110px'>", unsafe_allow_html=True)
    else:
        st.caption("No logo yet: the sheet shows “SPA” text. Upload your logo (PNG/JPG), or save it as "
                   "spa_logo.png next to this script.")
    up = st.file_uploader("Upload logo", type=["png", "jpg", "jpeg"], key="logo_upload")
    lc = st.columns(2)
    if lc[0].button("Use this logo", key="logo_use", disabled=up is None) and up is not None:
        data["logo"] = logo_from_upload(up.getvalue())
        rerun()
    if lc[1].button("Remove uploaded logo", key="logo_remove", disabled=not data["logo"]):
        data["logo"] = ""
        rerun()

    st.markdown("---")
    st.subheader("Backup")
    st.caption("Your data (including player notes) lives in a file on the computer running this app. If you host "
               "it somewhere that resets its disk, download a backup here and restore it later.")
    st.download_button("⬇ Download backup (.json)", json.dumps(data, indent=2, ensure_ascii=False),
                       file_name="spa_hockey_backup.json", mime="application/json", key="backup_dl")
    restore = st.file_uploader("Restore from a backup file", type=["json"], key="restore_upload")
    if st.button("Restore this backup", key="restore_go", disabled=restore is None) and restore is not None:
        try:
            restored = clean_data(json.loads(restore.getvalue().decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as exc:
            st.error(f"That file is not a valid backup: {exc}")
        else:
            st.session_state["data"] = restored
            data = restored
            for prefix in ("edit_", "spec_", "coach_"):
                clear_widget_state(prefix)
            st.session_state["selected"] = None
            st.session_state["flash"] = "Backup restored."
            persist()
            rerun()

# --- TAB 4: PRINTABLE LINE SHEET ---
with tab_print:
    st.caption("Players in Scratches are not printed. Stats and notes are never printed.")
    if st.button("🖨️ Open print window", key="print_btn"):
        # components.html runs inside an iframe, so ask the parent page to print.
        components.html("<script>window.parent.print();</script>", height=0)
    st.markdown(sheet_html(), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# End of run: save, and redraw the board if anything below it changed its data
# ---------------------------------------------------------------------------
persist()
if board_sig() != sig_after_board:
    rerun()
