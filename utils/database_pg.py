import hashlib
import hmac
import os
from contextlib import contextmanager
from datetime import datetime

import psycopg2
from psycopg2 import errors, pool
from psycopg2.extras import RealDictCursor


class GestionnaireBDPostgreSQL:
    """Gestionnaire PostgreSQL compatible avec l'interface SQLite du projet Usine Connectée."""

    def __init__(
        self,
        host=None,
        port=None,
        dbname=None,
        user=None,
        password=None,
        minconn=1,
        maxconn=10,
    ):
        self.config = {
            "host": host or os.getenv("PGHOST", "localhost"),
            "port": int(port or os.getenv("PGPORT", 5432)),
            "dbname": dbname or os.getenv("PGDATABASE", "usine_connectee"),
            "user": user or os.getenv("PGUSER", "usine_admin"),
            "password": password or os.getenv("PGPASSWORD", "usine_pass"),
        }
        self._pool = pool.ThreadedConnectionPool(minconn, maxconn, **self.config)
        self.initialiser_tables()

    @contextmanager
    def _connecter(self):
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def fermer(self):
        if self._pool:
            self._pool.closeall()

    @staticmethod
    def _formater_ligne(ligne):
        """Convertit un RealDictRow en dict standard avec horodatage formaté comme SQLite."""
        if ligne is None:
            return None
        d = dict(ligne)
        if "date_heure" in d and isinstance(d["date_heure"], datetime):
            d["date_heure"] = d["date_heure"].strftime("%Y-%m-%d %H:%M:%S")
        return d

    def initialiser_tables(self):
        with self._connecter() as conn:
            with conn.cursor() as curseur:
                # 1. Utilisateurs
                curseur.execute("""
                    CREATE TABLE IF NOT EXISTS utilisateurs (
                        id SERIAL PRIMARY KEY,
                        nom_utilisateur VARCHAR(100) UNIQUE NOT NULL,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        mot_de_passe TEXT NOT NULL,
                        role VARCHAR(50) DEFAULT 'operateur'
                    )
                """)

                # 2. Historique des connexions web
                curseur.execute("""
                    CREATE TABLE IF NOT EXISTS connexions_web (
                        id SERIAL PRIMARY KEY,
                        utilisateur_id INTEGER NOT NULL
                            REFERENCES utilisateurs(id) ON DELETE CASCADE,
                        date_heure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        adresse_ip VARCHAR(45)
                    )
                """)

                # 3. Télémétrie des capteurs
                curseur.execute("""
                    CREATE TABLE IF NOT EXISTS mesures_capteurs (
                        id SERIAL PRIMARY KEY,
                        date_heure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        temperature DOUBLE PRECISION,
                        humidite DOUBLE PRECISION,
                        luminosite INTEGER
                    )
                """)

                # 4. Liste blanche des badges RFID
                curseur.execute("""
                    CREATE TABLE IF NOT EXISTS badges_rfid (
                        id SERIAL PRIMARY KEY,
                        uid VARCHAR(64) UNIQUE NOT NULL,
                        proprietaire VARCHAR(100) NOT NULL,
                        actif SMALLINT DEFAULT 1 CHECK (actif IN (0, 1))
                    )
                """)

                # 5. Historique des passages RFID
                curseur.execute("""
                    CREATE TABLE IF NOT EXISTS journaux_acces (
                        id SERIAL PRIMARY KEY,
                        date_heure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        badge_uid VARCHAR(64) NOT NULL,
                        autorise SMALLINT NOT NULL CHECK (autorise IN (0, 1))
                    )
                """)

                # 6. Événements et alertes système
                curseur.execute("""
                    CREATE TABLE IF NOT EXISTS evenements_systeme (
                        id SERIAL PRIMARY KEY,
                        date_heure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        type_evenement VARCHAR(100) NOT NULL,
                        description TEXT,
                        resolu SMALLINT DEFAULT 0 CHECK (resolu IN (0, 1))
                    )
                """)

                # Indexation pour accélérer les requêtes historiques et tableaux de bord
                curseur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mesures_date ON mesures_capteurs (date_heure DESC);"
                )
                curseur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_acces_date ON journaux_acces (date_heure DESC);"
                )
                curseur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_acces_uid ON journaux_acces (badge_uid);"
                )
                curseur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_resolu ON evenements_systeme (resolu, date_heure DESC);"
                )

    # ==========================================
    # GESTION WEB & UTILISATEURS
    # ==========================================

    @staticmethod
    def _hacher_mdp(mot_de_passe, sel=None):
        if sel is None:
            sel = os.urandom(16)
        cle = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), sel, 100000)
        return sel.hex() + ":" + cle.hex()

    @staticmethod
    def _verifier_mdp(mot_de_passe, hash_stocke):
        sel_hex, _ = hash_stocke.split(":")
        candidat = GestionnaireBDPostgreSQL._hacher_mdp(
            mot_de_passe, bytes.fromhex(sel_hex)
        )
        return hmac.compare_digest(candidat, hash_stocke)

    def creer_utilisateur(self, nom_utilisateur, email, mot_de_passe, role="operateur"):
        mdp_hash = self._hacher_mdp(mot_de_passe)
        try:
            with self._connecter() as conn:
                with conn.cursor() as curseur:
                    curseur.execute(
                        """
                        INSERT INTO utilisateurs (nom_utilisateur, email, mot_de_passe, role)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (nom_utilisateur, email, mdp_hash, role),
                    )
            return True
        except errors.UniqueViolation:
            return False

    def authentifier_utilisateur(
        self, nom_utilisateur, mot_de_passe, adresse_ip="0.0.0.0"
    ):
        with self._connecter() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as curseur:
                curseur.execute(
                    "SELECT * FROM utilisateurs WHERE nom_utilisateur = %s",
                    (nom_utilisateur,),
                )
                user = curseur.fetchone()

                if user and self._verifier_mdp(mot_de_passe, user["mot_de_passe"]):
                    curseur.execute(
                        """
                        INSERT INTO connexions_web (utilisateur_id, date_heure, adresse_ip)
                        VALUES (%s, %s, %s)
                        """,
                        (user["id"], datetime.now(), adresse_ip),
                    )
                    return self._formater_ligne(user)
        return None

    # ==========================================
    # GESTION MATÉRIELLE (CAPTEURS & RFID)
    # ==========================================

    def enregistrer_mesure(self, temperature, humidite, luminosite, date_heure=None):
        with self._connecter() as conn:
            with conn.cursor() as curseur:
                curseur.execute(
                    """
                    INSERT INTO mesures_capteurs (date_heure, temperature, humidite, luminosite)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (date_heure or datetime.now(), temperature, humidite, luminosite),
                )

    def ajouter_badge(self, uid, proprietaire, actif=1):
        with self._connecter() as conn:
            with conn.cursor() as curseur:
                curseur.execute(
                    """
                    INSERT INTO badges_rfid (uid, proprietaire, actif)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (uid) DO UPDATE
                    SET proprietaire = EXCLUDED.proprietaire,
                        actif = EXCLUDED.actif
                    """,
                    (uid, proprietaire, int(bool(actif))),
                )

    def verifier_badge(self, uid):
        with self._connecter() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as curseur:
                curseur.execute(
                    "SELECT proprietaire FROM badges_rfid WHERE uid = %s AND actif = 1",
                    (uid,),
                )
                badge = curseur.fetchone()
                est_autorise = 1 if badge else 0
                curseur.execute(
                    """
                    INSERT INTO journaux_acces (date_heure, badge_uid, autorise)
                    VALUES (%s, %s, %s)
                    """,
                    (datetime.now(), uid, est_autorise),
                )
                return badge["proprietaire"] if badge else None

    def enregistrer_evenement(
        self, type_evenement, description, resolu=0, date_heure=None
    ):
        with self._connecter() as conn:
            with conn.cursor() as curseur:
                curseur.execute(
                    """
                    INSERT INTO evenements_systeme (date_heure, type_evenement, description, resolu)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        date_heure or datetime.now(),
                        type_evenement,
                        description,
                        int(bool(resolu)),
                    ),
                )

    def resoudre_evenement(self, evenement_id):
        with self._connecter() as conn:
            with conn.cursor() as curseur:
                curseur.execute(
                    "UPDATE evenements_systeme SET resolu = 1 WHERE id = %s",
                    (evenement_id,),
                )

    # ==========================================
    # LECTURES & ANALYTIQUE POUR LE TABLEAU DE BORD
    # ==========================================

    def obtenir_dernieres_mesures(self, limite=20):
        with self._connecter() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as curseur:
                curseur.execute(
                    "SELECT * FROM mesures_capteurs ORDER BY id DESC LIMIT %s",
                    (limite,),
                )
                return [self._formater_ligne(r) for r in curseur.fetchall()]

    def obtenir_journaux_acces(self, limite=20):
        with self._connecter() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as curseur:
                curseur.execute(
                    "SELECT * FROM journaux_acces ORDER BY id DESC LIMIT %s",
                    (limite,),
                )
                return [self._formater_ligne(r) for r in curseur.fetchall()]

    def obtenir_evenements(self, limite=20):
        with self._connecter() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as curseur:
                curseur.execute(
                    "SELECT * FROM evenements_systeme ORDER BY id DESC LIMIT %s",
                    (limite,),
                )
                return [self._formater_ligne(r) for r in curseur.fetchall()]

    def obtenir_statistiques_periode(self, heures=24):
        """Agrégation SQL native PostgreSQL pour le reporting industriel."""
        with self._connecter() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as curseur:
                curseur.execute(
                    """
                    SELECT
                        COUNT(*) AS nb_mesures,
                        ROUND(AVG(temperature)::numeric, 2) AS temp_moy,
                        MIN(temperature) AS temp_min,
                        MAX(temperature) AS temp_max,
                        ROUND(AVG(humidite)::numeric, 2) AS hum_moy,
                        ROUND(AVG(luminosite)::numeric, 1) AS lum_moy
                    FROM mesures_capteurs
                    WHERE date_heure >= NOW() - (%s || ' hours')::INTERVAL
                    """,
                    (heures,),
                )
                return dict(curseur.fetchone())