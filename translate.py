#!/usr/bin/env python3
"""Fill missing ES->RU occupation translations via Google Translate, cached in translations.json.
Existing entries (incl. hand-curated) are preserved; only NEW occupations are translated."""
import json, os, re, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
OFFERS = os.path.join(BASE, "asturias_offers.json")
TRANS = os.path.join(BASE, "translations.json")

raw = json.load(open(OFFERS)) if os.path.exists(OFFERS) else []
offers = raw.get("offers", []) if isinstance(raw, dict) else raw
cache = json.load(open(TRANS)) if os.path.exists(TRANS) else {}
cache_cf = {k.lower() for k in cache}

def norm(t):
    t = re.sub(r"\(\s*ref[^)]*\)", "", t or "", flags=re.I)
    t = re.sub(r"ref[.:]\s*\d+", "", t, flags=re.I)
    t = re.sub(r"\(\s*\d+\s*\)", "", t)
    t = re.sub(r"^\s*\d+\s+(puestos?\s+de\s+|plazas?\s+de\s+)?", "", t, flags=re.I)
    t = re.sub(r"[.\s]+$", "", t).strip(" .:-")
    return re.sub(r"\s+", " ", t)

# distinct occupation "base" strings needing translation
need = []
seen = set()
for o in offers:
    b = (o.get("base") or norm(o.get("title", ""))).strip()
    if not b or b.lower() in cache_cf or b.lower() in seen:
        continue
    seen.add(b.lower())
    need.append(b)

print(f"occupations: {len(offers)} offers, {len(cache)} cached, {len(need)} new to translate")
if not need:
    print("nothing new to translate.")
    sys.exit(0)

try:
    from deep_translator import GoogleTranslator
except ImportError:
    print("deep-translator not installed; leaving new occupations untranslated.")
    sys.exit(0)

tr = GoogleTranslator(source="es", target="ru")
added = 0
for i, es in enumerate(need):
    # strip a trailing "(ref...)" that may survive, for a cleaner translation input
    src = re.sub(r"\(\s*ref[^)]*\)", "", es, flags=re.I).strip() or es
    try:
        ru = tr.translate(src)
        if ru and ru.strip():
            cache[es] = ru.strip()
            added += 1
    except Exception as e:
        print(f"  translate failed for {es!r}: {e}")
    time.sleep(0.4)  # be gentle with the free endpoint
    if (i + 1) % 25 == 0:
        print(f"  ...{i+1}/{len(need)}")

json.dump(cache, open(TRANS, "w"), ensure_ascii=False, indent=2, sort_keys=True)
print(f"added {added} translations -> translations.json ({len(cache)} total)")
