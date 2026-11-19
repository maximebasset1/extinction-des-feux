"""Étape 1 (data engineer) : télécharger qualifications et essais libres.

Usage : python src/fetch_data.py            (tout)
        python src/fetch_data.py --target   (seulement le week-end à prédire, pour suivre les essais)
Un fichier déjà téléchargé n'est pas retéléchargé, sauf ceux du week-end cible (mis à jour pendant le week-end).
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import BASE_URL, DATA_RAW, SESSIONS, TARGET_GP, TARGET_HISTORY, TARGET_SEASON, seasons_to_fetch  # noqa: E402


def local_path(season: int, *parts: str) -> Path:
    return DATA_RAW.joinpath(str(season), *parts)


def download(job: tuple) -> str:
    season, parts, refresh = job
    dest = local_path(season, *parts)
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return "cache"
    url = BASE_URL.format(season=season) + "/" + "/".join(urllib.parse.quote(p) for p in parts)
    last = ""
    for attempt in range(4):  # le serveur peut limiter le débit (429) : on attend puis on réessaie
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return "absent"
            last = f"erreur {exc}"
            wait = int(exc.headers.get("Retry-After", 0) or 0) if exc.code == 429 else 0
        except Exception as exc:  # réseau
            last, wait = f"erreur {exc}", 0
        time.sleep(max(wait, 2 ** attempt * 3))
    else:
        return last
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)  # jamais de fichier à moitié écrit
    return "ok"


def jobs_for(calendar: dict, sessions: list, refresh: bool) -> list:
    # 1) liste des pilotes de chaque session
    head = [(s, (gp, ses, "drivers.json"), refresh) for s, gps in calendar.items() for gp in gps for ses in sessions]
    head += [(s, (gp, ses, "session_info.json"), refresh) for s, gps in calendar.items() for gp in gps for ses in sessions]
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(download, head))
    # 2) un fichier de tours par pilote
    jobs = []
    for s, gps in calendar.items():
        for gp in gps:
            for ses in sessions:
                f = local_path(s, gp, ses, "drivers.json")
                if f.exists():
                    for d in json.loads(f.read_text(encoding="utf-8"))["drivers"]:
                        jobs.append((s, (gp, ses, d["driver"], "laptimes.json"), refresh))
    return jobs


def run(calendar: dict, sessions: list, refresh: bool = False) -> None:
    jobs = jobs_for(calendar, sessions, refresh)
    with ThreadPoolExecutor(8) as pool:
        status = list(pool.map(download, jobs))
    errors = [j for j, st in zip(jobs, status) if st.startswith("erreur")]
    print(f"{len(jobs)} fichiers de tours : {len(jobs) - len(errors)} disponibles, {len(errors)} en erreur")
    if errors:
        missing = [j for j in errors if not local_path(j[0], *j[1]).exists()]
        if len(missing) > max(5, 0.02 * len(jobs)):
            sys.exit(f"Trop de fichiers manquants ({len(missing)}) : calcul arrêté pour ne pas publier "
                     "des pronostics faux. Relance plus tard.")


def previous_race() -> str | None:
    """Course du calendrier juste avant la cible (même saison), si elle est connue."""
    import json
    from config import CALENDAR_FILE
    if not CALENDAR_FILE.exists():
        return None
    races = json.loads(CALENDAR_FILE.read_text(encoding="utf-8")).get(str(TARGET_SEASON), [])
    races = sorted((r for r in races if "R" in r.get("sessions", {})), key=lambda r: r["sessions"]["R"])
    names = [r["gp"] for r in races]
    if TARGET_GP in names and names.index(TARGET_GP) > 0:
        return names[names.index(TARGET_GP) - 1]
    return None


def main(target_only: bool = False) -> None:
    target = {TARGET_SEASON: [TARGET_GP]}
    if not target_only:
        history = {s: [g for g in gps if not (s == TARGET_SEASON and g == TARGET_GP)]
                   for s, gps in seasons_to_fetch().items()}
        run(history, SESSIONS)
        if TARGET_HISTORY:
            run(TARGET_HISTORY, ["Qualifying"])
    prev = previous_race()
    if prev:  # la course qui vient de se terminer : ses fichiers peuvent encore être complétés
        print(f"Course précédente ({prev}) : mise à jour")
        run({TARGET_SEASON: [prev]}, SESSIONS, refresh=True)
    print(f"Week-end cible ({TARGET_GP} {TARGET_SEASON}) :")
    run(target, SESSIONS, refresh=True)
    done = [s for s in SESSIONS if any(local_path(TARGET_SEASON, TARGET_GP, s).glob("*/laptimes.json"))]
    print("   sessions déjà disponibles :", ", ".join(done) if done else "aucune")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="store_true", help="seulement le week-end cible")
    main(ap.parse_args().target)
