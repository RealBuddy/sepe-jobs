#!/usr/bin/env python3
"""Pull SEPE offers for Asturias (provincia=33) sector by sector -> asturias_offers.json.

An unfiltered provincia=33 search is capped by SEPE at 15 pages / 600 offers: the site
silently drops the OLDEST and only hints at it with a "más resultados de los que se
presentan" notice. Per-sector searches stay far under the cap (biggest is ~141) and
together yield ~721. Each sector is therefore a complete, independently refreshable
slice: a run may refresh any subset of sectors, and only those get swept.

Polite: one session for the whole run, 3-4.5s throttle, stop-on-block.
"""
import re, html as H, json, time, random, os, sys, argparse, urllib.parse, urllib.request, http.cookiejar
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "asturias_offers.json")
BASE = "https://www.sistemanacionalempleo.es/OfertaDifusionWEB/"
DO = BASE + "busquedaOfertas.do"
FORM = DO + "?modo=continuar"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
WAF = re.compile(r"request rejected|access denied|forbidden|captcha|support id", re.I)
NO_HITS = re.compile(r"No se han encontrado ofertas", re.I)

SECTORS = ["AO", "AA", "AR", "AU", "CC", "DO", "EO", "IP", "IA", "FE", "MD", "IG", "MT", "IQ",
           "IT", "IM", "MR", "MN", "MO", "PA", "PC", "PT", "SA", "SF", "SP", "EM", "TC", "TH"]

# Night slots, keyed by UTC hour, balanced by page count (the big ones: SP/TH 4 pages, SA 3).
# Each slot is ~7-11 requests. Every slot runs the full pipeline afterwards, so a cron the
# scheduler drops only delays its own sectors by a day instead of stalling the catalog.
SLOTS = {
    1: ["SP", "CC", "AA", "MD", "DO", "IG", "PA"],
    2: ["TH", "EO", "AO", "AU", "FE", "IM", "PC"],
    3: ["SA", "TC", "IP", "MR", "IA", "SF", "MN"],
    4: ["MO", "EM", "MT", "IQ", "IT", "AR", "PT"],
}

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", UA), ("Accept-Language", "es-ES,es;q=0.9")]

def nap(): time.sleep(3.0 + random.random() * 1.5)

def get(url, ref=None):
    r = urllib.request.Request(url, headers={"Referer": ref} if ref else {})
    with op.open(r, timeout=25) as x: return x.status, x.read().decode("iso-8859-1", "replace")

def post(url, data, ref=None):
    body = "&".join(f"{k}={urllib.parse.quote(str(v), encoding='iso-8859-1')}" for k, v in data.items())
    h = {"Content-Type": "application/x-www-form-urlencoded"}
    if ref: h["Referer"] = ref
    r = urllib.request.Request(url, data=body.encode("iso-8859-1", "replace"), headers=h)
    with op.open(r, timeout=25) as x: return x.status, x.read().decode("iso-8859-1", "replace")

def parse(doc):
    out = []
    A = list(re.finditer(r'<a[^>]*detalleOferta\.do\?[^"\']*?id=(\d{6,})[^"\']*"[^>]*>(.*?)</a>', doc, re.S | re.I))
    for i, m in enumerate(A):
        oid = m.group(1)
        title = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        pre = doc[(A[i-1].end() if i else max(0, m.start()-400)):m.start()]
        post_ = doc[m.end():(A[i+1].start() if i+1 < len(A) else m.end()+400)]
        pflat = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", pre)))
        sflat = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", post_)))
        d = re.findall(r"\d{2}/\d{2}/\d{4}", pflat)
        loc = re.search(r"([A-Za-zÁÉÍÓÚÑáéíóúñ .'\-/]+?)\s*\(([^)]+)\)", sflat)
        out.append({"id": oid, "title": title, "date": d[-1] if d else None,
                    "municipio": loc.group(1).strip() if loc else None,
                    "provincia": loc.group(2).strip() if loc else "Asturias",
                    "url": f"https://www.sistemanacionalempleo.es/OfertaDifusionWEB/detalleOferta.do?modo=inicio&id={oid}&ret=B"})
    return out

def open_session():
    """Form -> advanced search. Returns idFlujo, reusable for every search in this run."""
    st, form = get(FORM, FORM)
    idf = re.search(r'name="idFlujo"\s+value="([^"]+)"', form).group(1)
    nap()
    get(DO + f"?modo=cambiarModo&idFlujo={idf}", FORM)
    return idf

def crawl_sector(idf, sec):
    """Return list of offers, or None if the response was not trustworthy.

    None means "we don't know what's in this sector right now" (block, HTTP error,
    truncated reply) and must never be confused with "this sector is empty" -- the
    caller would sweep a live sector away. Only an explicit no-hits page counts as empty.
    """
    ref = DO + f"?modo=cambiarModo&idFlujo={idf}"
    st, p = post(FORM, {"idFlujo": idf, "queryStr": "", "palabraBusqueda": "", "sectorProfesional": sec,
                        "area": "/es", "provincia": "33", "municipio": "", "diaINI": "", "mesINI": "",
                        "anioINI": "", "diaFIN": "", "mesFIN": "", "anioFIN": "", "salarioCuantia": "",
                        "botonNavegacion": "Enviar"}, ref=ref)
    if st != 200 or WAF.search(p):
        print(f"  {sec}: BLOCKED (status {st})", flush=True); return None
    u = H.unescape(p)
    # Must precede parsing: a no-hits page still renders a "por Comunidad Autónoma" widget
    # holding ~10 offers from other provinces, which parse() cannot tell from real results.
    if NO_HITS.search(u):
        print(f"  {sec}: empty", flush=True); return []
    offers = {o["id"]: o for o in parse(p)}
    if not offers:
        print(f"  {sec}: no rows and no 'not found' notice -- treating as failure", flush=True); return None
    tp = re.search(r"Total de p.ginas:\s*(\d+)", u)
    pages = int(tp.group(1)) if tp else 1
    for pg in range(1, pages):
        nap()
        st, d = get(BASE + f"listadoOfertas.do?modo=pagina&idFlujo={idf}&indice={pg*40+1}", FORM)
        if st != 200 or WAF.search(d):
            print(f"  {sec}: BLOCKED at page {pg+1} (status {st})", flush=True); return None
        for o in parse(d): offers[o["id"]] = o
    if re.search(r"m.s resultados de los que se presentan", u, re.I):
        print(f"  {sec}: WARNING -- SEPE says this sector is truncated; shard it further", flush=True)
    # We asked for provincia=33, so a row placed elsewhere is never ours. parse() falls back
    # to "Asturias" when the location is unreadable, so this only drops confidently-foreign
    # rows -- an Asturias offer registered by another province's office (its id then carries
    # that province's prefix, e.g. 06...Ribadedeva) still reads as Asturias and stays.
    out = [o for o in offers.values() if (o.get("provincia") or "Asturias").lower().startswith("asturias")]
    if len(out) != len(offers):
        print(f"  {sec}: dropped {len(offers) - len(out)} row(s) outside Asturias", flush=True)
    print(f"  {sec}: {len(out)} offers ({pages} pages)", flush=True)
    return out

def load_store():
    if not os.path.exists(OUT): return {"offers": [], "sectors": {}}
    s = json.load(open(OUT))
    return {"offers": s.get("offers", []), "sectors": s.get("sectors", {})}

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="crawl every sector, replacing the store outright")
    g.add_argument("--slot", type=int, choices=sorted(SLOTS), help="crawl one night slot's sectors")
    g.add_argument("--sectors", help="comma-separated sector codes")
    a = ap.parse_args()

    if a.slot: want = SLOTS[a.slot]
    elif a.sectors: want = [s.strip().upper() for s in a.sectors.split(",") if s.strip()]
    else: want = SECTORS
    bad = [s for s in want if s not in SECTORS]
    if bad: sys.exit(f"unknown sector(s): {', '.join(bad)}")
    full = a.all or set(want) == set(SECTORS)
    print(f"crawling {len(want)} sector(s): {', '.join(want)}", flush=True)

    idf = open_session()
    fresh, failed = {}, []
    for sec in want:
        nap()
        got = crawl_sector(idf, sec)
        if got is None: failed.append(sec)
        else: fresh[sec] = got

    if not fresh:
        print(f"\nABORT: every sector failed ({', '.join(failed)}); store left untouched.")
        sys.exit(1)

    store = load_store()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if full and not failed:
        kept = []  # a clean full sweep is authoritative: the store is exactly what we just saw
    else:
        # Sweep only the sectors we actually refreshed. Everything else -- including sectors
        # that failed this run -- keeps yesterday's rows rather than silently disappearing.
        kept = [o for o in store["offers"] if o.get("sector") not in fresh]
        orphan = [o for o in kept if o.get("sector") not in SECTORS]
        if orphan:
            print(f"dropping {len(orphan)} offer(s) with no known sector (pre-sharding leftovers)")
            kept = [o for o in kept if o.get("sector") in SECTORS]

    offers = list(kept)
    for sec, got in fresh.items():
        for o in got:
            o["sector"] = sec
            offers.append(o)
        store["sectors"][sec] = {"last_crawled": now, "count": len(got)}

    seen, dedup = set(), []
    for o in offers:  # a fresh sector wins over a stale copy filed under another sector
        if o["id"] in seen: continue
        seen.add(o["id"]); dedup.append(o)
    if len(dedup) != len(offers):
        print(f"note: {len(offers) - len(dedup)} offer(s) appeared in more than one sector")

    # Stable order, or every run rewrites the whole file: refreshed sectors would land
    # wherever the merge happened to put them and git would diff ~6k lines for a handful
    # of real changes -- noisy history and a needlessly wide conflict surface.
    dedup.sort(key=lambda o: o["id"])
    res = {"offers": dedup, "count": len(dedup), "sectors": store["sectors"],
           "updated": now, "failed_sectors": sorted(failed)}
    json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=2, sort_keys=True)
    print(f"\nDONE: {len(dedup)} Asturias offers across {len(store['sectors'])} sector(s) -> {OUT}")
    if failed: print(f"failed (kept previous data): {', '.join(failed)}")

main()
