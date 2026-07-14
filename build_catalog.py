#!/usr/bin/env python3
"""Build index.html (searchable) + catalog.csv + offers/<municipio>/*.md
from asturias_offers.json + translations.json. Portable (relative paths)."""
import json, csv, collections, html, os, re, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
offs = json.load(open(os.path.join(BASE, "asturias_offers.json")))
if isinstance(offs, dict):
    offs = offs.get("offers", [])
tr = json.load(open(os.path.join(BASE, "translations.json")))
cf = {k.lower(): v for k, v in tr.items()}

def norm(t):
    t = re.sub(r"\(\s*ref[^)]*\)", "", t or "", flags=re.I)
    t = re.sub(r"ref[.:]\s*\d+", "", t, flags=re.I)
    t = re.sub(r"\(\s*\d+\s*\)", "", t)
    t = re.sub(r"^\s*\d+\s+(puestos?\s+de\s+|plazas?\s+de\s+)?", "", t, flags=re.I)
    t = re.sub(r"[.\s]+$", "", t).strip(" .:-")
    return re.sub(r"\s+", " ", t)

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
        "url": o.get("url") or "",
    })
rows.sort(key=lambda r: (r["municipio"], r["occupation_ru"] or r["occupation_es"]))
print(f"offers: {len(rows)}, without RU translation: {miss}")

# --- CSV ---
with open(os.path.join(BASE, "catalog.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["id", "occupation_ru", "occupation_es", "title_full_es",
                                      "municipio", "provincia", "date", "url"])
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
by_muni = collections.Counter(r["municipio"] for r in rows)
by_occ = collections.Counter(r["occupation_ru"] or r["occupation_es"] for r in rows)
munis = sorted(by_muni, key=lambda m: -by_muni[m])
top_occ = by_occ.most_common(12)
data_json = json.dumps(rows, ensure_ascii=False)
muni_opts = "".join(f'<option value="{html.escape(m)}">{html.escape(m)} ({by_muni[m]})</option>' for m in munis)
top_chips = "".join(f'<span class="chip" onclick="setSearch(this.dataset.q)" data-q="{html.escape(o)}">{html.escape(o)} · {c}</span>' for o, c in top_occ)

HTML = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Вакансии Астурии (SEPE) — каталог</title>
<style>
:root{{--bg:#0f1216;--card:#171b21;--line:#2a313b;--txt:#e7ecf2;--mut:#93a1b0;--acc:#4ea1ff;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}}
header{{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:14px 18px;z-index:5}}
h1{{margin:0 0 4px;font-size:18px}} .sub{{color:var(--mut);font-size:13px}}
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
tr:hover td{{background:#1b2028}} .ru{{font-weight:600}} .es{{color:var(--mut);font-size:12.5px}}
.muni{{white-space:nowrap}} .date{{color:var(--mut);white-space:nowrap;font-variant-numeric:tabular-nums}}
a.src{{color:var(--acc);text-decoration:none;white-space:nowrap}} a.src:hover{{text-decoration:underline}}
@media(max-width:640px){{.es{{display:none}}}}
</style></head><body>
<header>
  <h1>Вакансии Астурии · SEPE</h1>
  <div class="sub">{len(rows)} вакансий · {len(munis)} населённых пунктов · источник: Sistema Nacional de Empleo. Обновляется автоматически.</div>
  <div class="controls">
    <input id="q" placeholder="Поиск (рус/исп): повар, limpiador, сиделка, gijón…" oninput="render()">
    <select id="muni" onchange="render()"><option value="">Все города ({len(rows)})</option>{muni_opts}</select>
  </div>
  <div class="chips">{top_chips}</div>
</header>
<div class="wrap"><div class="count" id="count"></div>
  <table><thead><tr>
    <th onclick="sortBy('occupation_ru')">Профессия (RU)</th>
    <th onclick="sortBy('municipio')">Город</th>
    <th onclick="sortBy('date')">Дата</th><th>Отклик</th>
  </tr></thead><tbody id="rows"></tbody></table></div>
<script>
const DATA={data_json};
let sortKey='municipio',sortDir=1;const el=(id)=>document.getElementById(id);
function setSearch(q){{el('q').value=q;render();}}
function sortBy(k){{sortDir=(sortKey===k)?-sortDir:1;sortKey=k;render();}}
function render(){{
  const q=el('q').value.trim().toLowerCase(),m=el('muni').value;
  let r=DATA.filter(x=>{{if(m&&x.municipio!==m)return false;if(!q)return true;
    return (x.occupation_ru+' '+x.occupation_es+' '+x.title_full_es+' '+x.municipio).toLowerCase().includes(q);}});
  r.sort((a,b)=>{{const A=(a[sortKey]||'')+'',B=(b[sortKey]||'')+'';return A<B?-sortDir:A>B?sortDir:0;}});
  el('count').textContent=`Найдено: ${{r.length}}`;
  el('rows').innerHTML=r.map(x=>`<tr>
    <td><div class="ru">${{esc(x.occupation_ru||x.occupation_es)}}</div><div class="es">${{esc(x.occupation_es)}}</div></td>
    <td class="muni">${{esc(x.municipio)}}</td><td class="date">${{esc(x.date)}}</td>
    <td><a class="src" href="${{x.url}}" target="_blank" rel="noopener noreferrer">Откликнуться ↗</a></td></tr>`).join('');
}}
function esc(s){{return (s||'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));}}
render();
</script></body></html>"""
open(os.path.join(BASE, "index.html"), "w", encoding="utf-8").write(HTML)
print(f"wrote index.html, catalog.csv, offers/ ({len(rows)} offers, {len(munis)} municipios)")
