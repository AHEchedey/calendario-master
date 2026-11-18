#!/usr/bin/env python3
"""Convierte el calendar.json del calendario del máster en un calendar.ics.

Uso:
  python generate_ics.py [ORIGEN] [SALIDA] [--subjects GTI,IC,...] [--no-holidays]

ORIGEN  URL o ruta local del calendar.json
        (por defecto: https://inmahernandez.github.io/calendar-master/calendar.json)
SALIDA  archivo .ics a escribir (por defecto: calendar.ics)

Los UID son estables (dependen de asignatura+fecha+tipo+aula), así que Google
Calendar actualiza los eventos existentes en lugar de duplicarlos.
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

DEFAULT_SRC = "https://inmahernandez.github.io/calendar-master/calendar.json"


def load(src):
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=30) as r:
            return json.load(r)
    with open(src, encoding="utf-8") as f:
        return json.load(f)


def parse_date(s):
    d, m, y = s.split("/")
    return datetime(int(y), int(m), int(d)).date()


def esc(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def fold(line):
    """Pliega líneas a 75 octetos como exige RFC 5545."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        limit = 75 if not out else 74
        if size + n > limit:
            out.append(cur)
            cur, size = ch, n
        else:
            cur += ch
            size += n
    out.append(cur)
    return "\r\n ".join(out)


def event(uid_seed, day, summary, description="", location=""):
    uid = hashlib.sha1(uid_seed.encode("utf-8")).hexdigest() + "@calendar-master"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{esc(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{esc(description)}")
    if location:
        lines.append(f"LOCATION:{esc(location)}")
    lines.append("TRANSP:TRANSPARENT")
    lines.append("END:VEVENT")
    return lines


def build(data, subjects=None, holidays=True):
    cal = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//calendar-master//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Máster 2024/25",
        "X-WR-TIMEZONE:Europe/Madrid",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for s in data.get("subjects", []):
        sid = s["id"]
        # Se filtra por id de asignatura O por itinerario (path)
        if subjects and sid not in subjects and s.get("path") not in subjects:
            continue
        name = s.get("name", sid)
        for l in s.get("lectures", []):
            room = l.get("room", "")
            cal += event(f"lec|{sid}|{l['date']}|{room}", parse_date(l["date"]),
                         f"{sid} - {room}".strip(" -"), name, room)
        for e in s.get("exams", []):
            room = e.get("room", "")
            desc = " · ".join(x for x in (name, e.get("desc", "")) if x)
            cal += event(f"exam|{sid}|{e['date']}|{room}", parse_date(e["date"]),
                         f"EXAMEN {sid}" + (f" - {room}" if room else ""), desc, room)
    if holidays:
        for h in data.get("bankHolidays", []):
            cal += event(f"hol|{h['date']}|{h.get('desc','')}", parse_date(h["date"]),
                         f"Festivo: {h.get('desc','')}".strip())
    for sp in data.get("special", []):
        cal += event(f"spe|{sp['date']}|{sp.get('desc','')}", parse_date(sp["date"]),
                     sp.get("desc", "Evento"))
    cal.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in cal) + "\r\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", default=DEFAULT_SRC)
    ap.add_argument("output", nargs="?", default="calendar.ics")
    ap.add_argument("--subjects", help="IDs separados por comas, p. ej. GTI,IC")
    ap.add_argument("--no-holidays", action="store_true")
    ap.add_argument("--list", action="store_true", help="lista asignaturas e IDs y sale")
    a = ap.parse_args()

    data = load(a.source)
    if a.list:
        for s in data.get("subjects", []):
            print(f"id={s['id']}  itinerario={s.get('path')}  nombre={s.get('name')}  "
                  f"clases={len(s.get('lectures', []))}  examenes={len(s.get('exams', []))}")
        return
    subjects = set(x.strip() for x in a.subjects.split(",")) if a.subjects else None
    if subjects:
        known = {s["id"] for s in data.get("subjects", [])} | \
                {s.get("path") for s in data.get("subjects", [])}
        missing = subjects - known
        if missing:
            sys.exit(f"ERROR: no existen estos IDs en el JSON: {', '.join(sorted(missing))}. "
                     f"Usa --list para ver los disponibles.")
    ics = build(data, subjects, not a.no_holidays)
    with open(a.output, "w", encoding="utf-8", newline="") as f:
        f.write(ics)
    print(f"OK: {ics.count('BEGIN:VEVENT')} eventos -> {a.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
