"""Lance la plateforme F1 : python lancer.py  (ou double-clic sur Lancer_plateforme.bat).

- installe les bibliothèques manquantes (une seule fois) ;
- démarre le site et ouvre le navigateur sur http://localhost:8501 ;
- pour ARRÊTER : bouton « Arrêter la plateforme » dans le site, ou fermer cette fenêtre, ou Ctrl + C.
"""
import importlib.util
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = "http://localhost:8501"
NEEDED = ["streamlit", "altair", "pandas", "scipy", "sklearn", "matplotlib", "jinja2"]


def install_if_needed() -> None:
    missing = [m for m in NEEDED if importlib.util.find_spec(m) is None]
    if missing:
        print(f"Installation des bibliothèques manquantes ({', '.join(missing)}), une seule fois...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements-local.txt")])


def wait_until_up(timeout: float = 90) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            # sans proxy : le site tourne sur ton propre ordinateur
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(URL + "/_stcore/health", timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def main() -> None:
    install_if_needed()
    if not (ROOT / "reports" / "results" / "meta.json").exists():
        print("Premier lancement : téléchargement des données et calcul (environ 10 minutes)...")
        subprocess.check_call([sys.executable, str(ROOT / "src" / "main.py")], cwd=ROOT)
    print("Démarrage de la plateforme...")
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
                             "--server.headless", "true", "--browser.gatherUsageStats", "false"], cwd=ROOT)
    if wait_until_up():
        webbrowser.open(URL)
        print(f"\nLa plateforme est ouverte : {URL}")
        print("Si le navigateur ne s'est pas ouvert, copie cette adresse dans ton navigateur.")
        print("Pour ARRÊTER : bouton « Arrêter la plateforme » dans le site, ou ferme cette fenêtre.\n")
    else:
        print("Le site ne répond pas. Regarde les messages d'erreur ci-dessus.")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
    print("Plateforme arrêtée.")


if __name__ == "__main__":
    main()
