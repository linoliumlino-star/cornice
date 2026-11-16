#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera dash.png (600x800, scala di grigi) per il Kindle:
meteo di due localita' + impegni di oggi (e domani, se c'e' spazio).

Uso:
  python generate.py --out dash.png            # dati veri (serve la rete + i segreti ICS_*)
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


# --------------------------------------------------------------- agenda
def initials(title):
    t = re.sub(r"\(.*?\)", "", title)
    out = []
    for tok in t.split()[:2]:
        m = re.search(r"[^\W\d_]", tok)
        if m:
            out.append(m.group(0).upper() + ".")
    return "".join(out) or title[:3]


def normalize(cal_cfg, ev):
    """Restituisce il testo da mostrare, oppure None se l'evento va scartato."""
    mode = cal_cfg.get("mode", "full")
    title = ev["title"]
    if mode == "initials":
        return initials(title)
    if mode == "match":
        if cal_cfg["match"].lower() in title.lower():
            return cal_cfg.get("show_as", title)
        return None
    return title


def load_events(cfg, start, end, tz):
    import requests
    import icalendar
    import recurring_ical_events
    out, errors = [], []
    for cal_cfg in cfg["calendars"]:
        url = os.environ.get(cal_cfg["env"], "").strip()
        if not url:
            errors.append(cal_cfg["label"])
            continue
        try:
            r = requests.get(url, timeout=40)
            r.raise_for_status()
            cal = icalendar.Calendar.from_ical(r.content)
            for comp in recurring_ical_events.of(cal).between(start, end):
                if str(comp.get("STATUS", "")).upper() == "CANCELLED":
                    continue
                s = comp.decoded("DTSTART")
                e = comp.decoded("DTEND") if comp.get("DTEND") else s
                allday = not isinstance(s, dt.datetime)
                if allday:
                    s = dt.datetime.combine(s, dt.time(0), tzinfo=tz)
                    e = dt.datetime.combine(e, dt.time(0), tzinfo=tz)
                else:
                    s = s.astimezone(tz) if s.tzinfo else s.replace(tzinfo=tz)
                    e = e.astimezone(tz) if e.tzinfo else e.replace(tzinfo=tz)
                out.append({"cal": cal_cfg, "title": str(comp.get("SUMMARY", "")).strip(),
                            "start": s, "end": e, "allday": allday})
        except Exception as ex:  # noqa
            print(f"[{cal_cfg['label']}] errore: {ex}", file=sys.stderr)
            errors.append(cal_cfg["label"])
    return out, errors


def items_for_day(events, day, tz):
    d0 = dt.datetime.combine(day, dt.time(0), tzinfo=tz)
    d1 = d0 + dt.timedelta(days=1)
    items = []
    for ev in events:
        if not (ev["start"] < d1 and ev["end"] > d0) and not (ev["start"] == ev["end"] and d0 <= ev["start"] < d1):
            continue
        text = normalize(ev["cal"], ev)
        if text is None:
            continue
        items.append({"allday": ev["allday"], "start": ev["start"], "end": ev["end"], "text": text})
    items.sort(key=lambda i: (not i["allday"], i["start"]))
    return items


# ------------------------------------------------------------ disegno
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


def draw_rows(d, items, x, y, maxrows, rowh, width):
    """Disegna le righe dell'agenda; ritorna (y finale, righe usate)."""
    shown = items
    extra = 0
    if len(items) > maxrows:
        shown = items[:maxrows - 1]
        extra = len(items) - len(shown)
    for it in shown:
        if it["allday"]:
            d.text((x, y), "●", font=font(20), fill=BLACK)
            d.text((x + 34, y), fit_text(d, it["text"], font(24, True), width - 34), font=font(24, True), fill=BLACK)
        else:
            t = f"{it['start']:%H:%M}–{it['end']:%H:%M}"
            d.text((x, y), t, font=font(24, True), fill=BLACK)
            d.text((x + 168, y), fit_text(d, it["text"], font(24), width - 168), font=font(24), fill=BLACK)
        y += rowh
    if extra:
        d.text((x, y), f"+ altri {extra}…", font=font(22), fill=MID)
        y += rowh
    return y, len(shown) + (1 if extra else 0)


def render(now, weather, events, cal_errors, demo=False):
    tz = now.tzinfo
    im = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    today = now.date()
    tomorrow = today + dt.timedelta(days=1)

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

    # agenda
    y = 368
    d.text((16, y), "OGGI", font=font(20, True), fill=BLACK)
    y += 34
    rowh = 34
    bottom = 764
    today_items = items_for_day(events, today, tz)
    tomorrow_items = items_for_day(events, tomorrow, tz)
    maxrows = (bottom - y) // rowh
    if cal_errors:
        d.text((W - 16 - d.textlength("calendario non letto", font=font(16)), y - 30),
               "calendario non letto", font=font(16), fill=MID)
    if not today_items:
        d.text((16, y), "Nessun impegno oggi", font=font(24), fill=MID)
        y += rowh
        rows_used = 1
    else:
        # lascio almeno 3 righe a "domani" se c'e' spazio
        y, rows_used = draw_rows(d, today_items, 16, y, maxrows, rowh, W - 32)
    left = maxrows - rows_used
    if left >= 3 and tomorrow_items:
        y += 6
        d.rectangle([16, y, W - 16, y + 1], fill=LIGHT)
        y += 10
        d.text((16, y), f"DOMANI · {GIORNI3[tomorrow.weekday()]} {tomorrow.day}", font=font(18, True), fill=DARK)
        y += 30
        left = (bottom - y) // rowh
        draw_rows(d, tomorrow_items, 16, y, max(left, 1), rowh, W - 32)

    # piede
    foot = f"aggiornato {now:%d/%m %H:%M}" + ("  ·  DEMO" if demo else "")
    d.text((16, 774), foot, font=font(15), fill=MID)

    # 16 livelli di grigio, senza dithering (il testo resta nitido)
    return im.point(lambda v: min(255, round(v / 17) * 17))


# ----------------------------------------------------------------- demo
def demo_data(tz):
    now = dt.datetime(2026, 11, 18, 6, 30, tzinfo=tz)

    def L(d, h1, m1, h2, m2, title, cal=0):
        return {"cal": CFG["calendars"][cal], "title": title, "allday": False,
                "start": dt.datetime(2026, 11, d, h1, m1, tzinfo=tz),
                "end": dt.datetime(2026, 11, d, h2, m2, tzinfo=tz)}

    def A(d, title, cal=1):
        return {"cal": CFG["calendars"][cal], "title": title, "allday": True,
                "start": dt.datetime(2026, 11, d, 0, 0, tzinfo=tz),
                "end": dt.datetime(2026, 11, d + 1, 0, 0, tzinfo=tz)}

    ev = [L(18, 15, 15, 16, 0, "Andrea Lisi"), L(18, 16, 0, 16, 30, "Coco Dario"),
          L(18, 16, 30, 17, 15, "Zuccheri Gabriele"), L(18, 17, 15, 18, 0, "Serra Davide"),
          L(18, 18, 0, 18, 45, "Stanzani Arianna"), A(18, "Marco"), A(17, "Federica"),
          L(19, 16, 30, 17, 15, "Tipaldi Irene"), L(19, 17, 15, 18, 0, "Cocchi Zoe"),
          L(19, 18, 0, 18, 45, "Loccarini Anna"), L(19, 18, 45, 19, 30, "Ciocca Nicolò"),
          A(19, "Marco")]
    w1 = {"days": [
        {"date": "2026-11-18", "code": 61, "tmax": 11.4, "tmin": 6.2, "pop": 70, "rain": 4.0, "snow": 0, "wind": 14},
        {"date": "2026-11-19", "code": 3, "tmax": 10.1, "tmin": 5.0, "pop": 20, "rain": 0.2, "snow": 0, "wind": 10},
        {"date": "2026-11-20", "code": 2, "tmax": 12.8, "tmin": 4.1, "pop": 5, "rain": 0, "snow": 0, "wind": 8}]}
    w2 = {"days": [
        {"date": "2026-11-18", "code": 73, "tmax": 1.2, "tmin": -4.0, "pop": 80, "rain": 3.0, "snow": 6, "wind": 12},
        {"date": "2026-11-19", "code": 71, "tmax": 0.0, "tmin": -5.5, "pop": 50, "rain": 1.0, "snow": 2, "wind": 9},
        {"date": "2026-11-20", "code": 0, "tmax": 3.1, "tmin": -6.0, "pop": 0, "rain": 0, "snow": 0, "wind": 6}]}
    return now, [w1, w2], ev


# ----------------------------------------------------------------- main
def main():
    global CFG
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dash.png")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    CFG = json.load(open(a.config, encoding="utf-8"))
    tz = ZoneInfo(CFG["timezone"])

    if a.demo:
        now, wlist, events = demo_data(tz)
        weather = list(zip(CFG["locations"], wlist))
        errors = []
    else:
        now = dt.datetime.now(tz)
        weather, wfail = [], 0
        for loc in CFG["locations"]:
            try:
                weather.append((loc, fetch_weather(loc, CFG["timezone"])))
            except Exception as e:  # noqa
                print(f"[meteo {loc['name']}] errore: {e}", file=sys.stderr)
                weather.append((loc, None))
                wfail += 1
        d0 = dt.datetime.combine(now.date(), dt.time(0), tzinfo=tz)
        events, errors = load_events(CFG, d0, d0 + dt.timedelta(days=2), tz)
        if wfail == len(CFG["locations"]) and len(errors) == len(CFG["calendars"]):
            print("Nessun dato disponibile: non genero l'immagine.", file=sys.stderr)
            sys.exit(1)

    im = render(now, weather, events, errors, demo=a.demo)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)
    print(f"Scritto {out} ({im.size[0]}x{im.size[1]}, modo {im.mode})")


CFG = {}

if __name__ == "__main__":
    main()
