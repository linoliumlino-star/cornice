#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera dash.png (600x800, scala di grigi) per il Kindle:
meteo compatto di due localita', frase del giorno in bolognese, risultati NBA della notte
e titoli delle ultime notizie (Il Post).

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
                 "precipitation_probability_max,precipitation_sum,snowfall_sum,wind_speed_10m_max",
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


UAS = [HDRS["User-Agent"],
       "Feedly/1.0 (+http://www.feedly.com/fetcher.html; like FeedFetcher-Google)",
       "Mozilla/5.0 (compatible; Feedbin; +https://feedbin.com)"]


def fetch_news(url, retries=2):
    import requests
    last = None
    for ua in UAS:
        for _ in range(retries):
            try:
                r = requests.get(url, timeout=30, headers={**HDRS, "User-Agent": ua})
                r.raise_for_status()
                return parse_news(r.content)
            except Exception as e:  # noqa
                last = e
                time.sleep(3)
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



# ------------------------------------------------------------------ NBA
ABBR_FIX = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS", "PHO": "PHX"}


def fetch_nba(now, retries=3):
    """Partite NBA concluse 'ieri' (data americana, fuso Est). -> [(away, sc_away, home, sc_home)]"""
    import requests
    et = ZoneInfo("America/New_York")
    day = now.astimezone(et).date() - dt.timedelta(days=1)
    url = ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
           f"?dates={day:%Y%m%d}&limit=50")
    last = None
    for _ in range(retries):
        try:
            r = requests.get(url, timeout=30, headers=HDRS)
            r.raise_for_status()
            return parse_nba(r.json())
        except Exception as e:  # noqa
            last = e
            time.sleep(4)
    raise last


def parse_nba(j):
    out = []
    for ev in j.get("events", []):
        try:
            if not ev["status"]["type"].get("completed"):
                continue
            comp = ev["competitions"][0]["competitors"]
            home = next(c for c in comp if c["homeAway"] == "home")
            away = next(c for c in comp if c["homeAway"] == "away")
            ab = lambda c: ABBR_FIX.get(c["team"]["abbreviation"], c["team"]["abbreviation"])
            out.append((ab(away), int(away["score"]), ab(home), int(home["score"])))
        except Exception:  # noqa
            continue
    return out


def draw_nba(d, games, y, error=False):
    """Riquadro risultati NBA a due colonne. Ritorna la y sotto il riquadro."""
    x0, x1 = 12, W - 12
    f_t, f_n, f_b = font(15, True), font(19), font(19, True)
    if error or games is None:
        rows, h = 0, 58
    elif not games:
        rows, h = 0, 58
    else:
        rows = (len(games) + 1) // 2
        h = 34 + rows * 26 + 6
    d.rectangle([x0, y, x1, y + h], outline=BLACK, width=2)
    d.text((x0 + 12, y + 8), "NBA · STANOTTE", font=f_t, fill=BLACK)
    if rows == 0:
        msg = "risultati non disponibili" if (error or games is None) else "nessuna partita"
        d.text((x0 + 12, y + 30), msg, font=font(17), fill=MID)
        return y + h
    colw = (x1 - x0 - 24) // 2
    for i, (aw, sa, ho, sh) in enumerate(games):
        cx = x0 + 14 + (i % 2) * (colw + 6)
        cy = y + 34 + (i // 2) * 26
        win_away = sa > sh
        x = cx
        d.text((x, cy), aw, font=f_b if win_away else f_n, fill=BLACK)
        x += d.textlength(aw, font=f_b if win_away else f_n)
        d.text((x, cy), " - ", font=f_n, fill=BLACK)
        x += d.textlength(" - ", font=f_n)
        d.text((x, cy), ho, font=f_n if win_away else f_b, fill=BLACK)
        x += d.textlength(ho, font=f_n if win_away else f_b)
        d.text((x, cy), f"  {sa}-{sh}", font=f_n, fill=DARK)
    return y + h


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


# ----------------------------------------------------------------- notizie
def fit_text(d, text, fnt, maxw):
    if d.textlength(text, font=fnt) <= maxw:
        return text
    while text and d.textlength(text + "…", font=fnt) > maxw:
        text = text[:-1]
    return text + "…"


def center_text(d, y, text, fnt, fill, x0=0, x1=W):
    w = d.textlength(text, font=fnt)
    d.text((x0 + (x1 - x0 - w) / 2, y), text, font=fnt, fill=fill)


def draw_news(d, items, x, y, bottom, width, label):
    d.text((x, y), label, font=font(14, True), fill=BLACK)
    y += 22
    if not items:
        d.text((x, y), "notizie non disponibili", font=font(17), fill=MID)
        return
    fnt = font(17, True)
    lh, gap, bullet = 20, 7, 18
    for it in items:
        lines = wrap_text(d, it["title"], fnt, width - bullet, 2)
        need = len(lines) * lh
        if y + need > bottom:
            break
        d.rectangle([x + 1, y + 7, x + 7, y + 13], fill=BLACK)
        for ln in lines:
            d.text((x + bullet, y), ln, font=fnt, fill=BLACK)
            y += lh
        y += gap


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


# -------------------------------------------------------------------- meteo
def day_label(day):
    dd = dt.date.fromisoformat(day["date"])
    return f"{GIORNI3[dd.weekday()]} {dd.day}"


def wet(day):
    return kind_of(day["code"]) in ("rain", "snow", "storm") or (day.get("pop") or 0) >= 40


def fmt_t(v):
    return "–" if v is None else f"{round(v)}°"


def draw_panel(d, x0, y0, x1, loc, w):
    """Meteo: oggi in grande, poi i prossimi giorni in piccolo. Ritorna la y del fondo."""
    center_text(d, y0, loc["name"].upper(), font(16, True), BLACK, x0, x1)
    if w is None:
        center_text(d, y0 + 30, "meteo non disponibile", font(17), MID, x0, x1)
        return y0 + 60
    today = w["days"][0]
    k = kind_of(today["code"])
    f_t = font(42, True)
    txt = f"{fmt_t(today['tmax'])} / {fmt_t(today['tmin'])}"
    icon_w = 50
    sx = x0 + (x1 - x0 - (icon_w + 8 + d.textlength(txt, font=f_t))) / 2
    draw_icon(d, k, sx + icon_w / 2, y0 + 50, 32)
    d.text((sx + icon_w + 8, y0 + 22), txt, font=f_t, fill=BLACK)
    parts = [DESCR[k]]
    if today.get("pop") is not None:
        parts.append(f"prec. {round(today['pop'])}%")
    if today.get("snow"):
        parts.append(f"neve {today['snow']:.0f} cm")
    center_text(d, y0 + 78, " · ".join(parts), font(16), DARK, x0, x1)

    yf = y0 + 108
    d.line([24, yf - 4, W - 24, yf - 4], fill=LIGHT, width=2)
    days = w["days"][1:5]
    cw = (x1 - x0) / max(len(days), 1)
    f_d, f_v, f_p = font(14, True), font(16, True), font(13)
    for n, day in enumerate(days):
        cx = x0 + cw * n + cw / 2
        center_text(d, yf, day_label(day), f_d, BLACK, cx - cw / 2, cx + cw / 2)
        tt = f"{fmt_t(day['tmax'])}/{fmt_t(day['tmin'])}"
        tot = 28 + d.textlength(tt, font=f_v)
        ix = cx - tot / 2
        draw_icon(d, kind_of(day["code"]), ix + 10, yf + 33, 17)
        d.text((ix + 28, yf + 22), tt, font=f_v, fill=BLACK)
        if wet(day) and day.get("pop") is not None:
            center_text(d, yf + 44, f"prec. {round(day['pop'])}%", f_p, DARK, cx - cw / 2, cx + cw / 2)
    return yf + 62


def render(now, weather, news, news_error, label, games, nba_error, phrase, demo=False):
    im = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    today = now.date()

    # data + frase del giorno
    center_text(d, 8, f"{GIORNI[today.weekday()]} {today.day} {MESI[today.month - 1]}".upper(),
                font(30, True), BLACK)
    y = 46
    if phrase:
        if phrase.get("a") is not None:
            fd = font(16, True, italic=True)
            for ln in wrap_text(d, "«" + phrase["d"] + "»", fd, W - 40, 4):
                center_text(d, y, ln, fd, BLACK)
                y += 21
            if phrase["a"]:
                center_text(d, y, "— " + phrase["a"], font(14), DARK)
                y += 19
        else:
            fd, fi = font(18, True, italic=True), font(14)
            for ln in wrap_text(d, "«" + phrase["d"] + "»", fd, W - 40, 2):
                center_text(d, y, ln, fd, BLACK)
                y += 22
            for ln in wrap_text(d, phrase["i"], fi, W - 40, 2):
                center_text(d, y, ln, fi, DARK)
                y += 18
    y += 6
    d.rectangle([0, y, W, y + 2], fill=BLACK)

    # meteo
    loc, w = weather[0]
    y = draw_panel(d, 0, y + 10, W, loc, w)
    d.rectangle([0, y, W, y + 2], fill=BLACK)

    # NBA
    y = draw_nba(d, games, y + 10, error=nba_error) + 10

    # notizie
    draw_news(d, [] if news_error else news, 16, y, 766, W - 32, label)

    # piede
    foot = f"aggiornato {now:%d/%m %H:%M}" + ("  ·  DEMO" if demo else "")
    d.text((16, 781), foot, font=font(12), fill=MID)

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
        {"date": "2026-11-20", "code": 2, "tmax": 12.8, "tmin": 4.1, "pop": 5, "rain": 0, "snow": 0, "wind": 8},
        {"date": "2026-11-21", "code": 61, "tmax": 9.0, "tmin": 5.2, "pop": 65, "rain": 5, "snow": 0, "wind": 15},
        {"date": "2026-11-22", "code": 0, "tmax": 12.0, "tmin": 3.0, "pop": 0, "rain": 0, "snow": 0, "wind": 7}]}
    w2 = {"days": [
        {"date": "2026-11-18", "code": 73, "tmax": 1.2, "tmin": -4.0, "pop": 80, "rain": 3.0, "snow": 6, "wind": 12},
        {"date": "2026-11-19", "code": 71, "tmax": 0.0, "tmin": -5.5, "pop": 50, "rain": 1.0, "snow": 2, "wind": 9},
        {"date": "2026-11-20", "code": 0, "tmax": 3.1, "tmin": -6.0, "pop": 0, "rain": 0, "snow": 0, "wind": 6}]}
    games = [("LAL", 131, "PHX", 123), ("IND", 124, "PHI", 131), ("CHA", 105, "LAC", 113),
             ("BOS", 118, "MIA", 102), ("DEN", 120, "GSW", 117), ("NYK", 99, "MIL", 104),
             ("DAL", 110, "SAS", 108)]
    return now, [w1, w2], news, games


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
        now, wlist, news, games = demo_data(tz)
        weather = list(zip(cfg["locations"], wlist))
        news_error = False
        nba_error = False
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
        try:
            games, nba_error = fetch_nba(now), False
        except Exception as e:  # noqa
            print(f"[nba] errore: {e}", file=sys.stderr)
            games, nba_error = None, True
        news, news_error = [], True
        sources = ncfg.get("sources") or [{"label": "", "url": ncfg.get("url", "")}]
        for src in sources:
            name = src.get("label") or src["url"]
            try:
                if a.news_file:
                    got = parse_news(open(a.news_file, "rb").read())
                else:
                    got = fetch_news(src["url"])
                if src.get("strip"):
                    for g in got:
                        g["title"] = re.sub(src["strip"], "", g["title"]).strip()
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

    im = render(now, weather, news, news_error, label, games, nba_error,
                get_phrase(now.date(), a.demo), demo=a.demo)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)
    print(f"Scritto {out} ({im.size[0]}x{im.size[1]}, modo {im.mode})")


if __name__ == "__main__":
    main()
