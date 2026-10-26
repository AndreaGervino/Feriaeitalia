"""Recalculate transfer_* columns in ski_finder_data.csv with OSRM driving routes.

OSRM duration x 1.1 (winter), rounded to nearest 5 min, blank if > 360.
Usage: python3 osrm_transfers.py ski_finder_data.csv
"""
import csv, json, sys, time, urllib.request

AIRPORTS = {"TRN": (45.2008, 7.6496), "MXP": (45.6306, 8.7281), "BGY": (45.6739, 9.7042),
            "VRN": (45.3957, 10.8885), "VCE": (45.5053, 12.3519), "INN": (47.2602, 11.3439)}
# lat, lon as stored on each ski area page
COORDS = {
 "alagna-valsesia": (45.85, 7.933), "aprica": (46.154, 10.152), "artesina": (44.2473, 7.7566),
 "bardonecchia": (45.067, 6.7), "bormio": (46.468, 10.372), "campitello-di-fassa": (46.4722, 11.7392),
 "canazei": (46.4769, 11.7694), "cervinia": (45.933, 7.633), "cesana-torinese": (44.954, 6.778),
 "champoluc": (45.826, 7.726), "cima-piazzi-san-colombano": (46.47218, 10.32136), "claviere": (44.933, 6.75),
 "colfosco": (46.5544, 11.8536), "corvara": (46.5526, 11.8743), "folgaria": (45.9165, 11.1704),
 "folgarida-marilleva": (46.29841, 10.866374), "foppolo-carona": (46.036, 9.712), "frabosa-soprana": (44.2872, 7.8069),
 "gressoney": (45.831, 7.819), "la-thuile": (45.717, 6.9488), "la-villa": (46.5834, 11.9047),
 "lavarone": (45.9394, 11.27457), "limone-piemonte": (44.201, 7.572), "livigno": (46.539, 10.135),
 "madesimo": (46.443, 9.334), "madonna-di-campiglio": (46.2306, 10.8258), "moena": (46.3775, 11.6617),
 "monte-bondone": (45.98806, 11.03083), "ortisei": (46.5758, 11.6761), "paganella": (46.1667, 11.0167),
 "panarotta": (46.05001, 11.33446), "pejo": (46.3597, 10.6867), "piani-di-bobbio": (45.933, 9.456),
 "pila": (45.6889, 7.3082), "pinzolo": (46.1594, 10.7664), "ponte-di-legno-tonale": (46.259, 10.509),
 "pozza-di-fassa": (46.4303, 11.6839), "prali": (44.8893, 7.0489), "prato-nevoso": (44.2569, 7.7889),
 "san-cassiano": (46.5700687, 11.93606), "san-martino-di-castrozza": (46.2583, 11.8), "sansicario": (44.9585, 6.8066),
 "santa-caterina-valfurva": (46.4139, 10.4917), "santa-cristina-val-gardena": (46.5589, 11.7267),
 "sauze-d-oulx": (45.033, 6.85), "selva-di-val-gardena": (46.5553, 11.7558), "sestriere": (44.9569, 6.8781),
 "torgnon": (45.8026, 7.5709), "vigo-di-fassa": (46.4181, 11.6725),
}

# Stored coordinates that snap onto slow tracks: route to the village road instead.
END_OVERRIDE = {
    "bardonecchia": ((45.069627, 6.71135), "stored point snaps onto Strada del Colomion track (+68 min); routed to the town end of that track instead"),
    "claviere": ((44.9386, 6.7525), "stored point is on the slopes and routes via a track (+26 min); routed to Claviere village on the SS24 instead"),
}
# Force winter-open roads where OSRM picks passes closed in winter.
TIRANO = (46.2155, 10.1689)      # avoids Passo del Mortirolo
LIVIGNO = (46.539, 10.135)       # INN via Munt la Schera tunnel, then Foscagno (avoids Umbrail/Stelvio)
FOSCAGNO = (46.4848, 10.2205)    # Livigno from the south via Bormio and Foscagno (avoids Forcola di Livigno)
CHIAVENNA = (46.3215, 9.3985)    # avoids Spluga
WAYPOINTS = {}
for s_ in ("bormio", "cima-piazzi-san-colombano", "santa-caterina-valfurva"):
    for a in ("BGY", "VRN", "VCE"):
        WAYPOINTS[(s_, a)] = ([TIRANO], "via Tirano (Mortirolo closed in winter)")
    WAYPOINTS[(s_, "INN")] = ([LIVIGNO, FOSCAGNO], "via Munt la Schera tunnel, Livigno and Foscagno (Umbrail/Stelvio closed in winter)")
WAYPOINTS[("aprica", "INN")] = ([LIVIGNO, FOSCAGNO, TIRANO], "via Livigno, Bormio and Tirano (Umbrail/Stelvio closed in winter)")
for a in ("TRN", "MXP", "BGY", "VRN", "VCE"):
    WAYPOINTS[("livigno", a)] = ([TIRANO, FOSCAGNO], "via Tirano, Bormio and Foscagno (Forcola di Livigno closed in winter)")
for a in ("MXP", "INN"):
    WAYPOINTS[("madesimo", a)] = ([CHIAVENNA], "via Chiavenna (Spluga closed in winter)")

def route(points):
    coords = ";".join(f"{lon},{lat}" for lat, lon in points)
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=false"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.load(r)
            if d.get("code") == "Ok":
                return d["routes"][0]["duration"]
        except Exception as e:
            err = e
        time.sleep(2 ** (attempt + 1))
    raise SystemExit(f"OSRM route failed: {err}")

def table():
    # one OSRM table call: 6 airport sources x 49 destinations
    slugs = list(COORDS)
    pts = list(AIRPORTS.values()) + [END_OVERRIDE.get(s, (COORDS[s],))[0] for s in slugs]
    coords = ";".join(f"{lon},{lat}" for lat, lon in pts)
    src = ";".join(str(i) for i in range(len(AIRPORTS)))
    dst = ";".join(str(i) for i in range(len(AIRPORTS), len(pts)))
    url = f"https://router.project-osrm.org/table/v1/driving/{coords}?sources={src}&destinations={dst}&annotations=duration"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.load(r)
            if d.get("code") == "Ok":
                return slugs, d["durations"]
        except Exception as e:
            err = e
        time.sleep(2 ** (attempt + 1))
    raise SystemExit(f"OSRM failed: {err}")

def main(path):
    slugs, dur = table()
    for (s, a), (via, _) in WAYPOINTS.items():
        j, i = slugs.index(s), list(AIRPORTS).index(a)
        dur[i][j] = route([AIRPORTS[a], *via, END_OVERRIDE.get(s, (COORDS[s],))[0]])
        time.sleep(1)
    res = {}
    for j, s in enumerate(slugs):
        res[s] = {}
        for i, a in enumerate(AIRPORTS):
            sec = dur[i][j]
            if sec is None:
                res[s][a] = ""
                continue
            m = 5 * round(sec * 1.1 / 60 / 5)
            res[s][a] = "" if m > 360 else m
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    old = "Transfers: NOT yet recalculated with OSRM (router.project-osrm.org still blocked by this session's network policy) - these are the earlier manual estimates."
    new = "Transfers: OSRM driving duration x1.1 for winter, rounded to 5 min; blank if over 360."
    for r in rows:
        for a in AIRPORTS:
            r[f"transfer_{a}"] = res[r["slug"]][a]
        extra = []
        if r["slug"] in END_OVERRIDE:
            extra.append(END_OVERRIDE[r["slug"]][1])
        extra += [f"{a} {why}" for (sl, a), (_, why) in WAYPOINTS.items() if sl == r["slug"]]
        n = new + (" Routing fixes: " + "; ".join(extra) + "." if extra else "")
        r["notes"] = r["notes"].replace(old, n)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("updated", len(rows))

if __name__ == "__main__":
    main(sys.argv[1])
