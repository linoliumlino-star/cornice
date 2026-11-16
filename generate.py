#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera dash.png (600x800, scala di grigi) per il Kindle:
meteo di due localita' + titoli delle ultime notizie (feed RSS).

Uso:
  python generate.py --out dash.png            # dati veri (serve la rete)
  python generate.py --demo --out demo.png     # dati d'esempio, senza rete
"""
import argparse, json, os, re, sys, time
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 600, 800
BLACK, DARK, MID, LIGHT, WHITE = 0, 50, 115, 190, 255

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
GIORNI3 = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def font(size, bold=False):
    name = "DejaVuSansCondensed-Bold.ttf" if bold else "DejaVuSansCondensed.ttf"
    p = ROOT / "fonts" / name
    if not p.exists():
        p = ROOT / name
    if not p.exists():
        p = Path("/usr/share/fonts/truetype/dejavu") / name
    return ImageFont.truetype(str(p), size)


# ----------------------------------------------------------------- meteo
def kind_of(code):
    if code in (0, 1):
        return "sun"
    if code == 2:
        return "partly"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "fog"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "storm"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    return "cloud"


DESCR = {"sun": "sereno", "partly": "variabile", "cloud": "nuvoloso", "fog": "nebbia",
         "rain": "pioggia", "snow": "neve", "storm": "temporale"}


def fetch_weather(loc, tzname, retries=3):
    import requests
    params = {
        "latitude": loc["lat"], "longitude": loc["lon"], "elevation": loc.get("elevation"),
        "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,precipitation_sum,snowfall_sum,wind_speed_10m_max",
        "timezone": tzname, "forecast_days": 3, "wind_speed_unit": "kmh",
    }
    last = None
    for _ in range(retries):
        try:
            r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=30)
            r.raise_for_status()
            return parse_weather(r.json())
        except Exception as e:  # noqa
            last = e
            time.sleep(4)
    raise last


def parse_weather(j):
    d = j["daily"]
    days = []
    for i in range(len(d["time"])):
        days.append({
            "date": d["time"][i], "code": d["weather_code"][i],
            "tmax": d["temperature_2m_max"][i], "tmin": d["temperature_2m_min"][i],
            "pop": d["precipitation_probability_max"][i], "rain": d["precipitation_sum"][i],
            "snow": d["snowfall_sum"][i], "wind": d["wind_speed_10m_max"][i],
        })
    return {"days": days}


# ------------------------------------------------------------- icone
def _cloud_shapes(cx, cy, s):
    return [("c", cx - 0.22 * s, cy - 0.02 * s, 0.26 * s),
            ("c", cx + 0.12 * s, cy - 0.14 * s, 0.34 * s),
            ("c", cx + 0.42 * s, cy + 0.04 * s, 0.22 * s),
            ("r", cx - 0.48 * s, cy + 0.02 * s, cx + 0.64 * s, cy + 0.30 * s, 0.14 * s)]


def draw_cloud(d, cx, cy, s, line=3):
    shapes = _cloud_shapes(cx, cy, s)
    for color, grow in ((BLACK, line), (WHITE, 0)):
        for sh in shapes:
            if sh[0] == "c":
                _, x, y, r = sh
                r += grow
                d.ellipse([x - r, y - r, x + r, y + r], fill=color)
            else:
                _, x0, y0, x1, y1, rad = sh
                d.rounded_rectangle([x0 - grow, y0 - grow, x1 + grow, y1 + grow],
                                    radius=rad + grow, fill=color)


def draw_sun(d, cx, cy, s, line=3):
    import math
    r = 0.30 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=BLACK, width=line)
    for k in range(8):
        a = k * math.pi / 4
        x0, y0 = cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45
        x1, y1 = cx + math.cos(a) * r * 2.0, cy + math.sin(a) * r * 2.0
        d.line([x0, y0, x1, y1], fill=BLACK, width=line)


def draw_icon(d, kind, cx, cy, s):
    line = max(2, int(s / 14))
    if kind == "sun":
        draw_sun(d, cx, cy, s, line)
    elif kind == "partly":
        draw_sun(d, cx - 0.28 * s, cy - 0.25 * s, s * 0.8, line)
        draw_cloud(d, cx + 0.05 * s, cy + 0.12 * s, s * 0.82, line)
    elif kind == "cloud":
        draw_cloud(d, cx, cy, s, line)
    elif kind == "fog":
        for i, (dx, w) in enumerate(((0.0, 1.0), (0.12, 0.8), (-0.05, 0.95), (0.1, 0.7))):
            y = cy - 0.36 * s + i * 0.24 * s
            d.line([cx - 0.55 * s * w + dx * s, y, cx + 0.55 * s * w + dx * s, y],
                   fill=BLACK, width=line + 1)
    elif kind == "rain":
        draw_cloud(d, cx, cy - 0.18 * s, s * 0.9, line)
        for i in (-1, 0, 1):
            x = cx + i * 0.3 * s
            d.line([x + 0.05 * s, cy + 0.2 * s, x - 0.08 * s, cy + 0.52 * s], fill=BLACK, width=line + 1)
    elif kind == "snow":
        draw_cloud(d, cx, cy - 0.18 * s, s * 0.9, line)
        for (dx, dy) in ((-0.3, 0.3), (0.0, 0.5), (0.3, 0.3), (-0.15, 0.62), (0.15, 0.62)):
            r = max(2, 0.055 * s)
            d.ellipse([cx + dx * s - r, cy + dy * s - r, cx + dx * s + r, cy + dy * s + r], fill=BLACK)
    elif kind == "storm":
        draw_cloud(d, cx, cy - 0.2 * s, s * 0.9, line)
        pts = [(0.08, 0.14), (-0.14, 0.46), (0.0, 0.46), (-0.1, 0.78), (0.22, 0.34), (0.06, 0.34)]
        d.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=BLACK)


# ---------------------------------------------------------------- notizie
HDRS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
        "Accept-Language": "it-IT,it;q=0.9"}


def fetch_news(url, retries=3):
    import requests
    import xml.etree.ElementTree as ET
    last = None
    for _ in range(retries):
        try:
            r = requests.get(url, timeout=30, headers=HDRS)
            r.raise_for_status()
            return parse_news(r.content)
        except Exception as e:  # noqa
            last = e
            time.sleep(4)
    raise last


def parse_news(xml_bytes):
    """Legge un feed RSS 2.0 o Atom e restituisce [{'title', 'when'}] (piu' recenti per primi)."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    root = ET.fromstring(xml_bytes)
    out = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title, when = "", None
        for ch in it:
            t = ch.tag.split("}")[-1]
            if t == "title" and ch.text:
                title = re.sub(r"\s+", " ", ch.text).strip()
            elif t in ("pubDate", "published", "updated") and ch.text and when is None:
                try:
                    when = parsedate_to_datetime(ch.text)
                except Exception:  # noqa
                    try:
                        when = dt.datetime.fromisoformat(ch.text.strip().replace("Z", "+00:00"))
                    except Exception:  # noqa
                        when = None
        if title:
            out.append({"title": title, "when": when})
    return out


def wrap_text(d, text, fnt, maxw, maxlines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=fnt) <= maxw:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > maxlines:
        lines = lines[:maxlines]
        lines[-1] = fit_text(d, lines[-1] + " …", fnt, maxw)
    return lines


def draw_news(d, items, x, y, bottom, width, label, tz):
    d.text((x, y), label, font=font(20, True), fill=BLACK)
    y += 36
    if not items:
        d.text((x, y), "notizie non disponibili", font=font(24), fill=MID)
        return
    fnt = font(23, True)
    lh, gap, bullet = 28, 14, 26
    for it in items:
        lines = wrap_text(d, it["title"], fnt, width - bullet, 3)
        need = len(lines) * lh
        if y + need > bottom:
            break
        d.rectangle([x + 2, y + 9, x + 12, y + 19], fill=BLACK)
        for ln in lines:
            d.text((x + bullet, y), ln, font=fnt, fill=BLACK)
            y += lh
        y += gap


def fit_text(d, text, fnt, maxw):
    if d.textlength(text, font=fnt) <= maxw:
        return text
    while text and d.textlength(text + "…", font=fnt) > maxw:
        text = text[:-1]
    return text + "…"


def draw_panel(d, x0, y0, x1, loc, w):
    """Pannello meteo di una localita' (x0..x1, a partire da y0)."""
    d.text((x0 + 8, y0 + 4), fit_text(d, loc["name"].upper(), font(19, True), x1 - x0 - 16),
           font=font(19, True), fill=BLACK)
    if w is None:
        d.text((x0 + 8, y0 + 70), "meteo non", font=font(22), fill=MID)
        d.text((x0 + 8, y0 + 96), "disponibile", font=font(22), fill=MID)
        return
    today = w["days"][0]
    k = kind_of(today["code"])
    draw_icon(d, k, x0 + 62, y0 + 78, 44)
    tmax = "–" if today["tmax"] is None else f"{round(today['tmax'])}°"
    tmin = "–" if today["tmin"] is None else f"{round(today['tmin'])}°"
    d.text((x0 + 128, y0 + 36), tmax, font=font(56, True), fill=BLACK)
    d.text((x0 + 130, y0 + 98), f"min {tmin}", font=font(22), fill=DARK)
    d.text((x0 + 8, y0 + 138), DESCR[k], font=font(22, True), fill=BLACK)
    parts = []
    if today.get("pop") is not None:
        parts.append(f"prec. {round(today['pop'])}%")
    if today.get("snow"):
        parts.append(f"neve {today['snow']:.0f} cm")
    d.text((x0 + 8, y0 + 168), " · ".join(parts), font=font(18), fill=DARK)
    if today.get("wind") is not None:
        d.text((x0 + 8, y0 + 192), f"vento {round(today['wind'])} km/h", font=font(18), fill=DARK)
    # mini previsioni dei due giorni successivi
    for n, day in enumerate(w["days"][1:3]):
        x = x0 + 8 + n * 138
        dd = dt.date.fromisoformat(day["date"])
        d.text((x, y0 + 222), f"{GIORNI3[dd.weekday()]} {dd.day}", font=font(17, True), fill=BLACK)
        draw_icon(d, kind_of(day["code"]), x + 20, y0 + 262, 16)
        tx = "–" if day["tmax"] is None else f"{round(day['tmax'])}°"
        tn = "–" if day["tmin"] is None else f"{round(day['tmin'])}°"
        d.text((x + 46, y0 + 246), f"{tx}/{tn}", font=font(20, True), fill=BLACK)


def render(now, weather, news, news_error, label, demo=False):
    im = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    today = now.date()

    # intestazione
    d.text((16, 12), f"{GIORNI[today.weekday()]} {today.day} {MESI[today.month - 1]}".upper(),
           font=font(32, True), fill=BLACK)
    d.rectangle([0, 60, W, 63], fill=BLACK)

    # meteo
    y0 = 70
    d.line([300, y0 + 4, 300, y0 + 282], fill=LIGHT, width=2)
    for (x0, x1), (loc, w) in zip(((8, 296), (306, 594)), weather):
        draw_panel(d, x0, y0, x1, loc, w)
    d.rectangle([0, 358, W, 360], fill=BLACK)

    # notizie
    draw_news(d, [] if news_error else news, 16, 370, 762, W - 32, label, now.tzinfo)

    # piede
    foot = f"aggiornato {now:%d/%m %H:%M}" + ("  ·  DEMO" if demo else "")
    d.text((16, 774), foot, font=font(15), fill=MID)

    # 16 livelli di grigio, senza dithering (il testo resta nitido)
    return im.point(lambda v: min(255, round(v / 17) * 17))


# ----------------------------------------------------------------- demo
def demo_data(tz):
    now = dt.datetime(2026, 11, 18, 6, 30, tzinfo=tz)
    news = [{"title": t, "when": None} for t in (
        "Il governo ha approvato la legge di bilancio, con alcune novità su pensioni e sanità",
        "In Emilia-Romagna è prevista allerta meteo per le piogge intense di mercoledì",
        "Cosa sappiamo del nuovo accordo commerciale tra Unione Europea e Mercosur",
        "È morto a 86 anni un celebre regista teatrale: aveva diretto opere in tutto il mondo",
        "Perché i biglietti dei concerti sono diventati così costosi",
        "Il Portogallo ha annunciato un'allerta di cinque giorni per il rischio di incendi",
        "Una nuova ricerca spiega perché dormiamo peggio d'inverno")]
    w1 = {"days": [
        {"date": "2026-11-18", "code": 61, "tmax": 11.4, "tmin": 6.2, "pop": 70, "rain": 4.0, "snow": 0, "wind": 14},
        {"date": "2026-11-19", "code": 3, "tmax": 10.1, "tmin": 5.0, "pop": 20, "rain": 0.2, "snow": 0, "wind": 10},
        {"date": "2026-11-20", "code": 2, "tmax": 12.8, "tmin": 4.1, "pop": 5, "rain": 0, "snow": 0, "wind": 8}]}
    w2 = {"days": [
        {"date": "2026-11-18", "code": 73, "tmax": 1.2, "tmin": -4.0, "pop": 80, "rain": 3.0, "snow": 6, "wind": 12},
        {"date": "2026-11-19", "code": 71, "tmax": 0.0, "tmin": -5.5, "pop": 50, "rain": 1.0, "snow": 2, "wind": 9},
        {"date": "2026-11-20", "code": 0, "tmax": 3.1, "tmin": -6.0, "pop": 0, "rain": 0, "snow": 0, "wind": 6}]}
    return now, [w1, w2], news


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dash.png")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--news-file", help="(test) legge le notizie da un file XML locale")
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    tz = ZoneInfo(cfg["timezone"])
    ncfg = cfg.get("news", {})
    label = ncfg.get("label", "NOTIZIE")
    limit = int(ncfg.get("max", 8))

    if a.demo:
        now, wlist, news = demo_data(tz)
        weather = list(zip(cfg["locations"], wlist))
        news_error = False
    else:
        now = dt.datetime.now(tz)
        weather, wfail = [], 0
        for loc in cfg["locations"]:
            try:
                weather.append((loc, fetch_weather(loc, cfg["timezone"])))
            except Exception as e:  # noqa
                print(f"[meteo {loc['name']}] errore: {e}", file=sys.stderr)
                weather.append((loc, None))
                wfail += 1
        news, news_error = [], True
        sources = ncfg.get("sources") or [{"label": "", "url": ncfg.get("url", "")}]
        for src in sources:
            name = src.get("label") or src["url"]
            try:
                if a.news_file:
                    got = parse_news(open(a.news_file, "rb").read())
                else:
                    got = fetch_news(src["url"], retries=2)
                got = got[:limit]
                if not got:
                    raise ValueError("feed vuoto")
                news, news_error = got, False
                if src.get("label"):
                    label = f"{label} · {src['label']}"
                print(f"[notizie] fonte: {name}")
                break
            except Exception as e:  # noqa
                print(f"[notizie] {name}: errore: {e}", file=sys.stderr)
        if wfail == len(cfg["locations"]) and news_error:
            print("Nessun dato disponibile: non genero l'immagine.", file=sys.stderr)
            sys.exit(1)

    im = render(now, weather, news, news_error, label, demo=a.demo)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)
    print(f"Scritto {out} ({im.size[0]}x{im.size[1]}, modo {im.mode})")


if __name__ == "__main__":
    main()
