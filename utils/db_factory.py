import logging
import os
from pathlib import Path
from dotenv import load_dotenv

from .database_pg import GestionnaireBDPostgreSQL

try:
    from .create_db import GestionnaireBD as GestionnaireBDSQLite
except ImportError:
    GestionnaireBDSQLite = None

load_dotenv()
logger = logging.getLogger(__name__)

RACINE_PROJET = Path(__file__).resolve().parent.parent
DEFAUT_SQLITE = RACINE_PROJET / "data" / "usine.db"


def obtenir_gestionnaire_bd(moteur=None, fallback_sqlite=True):
    """
    Point d'entrée unifié SQLite / PostgreSQL pour Next_factory.
    Basculable via la variable d'environnement DB_ENGINE ('postgresql' ou 'sqlite').
    """
    choix = (moteur or os.getenv("DB_ENGINE", "postgresql")).strip().lower()
    chemin_sqlite = Path(os.getenv("SQLITE_PATH", str(DEFAUT_SQLITE)))

    if choix in ("pg", "postgres", "postgresql"):
        try:
            bd = GestionnaireBDPostgreSQL()
            logger.info("Connexion PostgreSQL active (%s).", bd.config["host"])
            return bd
        except Exception as err:
            if not fallback_sqlite:
                raise
            logger.warning(
                "PostgreSQL indisponible (%s). Bascule sur SQLite (%s).",
                err,
                chemin_sqlite,
            )

    if GestionnaireBDSQLite is None:
        raise RuntimeError(
            "Le module SQLite (utils/create_db.py) n'est pas encore présent sur cette branche."
        )

    chemin_sqlite.parent.mkdir(parents=True, exist_ok=True)
    return GestionnaireBDSQLite(nom_bd=str(chemin_sqlite))