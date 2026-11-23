import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from .database_pg import GestionnaireBDPostgreSQL

load_dotenv()
DEFAUT_SQLITE = Path(__file__).resolve().parent.parent / "data" / "usine.db"


def synchroniser_sqlite_vers_pg(chemin_sqlite=None):
    chemin = Path(chemin_sqlite) if chemin_sqlite else DEFAUT_SQLITE
    if not chemin.exists():
        raise FileNotFoundError(f"Base SQLite introuvable : {chemin}")

    pg = GestionnaireBDPostgreSQL()
    sq = sqlite3.connect(str(chemin))
    sq.row_factory = sqlite3.Row

    stats = {"utilisateurs": 0, "badges": 0, "mesures": 0, "acces": 0, "evenements": 0}

    with pg._connecter() as conn_pg:
        cur_pg = conn_pg.cursor()

        for row in sq.execute("SELECT nom_utilisateur, email, mot_de_passe, role FROM utilisateurs"):
            cur_pg.execute(
                """
                INSERT INTO utilisateurs (nom_utilisateur, email, mot_de_passe, role)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (nom_utilisateur) DO NOTHING
                """,
                (row["nom_utilisateur"], row["email"], row["mot_de_passe"], row["role"]),
            )
            stats["utilisateurs"] += cur_pg.rowcount

        for row in sq.execute("SELECT uid, proprietaire, actif FROM badges_rfid"):
            cur_pg.execute(
                """
                INSERT INTO badges_rfid (uid, proprietaire, actif)
                VALUES (%s, %s, %s)
                ON CONFLICT (uid) DO UPDATE
                SET proprietaire = EXCLUDED.proprietaire, actif = EXCLUDED.actif
                """,
                (row["uid"], row["proprietaire"], row["actif"]),
            )
            stats["badges"] += 1

        for table, cols in [
            ("mesures_capteurs", ("date_heure", "temperature", "humidite", "luminosite")),
            ("journaux_acces", ("date_heure", "badge_uid", "autorise")),
            ("evenements_systeme", ("date_heure", "type_evenement", "description", "resolu")),
        ]:
            cur_pg.execute(f"SELECT MAX(date_heure) FROM {table}")
            derniere = cur_pg.fetchone()[0]
            filtre = str(derniere) if derniere else "1970-01-01 00:00:00"
            col_sql = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))

            cle_stat = {"mesures_capteurs": "mesures", "journaux_acces": "acces", "evenements_systeme": "evenements"}[table]
            for row in sq.execute(f"SELECT {col_sql} FROM {table} WHERE date_heure > ?", (filtre,)):
                cur_pg.execute(
                    f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})",
                    tuple(row[c] for c in cols),
                )
                stats[cle_stat] += 1

    sq.close()
    pg.fermer()
    return stats


if __name__ == "__main__":
    print(f"Synchronisation terminée : {synchroniser_sqlite_vers_pg()}")