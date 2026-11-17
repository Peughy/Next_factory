import sqlite3
import hashlib
import os
from datetime import datetime


class GestionnaireBD:
    def __init__(self, nom_bd="../data/usine.db"):
        self.nom_bd = nom_bd
        self.initialiser_tables()

    def _connecter(self):
        conn = sqlite3.connect(self.nom_bd, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def initialiser_tables(self):
        with self._connecter() as conn:
            curseur = conn.cursor()

            # 1. Utilisateurs
            curseur.execute("""
                CREATE TABLE IF NOT EXISTS utilisateurs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom_utilisateur TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    mot_de_passe TEXT NOT NULL,
                    role TEXT DEFAULT 'operateur'
                )
            """)

            # 2. Historique des connexions web
            curseur.execute("""
                CREATE TABLE IF NOT EXISTS connexions_web (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    utilisateur_id INTEGER NOT NULL,
                    date_heure DATETIME DEFAULT CURRENT_TIMESTAMP,
                    adresse_ip TEXT,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id) ON DELETE CASCADE
                )
            """)

            # 3. Télémétrie des capteurs
            curseur.execute("""
                CREATE TABLE IF NOT EXISTS mesures_capteurs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_heure DATETIME DEFAULT CURRENT_TIMESTAMP,
                    temperature REAL,
                    humidite REAL,
                    luminosite INTEGER
                )
            """)

            # 4. Liste blanche des badges RFID
            curseur.execute("""
                CREATE TABLE IF NOT EXISTS badges_rfid (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT UNIQUE NOT NULL,
                    proprietaire TEXT NOT NULL,
                    actif INTEGER DEFAULT 1
                )
            """)

            # 5. Historique des passages RFID
            curseur.execute("""
                CREATE TABLE IF NOT EXISTS journaux_acces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_heure DATETIME DEFAULT CURRENT_TIMESTAMP,
                    badge_uid TEXT NOT NULL,
                    autorise INTEGER NOT NULL
                )
            """)

            # 6. Événements et alertes système
            curseur.execute("""
                CREATE TABLE IF NOT EXISTS evenements_systeme (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_heure DATETIME DEFAULT CURRENT_TIMESTAMP,
                    type_evenement TEXT NOT NULL,
                    description TEXT,
                    resolu INTEGER DEFAULT 0
                )
            """)

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
        sel_hex, cle_hex = hash_stocke.split(":")
        return (
            GestionnaireBD._hacher_mdp(mot_de_passe, bytes.fromhex(sel_hex))
            == hash_stocke
        )

    def creer_utilisateur(self, nom_utilisateur, email, mot_de_passe, role="operateur"):
        mdp_hash = self._hacher_mdp(mot_de_passe)
        try:
            with self._connecter() as conn:
                conn.execute(
                    "INSERT INTO utilisateurs (nom_utilisateur, email, mot_de_passe, role) VALUES (?, ?, ?, ?)",
                    (nom_utilisateur, email, mdp_hash, role),
                )
            return True
        except sqlite3.IntegrityError:
            return False  # Nom d'utilisateur ou email déjà existant

    def authentifier_utilisateur(
        self, nom_utilisateur, mot_de_passe, adresse_ip="0.0.0.0"
    ):
        with self._connecter() as conn:
            user = conn.execute(
                "SELECT * FROM utilisateurs WHERE nom_utilisateur = ?",
                (nom_utilisateur,),
            ).fetchone()

            if user and self._verifier_mdp(mot_de_passe, user["mot_de_passe"]):
                conn.execute(
                    "INSERT INTO connexions_web (utilisateur_id, date_heure, adresse_ip) VALUES (?, ?, ?)",
                    (
                        user["id"],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        adresse_ip,
                    ),
                )
                return dict(user)
        return None

    # ==========================================
    # GESTION MATÉRIELLE (CAPTEURS & RFID)
    # ==========================================

    def enregistrer_mesure(self, temperature, humidite, luminosite):
        with self._connecter() as conn:
            conn.execute(
                "INSERT INTO mesures_capteurs (date_heure, temperature, humidite, luminosite) VALUES (?, ?, ?, ?)",
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    temperature,
                    humidite,
                    luminosite,
                ),
            )

    def ajouter_badge(self, uid, proprietaire, actif=1):
        with self._connecter() as conn:
            conn.execute(
                """INSERT INTO badges_rfid (uid, proprietaire, actif) VALUES (?, ?, ?)
                   ON CONFLICT(uid) DO UPDATE SET proprietaire=excluded.proprietaire, actif=excluded.actif""",
                (uid, proprietaire, actif),
            )

    def verifier_badge(self, uid):
        """Vérifie le badge, journalise le passage et renvoie le nom du propriétaire (ou None)."""
        with self._connecter() as conn:
            badge = conn.execute(
                "SELECT proprietaire FROM badges_rfid WHERE uid = ? AND actif = 1",
                (uid,),
            ).fetchone()

            est_autorise = 1 if badge else 0
            conn.execute(
                "INSERT INTO journaux_acces (date_heure, badge_uid, autorise) VALUES (?, ?, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), uid, est_autorise),
            )
            return badge["proprietaire"] if badge else None

    def enregistrer_evenement(self, type_evenement, description, resolu=0):
        with self._connecter() as conn:
            conn.execute(
                "INSERT INTO evenements_systeme (date_heure, type_evenement, description, resolu) VALUES (?, ?, ?, ?)",
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    type_evenement,
                    description,
                    resolu,
                ),
            )

    # ==========================================
    # LECTURES POUR LE TABLEAU DE BORD WEB
    # ==========================================

    def obtenir_dernieres_mesures(self, limite=20):
        with self._connecter() as conn:
            lignes = conn.execute(
                "SELECT * FROM mesures_capteurs ORDER BY id DESC LIMIT ?", (limite,)
            ).fetchall()
            return [dict(ligne) for ligne in lignes]

    def obtenir_journaux_acces(self, limite=20):
        with self._connecter() as conn:
            lignes = conn.execute(
                "SELECT * FROM journaux_acces ORDER BY id DESC LIMIT ?", (limite,)
            ).fetchall()
            return [dict(ligne) for ligne in lignes]

    def obtenir_evenements(self, limite=20):
        with self._connecter() as conn:
            lignes = conn.execute(
                "SELECT * FROM evenements_systeme ORDER BY id DESC LIMIT ?", (limite,)
            ).fetchall()
            return [dict(ligne) for ligne in lignes]


# ==========================================
# TEST UNITAIRE RAPIDE
# ==========================================
if __name__ == "__main__":
    bd = GestionnaireBD()
    bd.creer_utilisateur("admin", "admin@usine.local", "admin123", role="admin")
    print("✅ Base initialisée avec un compte admin et un badge de test.")
