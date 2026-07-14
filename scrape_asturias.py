#!/usr/bin/env python3
"""Pull ALL SEPE offers for Asturias (provincia=33, all sectors) -> asturias_offers.json.
Polite: single session, 3-4.5s throttle, stop-on-block."""
import re, html as H, json, time, random, os, sys, urllib.parse, urllib.request, http.cookiejar

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "asturias_offers.json")
BASE = "https://www.sistemanacionalempleo.es/OfertaDifusionWEB/"
DO = BASE + "busquedaOfertas.do"
FORM = DO + "?modo=continuar"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
WAF = re.compile(r"request rejected|access denied|forbidden|captcha|support id", re.I)

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

# flow: form -> advanced -> POST provincia=33
st, form = get(FORM, FORM)
idf = re.search(r'name="idFlujo"\s+value="([^"]+)"', form).group(1)
nap()
get(DO + f"?modo=cambiarModo&idFlujo={idf}", FORM); nap()
st, page1 = post(FORM, {"idFlujo": idf, "queryStr": "", "palabraBusqueda": "", "sectorProfesional": "",
                        "area": "/es", "provincia": "33", "municipio": "", "diaINI": "", "mesINI": "",
                        "anioINI": "", "diaFIN": "", "mesFIN": "", "anioFIN": "", "salarioCuantia": "",
                        "botonNavegacion": "Enviar"}, ref=DO + f"?modo=cambiarModo&idFlujo={idf}")
tp = re.search(r"Total de p.ginas:\s*(\d+)", H.unescape(page1))
pages = int(tp.group(1)) if tp else 1
offers = {o["id"]: o for o in parse(page1)}
print(f"page 1/{pages}: {len(offers)} offers", flush=True)
stopped = None
for p in range(1, pages):
    nap()
    st, pg = get(BASE + f"listadoOfertas.do?modo=pagina&idFlujo={idf}&indice={p*40+1}", FORM)
    if st != 200 or WAF.search(pg):
        stopped = f"blocked at page {p+1} (status {st})"; break
    new = parse(pg)
    for o in new: offers[o["id"]] = o
    print(f"page {p+1}/{pages}: +{len(new)} -> {len(offers)} total", flush=True)

res = {"offers": list(offers.values()), "count": len(offers), "pages": pages, "stopped": stopped}
# Safety: don't clobber a good dataset with a blocked/short crawl.
MIN_OK = 100
if len(offers) < MIN_OK and os.path.exists(OUT):
    prev = json.load(open(OUT))
    if prev.get("count", 0) >= len(offers):
        print(f"\nABORT SAVE: got only {len(offers)} (stopped={stopped}); keeping previous {prev.get('count')} offers.")
        sys.exit(0)
json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=2)
print(f"\nDONE: {len(offers)} Asturias offers, stopped={stopped} -> {OUT}")
