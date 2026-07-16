#!/usr/bin/env python3
"""Build index.html (searchable) + catalog.csv + offers/<municipio>/*.md
from asturias_offers.json + translations.json. Portable (relative paths)."""
import json, csv, collections, html, os, re, shutil
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
offs = json.load(open(os.path.join(BASE, "asturias_offers.json")))
if isinstance(offs, dict):
    offs = offs.get("offers", [])
tr = json.load(open(os.path.join(BASE, "translations.json")))
cf = {k.lower(): v for k, v in tr.items()}

SECTOR_NAMES = {
    "AO": "Administración y oficinas", "AA": "Agrario", "AR": "Artesanía", "AU": "Automoción",
    "CC": "Comercio", "DO": "Docencia e investigación", "EO": "Edificación y obras públicas",
    "IP": "Industria pesada y construcciones metálicas", "IA": "Industrias alimentarias",
    "FE": "Industrias de fabricación de equipos electromecánicos",
    "MD": "Industrias de la madera y corcho", "IG": "Industrias gráficas",
    "MT": "Industrias manufactureras diversas", "IQ": "Industrias químicas",
    "IT": "Industrias textiles", "IM": "Información y manifestaciones artísticas",
    "MR": "Mantenimiento y reparación", "MN": "Minería y primeras transformaciones",
    "MO": "Montaje e instalación", "PA": "Pesca y acuicultura", "PC": "Piel y cuero",
    "PT": "Producción, transformación y distribución de energía y agua", "SA": "Sanidad",
    "SF": "Seguros y finanzas", "SP": "Servicios a la comunidad y personales",
    "EM": "Servicios a las empresas", "TC": "Transportes y comunicaciones",
    "TH": "Turismo y hostelería",
}

def norm(t):
    t = re.sub(r"\(\s*ref[^)]*\)", "", t or "", flags=re.I)
    t = re.sub(r"ref[.:]\s*\d+", "", t, flags=re.I)
    t = re.sub(r"\(\s*\d+\s*\)", "", t)
    t = re.sub(r"^\s*\d+\s+(puestos?\s+de\s+|plazas?\s+de\s+)?", "", t, flags=re.I)
    t = re.sub(r"[.\s]+$", "", t).strip(" .:-")
    return re.sub(r"\s+", " ", t)

def iso(d):
    """dd/mm/yyyy -> yyyy-mm-dd (sortable). Empty string if unparseable."""
    m = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})\s*$", d or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""

rows = []
miss = 0
for o in offs:
    base = o.get("base") or norm(o.get("title", ""))
    ru = cf.get(base.lower(), "")
    if not ru:
        miss += 1
    rows.append({
        "id": o["id"], "occupation_es": base, "occupation_ru": ru,
        "title_full_es": o.get("title", ""), "municipio": o.get("municipio") or "",
        "provincia": o.get("provincia") or "Asturias", "date": o.get("date") or "",
        "date_iso": iso(o.get("date")), "sector": o.get("sector") or "",
        "sector_es": SECTOR_NAMES.get(o.get("sector"), ""), "url": o.get("url") or "",
    })
# id breaks ties: without it equal (municipio, occupation) rows keep the store's order,
# so any reshuffle upstream rewrites unrelated CSV lines.
rows.sort(key=lambda r: (r["municipio"], r["occupation_ru"] or r["occupation_es"], r["id"]))
print(f"offers: {len(rows)}, without RU translation: {miss}")

# --- CSV ---
with open(os.path.join(BASE, "catalog.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["id", "occupation_ru", "occupation_es", "title_full_es",
                                      "municipio", "provincia", "date", "date_iso",
                                      "sector", "sector_es", "url"])
    w.writeheader()
    w.writerows(rows)

# --- per-offer markdown files, grouped by municipio ---
def safe(s): return re.sub(r'[\/:*?"<>|]+', "_", (s or "").strip()) or "Sin_municipio"
oroot = os.path.join(BASE, "offers")
if os.path.isdir(oroot): shutil.rmtree(oroot)
os.makedirs(oroot)
for r in rows:
    occ = r["occupation_ru"] or r["occupation_es"]
    d = os.path.join(oroot, safe(r["municipio"])); os.makedirs(d, exist_ok=True)
    body = f"""# {occ}

- **Профессия (ES):** {r['occupation_es']}
- **Оригинальное название:** {r['title_full_es']}
- **Город:** {r['municipio']} ({r['provincia']})
- **Дата публикации:** {r['date']}
- **ID оферты:** {r['id']}

## 👉 Откликнуться на вакансию
**{r['url']}**

_На странице SEPE — раздел «Datos de contacto» (email/телефон) и «Requisitos»._
"""
    open(os.path.join(d, f"{safe(occ)[:50]} — {r['id']}.md"), "w", encoding="utf-8").write(body)

# --- HTML ---
try:
    from zoneinfo import ZoneInfo
    now, tz_ru, tz_es = datetime.now(ZoneInfo("Europe/Madrid")), "Мадрид", "Madrid"
except Exception:  # no tzdata on the host
    now, tz_ru, tz_es = datetime.now(timezone.utc), "UTC", "UTC"
by_muni = collections.Counter(r["municipio"] for r in rows)
munis = sorted(by_muni, key=lambda m: -by_muni[m])
data_json = json.dumps(rows, ensure_ascii=False)
muni_opts = "".join(f'<option value="{html.escape(m)}">{html.escape(m)} ({by_muni[m]})</option>' for m in munis)

def chips(field):
    # Group case-insensitively: SEPE's own titles mix casing, so a raw Counter renders
    # "Gerocultor/a · 20" next to "gerocultor/a · 7" as if they were different jobs.
    groups = collections.defaultdict(collections.Counter)
    for r in rows:
        v = r[field] or r["occupation_es"]
        groups[v.lower()][v] += 1
    top = sorted(groups.values(), key=lambda c: -sum(c.values()))[:12]
    return "".join(f'<span class="chip" onclick="setSearch(this.dataset.q)" data-q="{html.escape(c.most_common(1)[0][0])}">'
                   f'{html.escape(c.most_common(1)[0][0])} · {sum(c.values())}</span>' for c in top)

# Both pages are the same catalogue over the same data; they differ only in wording and in
# which occupation field leads. The ES page shows SEPE's own titles, so it needs no translation.
LANGS = {
    "index.html": dict(
        lang="ru", tz=tz_ru, fmt="%d.%m.%Y, %H:%M",
        title="Вакансии Астурии (SEPE) — каталог", h1="Вакансии Астурии · SEPE",
        sub=f"{len(rows)} вакансий · {len(munis)} населённых пунктов · источник: Sistema Nacional de Empleo.",
        updated="Обновлено", auto="обновляется автоматически каждую ночь",
        ph="Поиск (рус/исп): повар, limpiador, сиделка, gijón…",
        all_munis=f"Все города ({len(rows)})",
        th_occ="Профессия (RU)", th_muni="Город", th_date="Дата", th_apply="Отклик",
        apply="Откликнуться ↗", found="Найдено", sort_key="occupation_ru",
        primary="x.occupation_ru||x.occupation_es", secondary="x.occupation_es",
        alt_href="index_es.html", alt_label="Español", chips=chips("occupation_ru"),
    ),
    "index_es.html": dict(
        lang="es", tz=tz_es, fmt="%d/%m/%Y, %H:%M",
        title="Ofertas de empleo en Asturias (SEPE) — catálogo", h1="Ofertas de empleo en Asturias · SEPE",
        sub=f"{len(rows)} ofertas · {len(munis)} municipios · fuente: Sistema Nacional de Empleo.",
        updated="Actualizado", auto="se actualiza automáticamente cada noche",
        ph="Buscar: cocinero, limpiador, gijón…",
        all_munis=f"Todos los municipios ({len(rows)})",
        th_occ="Profesión", th_muni="Municipio", th_date="Fecha", th_apply="Oferta",
        apply="Ver oferta ↗", found="Encontradas", sort_key="occupation_es",
        # Not title_full_es: it is occupation_es plus a ref number, so it renders as a
        # near-duplicate of the line above it. The sector is the useful second line here.
        primary="x.occupation_es", secondary="x.sector_es",
        alt_href="index.html", alt_label="Русский", chips=chips("occupation_es"),
    ),
}

def page(c):
    updated = f"{now:{c['fmt']}} ({c['tz']})"
    return f"""<!doctype html><html lang="{c['lang']}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{c['title']}</title>
<style>
:root{{--bg:#0f1216;--card:#171b21;--line:#2a313b;--txt:#e7ecf2;--mut:#93a1b0;--acc:#4ea1ff;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}}
header{{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:14px 18px;z-index:5}}
h1{{margin:0 0 4px;font-size:18px}} .sub{{color:var(--mut);font-size:13px}}
.sub .upd{{color:var(--txt);font-weight:600}}
.controls{{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}}
input,select{{background:var(--card);border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:9px 12px;font-size:14px}}
input#q{{flex:1;min-width:220px}}
.chips{{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}}
.chip{{background:var(--card);border:1px solid var(--line);color:var(--mut);border-radius:20px;padding:3px 10px;font-size:12px;cursor:pointer}}
.chip:hover{{border-color:var(--acc);color:var(--txt)}}
.wrap{{padding:12px 18px 40px}} .count{{color:var(--mut);font-size:13px;margin:8px 0}}
table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{position:sticky;top:0;background:var(--card);font-size:12px;color:var(--mut);cursor:pointer;user-select:none}}
tr:hover td{{background:#1b2028}} .occ{{font-weight:600}} .alt{{color:var(--mut);font-size:12.5px}}
.muni{{white-space:nowrap}} .date{{color:var(--mut);white-space:nowrap;font-variant-numeric:tabular-nums}}
a.src{{color:var(--acc);text-decoration:none;white-space:nowrap}} a.src:hover{{text-decoration:underline}}
a.lang{{float:right;color:var(--acc);text-decoration:none;font-size:13px;border:1px solid var(--line);border-radius:20px;padding:3px 12px}}
a.lang:hover{{border-color:var(--acc)}}
@media(max-width:640px){{.alt{{display:none}}}}
</style></head><body>
<header>
  <a class="lang" href="{c['alt_href']}">{c['alt_label']}</a>
  <h1>{c['h1']}</h1>
  <div class="sub">{c['sub']}
    <br>{c['updated']}: <b class="upd">{updated}</b> · {c['auto']}.</div>
  <div class="controls">
    <input id="q" placeholder="{c['ph']}" oninput="render()">
    <select id="muni" onchange="render()"><option value="">{c['all_munis']}</option>{muni_opts}</select>
  </div>
  <div class="chips">{c['chips']}</div>
</header>
<div class="wrap"><div class="count" id="count"></div>
  <table><thead><tr>
    <th onclick="sortBy('{c['sort_key']}')">{c['th_occ']}</th>
    <th onclick="sortBy('municipio')">{c['th_muni']}</th>
    <th onclick="sortBy('date_iso')">{c['th_date']}</th><th>{c['th_apply']}</th>
  </tr></thead><tbody id="rows"></tbody></table></div>
<script>
const DATA={data_json};
let sortKey='date_iso',sortDir=-1;const el=(id)=>document.getElementById(id);
function setSearch(q){{el('q').value=q;render();}}
function sortBy(k){{sortDir=(sortKey===k)?-sortDir:1;sortKey=k;render();}}
function render(){{
  const q=el('q').value.trim().toLowerCase(),m=el('muni').value;
  let r=DATA.filter(x=>{{if(m&&x.municipio!==m)return false;if(!q)return true;
    return (x.occupation_ru+' '+x.occupation_es+' '+x.title_full_es+' '+x.municipio).toLowerCase().includes(q);}});
  r.sort((a,b)=>{{const A=(a[sortKey]||'')+'',B=(b[sortKey]||'')+'';return A<B?-sortDir:A>B?sortDir:0;}});
  el('count').textContent=`{c['found']}: ${{r.length}}`;
  el('rows').innerHTML=r.map(x=>`<tr>
    <td><div class="occ">${{esc({c['primary']})}}</div><div class="alt">${{esc({c['secondary']})}}</div></td>
    <td class="muni">${{esc(x.municipio)}}</td><td class="date">${{esc(x.date)}}</td>
    <td><a class="src" href="${{x.url}}" target="_blank" rel="noopener noreferrer">{c['apply']}</a></td></tr>`).join('');
}}
function esc(s){{return (s||'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));}}
render();
</script></body></html>"""

for fname, cfg in LANGS.items():
    open(os.path.join(BASE, fname), "w", encoding="utf-8").write(page(cfg))
print(f"wrote {', '.join(LANGS)}, catalog.csv, offers/ ({len(rows)} offers, {len(munis)} municipios)")
