#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera dash.png (600x800, scala di grigi) per il Kindle, in stile widget da parete:
data in alto, meteo grande (temperatura attuale e previsioni), frase del giorno in basso.

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


def font(size, bold=False, italic=False):
    base = "DejaVuSansCondensed"
    suffix = ("-BoldOblique" if bold else "-Oblique") if italic else ("-Bold" if bold else "")
    for nm in (base + suffix + ".ttf", base + ("-Bold" if bold else "") + ".ttf"):
        for folder in (ROOT / "fonts", ROOT, Path("/usr/share/fonts/truetype/dejavu")):
            p = folder / nm
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


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


def fetch_weather(loc, tzname, retries=4):
    import requests
    params = {
        "latitude": loc["lat"], "longitude": loc["lon"], "elevation": loc.get("elevation"),
        "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,precipitation_sum,snowfall_sum,wind_speed_10m_max,"
                 "sunrise,sunset",
        "timezone": tzname, "forecast_days": 5, "wind_speed_unit": "kmh",
    }
    last = None
    for _ in range(retries):
        try:
            r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=20)
            r.raise_for_status()
            return parse_weather(r.json())
        except Exception as e:  # noqa
            last = e
            time.sleep(6)
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
            "sunrise": d["sunrise"][i] if d.get("sunrise") else None,
            "sunset": d["sunset"][i] if d.get("sunset") else None,
        })
    cur = j.get("current") or {}
    return {"days": days, "now": cur.get("temperature_2m"), "now_code": cur.get("weather_code")}


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
    line = max(2, min(6, int(s / 14)))
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
            d.line([x + 0.05 * s, cy + 0.13 * s, x - 0.08 * s, cy + 0.46 * s], fill=BLACK, width=line + 1)
    elif kind == "snow":
        draw_cloud(d, cx, cy - 0.18 * s, s * 0.9, line)
        for (dx, dy) in ((-0.3, 0.3), (0.0, 0.5), (0.3, 0.3), (-0.15, 0.62), (0.15, 0.62)):
            r = max(2, 0.055 * s)
            d.ellipse([cx + dx * s - r, cy + dy * s - r, cx + dx * s + r, cy + dy * s + r], fill=BLACK)
    elif kind == "storm":
        draw_cloud(d, cx, cy - 0.2 * s, s * 0.9, line)
        pts = [(0.08, 0.14), (-0.14, 0.46), (0.0, 0.46), (-0.1, 0.78), (0.22, 0.34), (0.06, 0.34)]
        d.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=BLACK)


# ------------------------------------------------------------ testo
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



def fit_text(d, text, fnt, maxw):
    if d.textlength(text, font=fnt) <= maxw:
        return text
    while text and d.textlength(text + "…", font=fnt) > maxw:
        text = text[:-1]
    return text + "…"


def center_text(d, y, text, fnt, fill, x0=0, x1=W):
    w = d.textlength(text, font=fnt)
    d.text((x0 + (x1 - x0 - w) / 2, y), text, font=fnt, fill=fill)


# ------------------------------------------------------- frase del giorno
# Proverbi bolognesi tratti da fonti pubbliche (quotidiano.net, Wikiquote, raccolta di
# detti dell'Unione Reno Galliera); grafia e traduzione come riportate dalle fonti.
# 'm' = mesi in cui il detto "suona giusto" (None = tutto l'anno).
PHRASES = [
    {"d": "Utober bel ma porta teg' l'umbrell", "i": "Ottobre bello, ma porta con te l'ombrello", "m": [10]},
    {"d": "Per San Lùca chi n'ha semne se splùca", "i": "Per San Luca, chi non ha seminato resta a mani vuote", "m": [10]},
    {"d": "Quând ai é la fumèna, méttet la gabèna", "i": "Quando c'è la nebbia, mettiti la giacca", "m": [10, 11, 12, 1, 2]},
    {"d": "Par San Zamiân, s'an piôv incȗ, a piôv admân", "i": "Per San Geminiano, se oggi non piove, piove domani", "m": [1, 2]},
    {"d": "Febrarôl cȗrt cȗrt, l'é pîz d'un tȗrc", "i": "Febbraio, corto corto, è peggio di un turco", "m": [2]},
    {"d": "Par la Candelòra, dell'inverno sêmo fòra, ma se al sòul al dà in dal zèd, d'l'invéren a sèn a mèz",
     "i": "Per la Candelora siamo fuori dall'inverno, ma se il sole batte sulle siepi, ne siamo a metà", "m": [2]},
    {"d": "Mèrz marzâz, ténzom al cȗl e brîsa al mustâz", "i": "Marzo marzaccio, tingimi il sedere e non il viso", "m": [3]},
    {"d": "Quând al zîl al fà la lèna, al piôv dènter dala stmèna", "i": "Quando il cielo fa la lana, piove entro la settimana", "m": None},
    {"d": "Quând la muntâgna l'é scȗra, la stasòn l'é insicȗra", "i": "Quando la montagna è scura, la stagione è incerta", "m": None},
    {"d": "La fardȗra, trî dé dȗra", "i": "Il raffreddore dura tre giorni", "m": [10, 11, 12, 1, 2, 3]},
    {"d": "Granè nôva, bèn spâza", "i": "Scopa nuova, spazza bene", "m": None},
    {"d": "Mèl an fèr, pòra an avèir", "i": "Male non fare, paura non avere", "m": None},
    {"d": "Chî lâsa la vî vècia par la nôva, pinté as trôva", "i": "Chi lascia la via vecchia per la nuova, pentito si trova", "m": None},
    {"d": "La tèvla an lasèr mâi se la bòcca l'an sa da furmâi", "i": "Non lasciare la tavola finché la bocca non sa di formaggio", "m": None},
    {"d": "Al mêdigh pietôus fa la piega verminôusa", "i": "Il medico pietoso fa la piaga verminosa", "m": None},
    {"d": "L'aquila en ciapa mòsch", "i": "L'aquila non prende mosche", "m": None},
    {"d": "Un poc d'zug è po bèll", "i": "Un po' di scherzo è bello, se dura poco", "m": None},
    {"d": "Ch'in mâgna, à magnè", "i": "Chi non mangia, ha mangiato", "m": None},
]


def phrase_of_the_day(today):
    pool = [p for p in PHRASES if p["m"] is None or today.month in p["m"]]
    return pool[today.timetuple().tm_yday % len(pool)]


# ------------------------------------------- frase del giorno da Wikiquote
WQ_UA = {"User-Agent": "CorniceKindle/1.0 (https://github.com/linoliumlino-star/cornice)"}


def _wq_clean(s):
    s = s.replace("{{!}}", " / ")
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = s.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", s).strip()


def parse_quote(wt):
    """Legge il modello {{Cdg|citazione=...|autore=...}} di Wikiquote."""
    m = re.search(r"\{\{\s*Cdg\s*\|(.*)\}\}\s*$", wt.strip(), re.S)
    body, parts, depth, cur, i = m.group(1), [], 0, "", 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            cur += two
            i += 2
        elif two in ("}}", "]]"):
            depth -= 1
            cur += two
            i += 2
        elif body[i] == "|" and depth == 0:
            parts.append(cur)
            cur = ""
            i += 1
        else:
            cur += body[i]
            i += 1
    parts.append(cur)
    kv = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k.strip()] = v.strip()
    q, a = _wq_clean(kv["citazione"]), _wq_clean(kv.get("autore", ""))
    if not q or len(q) > 230:
        raise ValueError(f"citazione non adatta ({len(q)} caratteri)")
    return {"d": q, "a": a}


def fetch_quote(today, retries=3):
    """Citazione del giorno di it.wikiquote.org (una per ogni giorno dell'anno)."""
    import requests
    page = f"Template:Qotd/{today.day}{MESI[today.month - 1]}"
    last = None
    for _ in range(retries):
        try:
            r = requests.get("https://it.wikiquote.org/w/index.php", timeout=20, headers=WQ_UA,
                             params={"title": page, "action": "raw"})
            r.raise_for_status()
            return parse_quote(r.text)
        except Exception as e:  # noqa
            last = e
            time.sleep(3)
    raise last


def get_phrase(today, demo=False):
    if demo:
        return {"d": "Il peggio che può capitare a un genio è di essere compreso.", "a": "Ennio Flaiano"}
    try:
        return fetch_quote(today)
    except Exception as e:  # noqa
        print(f"[frase] Wikiquote: errore: {e} (uso un proverbio bolognese)", file=sys.stderr)
        return phrase_of_the_day(today)


# ------------------------------------------------------------------ disegno
def fmt_t(v):
    return "–" if v is None else f"{round(v)}°"


def day_label(day):
    dd = dt.date.fromisoformat(day["date"])
    return f"{GIORNI3[dd.weekday()].upper()} {dd.day}"


def wet(day):
    return kind_of(day["code"]) in ("rain", "snow", "storm") or (day.get("pop") or 0) >= 40


def hhmm(iso):
    return iso[-5:] if iso else "--:--"


CARD = 238   # grigio chiarissimo dei riquadri


def draw_hero(d, w, y0):
    """Icona del giorno con massima e minima in grande; ritorna la y del fondo."""
    today = w["days"][0]
    k = kind_of(today["code"])
    f_big, f_lab = font(88, True), font(20, True)
    tmax, tmin = fmt_t(today["tmax"]), fmt_t(today["tmin"])
    nw = max(d.textlength(tmax, font=f_big), d.textlength(tmin, font=f_big))
    icon_w, lab_w, gap = 190, 56, 24
    sx = (W - (icon_w + gap + lab_w + nw)) / 2
    draw_icon(d, k, sx + icon_w / 2, y0 + 96, 170)
    x = sx + icon_w + gap
    for i, (lab, txt) in enumerate((("MAX", tmax), ("MIN", tmin))):
        yy = y0 + i * 96
        d.text((x, yy + 63), lab, font=f_lab, fill=MID)
        d.text((x + lab_w, yy), txt, font=f_big, fill=BLACK)
    y = y0 + 200
    line1 = DESCR[k].capitalize()
    if today.get("pop") is not None and (wet(today) or today["pop"] >= 20):
        line1 += f"  ·  prec. {round(today['pop'])}%"
    if today.get("snow"):
        line1 += f"  ·  neve {today['snow']:.0f} cm"
    center_text(d, y, line1, font(26, True), BLACK)
    y += 38
    center_text(d, y, f"alba {hhmm(today.get('sunrise'))}    tramonto {hhmm(today.get('sunset'))}", font(18), MID)
    return y + 26


def draw_cards(d, w, y0, h=168):
    days = w["days"][1:5]
    n = len(days)
    gap = 10
    cw = (W - 24 - gap * (n - 1)) / n
    f_d, f_v, f_p = font(20, True), font(24, True), font(16)
    for i, day in enumerate(days):
        x0 = 12 + i * (cw + gap)
        d.rounded_rectangle([x0, y0, x0 + cw, y0 + h], radius=20, fill=CARD)
        cx = x0 + cw / 2
        center_text(d, y0 + 12, day_label(day), f_d, BLACK, x0, x0 + cw)
        draw_icon(d, kind_of(day["code"]), cx, y0 + 80, 56)
        center_text(d, y0 + 112, f"{fmt_t(day['tmax'])}/{fmt_t(day['tmin'])}", f_v, BLACK, x0, x0 + cw)
        if wet(day) and day.get("pop") is not None:
            center_text(d, y0 + 144, f"prec. {round(day['pop'])}%", f_p, DARK, x0, x0 + cw)
    return y0 + h


def draw_phrase(d, phrase, top, bottom):
    """Frase del giorno centrata verticalmente tra top e bottom."""
    if not phrase:
        return
    if phrase.get("a") is not None:
        fa = font(17)
        txt = "«" + phrase["d"] + "»"
        for size, nmax in ((21, 4), (19, 5), (17, 5)):
            fq = font(size, True, italic=True)
            if len(wrap_text(d, txt, fq, W - 56, 99)) <= nmax:
                break
        lines = wrap_text(d, txt, fq, W - 56, nmax)
        blocks = [(ln, fq, BLACK, size + 6) for ln in lines]
        if phrase["a"]:
            blocks.append(("— " + phrase["a"], fa, DARK, 26))
    else:
        fq, fi = font(22, True, italic=True), font(17)
        lines = wrap_text(d, "«" + phrase["d"] + "»", fq, W - 56, 3)
        blocks = [(ln, fq, BLACK, 28) for ln in lines]
        blocks += [(ln, fi, DARK, 22) for ln in wrap_text(d, phrase["i"], fi, W - 56, 2)]
    total = sum(b[3] for b in blocks)
    y = top + max(0, (bottom - top - total) / 2)
    for text, f, col, lh in blocks:
        center_text(d, y, text, f, col)
        y += lh


def render(now, loc, w, phrase, demo=False):
    im = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    today = now.date()

    # data
    center_text(d, 14, GIORNI[today.weekday()].upper(), font(28, True), DARK)
    center_text(d, 46, f"{today.day} {MESI[today.month - 1]}", font(54, True), BLACK)
    center_text(d, 116, loc["name"].upper(), font(17, True), MID)
    d.line([40, 146, W - 40, 146], fill=LIGHT, width=2)

    if w is None:
        center_text(d, 300, "meteo non disponibile", font(28), MID)
        y = 440
    else:
        y = draw_hero(d, w, 156)
        y = draw_cards(d, w, y + 4)

    # frase del giorno
    top = y + 14
    d.line([40, top, W - 40, top], fill=LIGHT, width=2)
    draw_phrase(d, phrase, top + 6, 772)

    # piede (a destra resta libero per l'indicatore di carica scritto dal Kindle)
    foot = f"aggiornato {now:%d/%m %H:%M}" + ("  ·  DEMO" if demo else "")
    d.text((16, 781), foot, font=font(12), fill=MID)

    # 16 livelli di grigio, senza dithering (il testo resta nitido)
    return im.point(lambda v: min(255, round(v / 17) * 17))


# ----------------------------------------------------------------- demo
def demo_data(tz):
    now = dt.datetime(2026, 11, 18, 6, 30, tzinfo=tz)
    w = {"now": 7.4, "now_code": 61, "days": [
        {"date": "2026-11-18", "code": 61, "tmax": 11.4, "tmin": 6.2, "pop": 70, "rain": 4.0, "snow": 0, "wind": 14, "sunrise": "2026-11-18T07:12", "sunset": "2026-11-18T16:56"},
        {"date": "2026-11-19", "code": 3, "tmax": 10.1, "tmin": 5.0, "pop": 20, "rain": 0.2, "snow": 0, "wind": 10, "sunrise": None, "sunset": None},
        {"date": "2026-11-20", "code": 2, "tmax": 12.8, "tmin": 4.1, "pop": 5, "rain": 0, "snow": 0, "wind": 8, "sunrise": None, "sunset": None},
        {"date": "2026-11-21", "code": 61, "tmax": 9.0, "tmin": 5.2, "pop": 65, "rain": 5, "snow": 0, "wind": 15, "sunrise": None, "sunset": None},
        {"date": "2026-11-22", "code": 0, "tmax": 12.0, "tmin": 3.0, "pop": 0, "rain": 0, "snow": 0, "wind": 7, "sunrise": None, "sunset": None}]}
    return now, w


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dash.png")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    tz = ZoneInfo(cfg["timezone"])
    loc = cfg["locations"][0]

    if a.demo:
        now, w = demo_data(tz)
    else:
        now = dt.datetime.now(tz)
        try:
            w = fetch_weather(loc, cfg["timezone"])
        except Exception as e:  # noqa
            print(f"[meteo] errore: {e}: non genero l'immagine (resta la precedente).", file=sys.stderr)
            sys.exit(1)

    im = render(now, loc, w, get_phrase(now.date(), a.demo), demo=a.demo)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)
    print(f"Scritto {out} ({im.size[0]}x{im.size[1]}, modo {im.mode})")


if __name__ == "__main__":
    main()
