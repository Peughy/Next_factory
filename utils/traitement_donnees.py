import statistics
import time
from collections import deque


class TraitementDonnees:
    """
    Pipeline de validation, stockage et détection d'anomalies pour Next_factory.
    Compatible SQLite (utils/create_db.py) et PostgreSQL (utils/database_pg.py).
    """

    def __init__(
        self,
        bd,
        seuil_temp_max=45.0,
        seuil_temp_min=5.0,
        seuil_humidite_max=80.0,
        seuil_obscurite=600,  # Aligné sur arduino/src/main.cpp (> 600 = sombre)
        fenetre_stats=20,
        seuil_zscore=3.0,
        cooldown_alerte_sec=30.0,
    ):
        self.bd = bd
        self.seuil_temp_max = seuil_temp_max
        self.seuil_temp_min = seuil_temp_min
        self.seuil_humidite_max = seuil_humidite_max
        self.seuil_obscurite = seuil_obscurite
        self.seuil_zscore = seuil_zscore
        self.cooldown_alerte_sec = cooldown_alerte_sec

        self._historique_temp = deque(maxlen=fenetre_stats)
        self._dernieres_alertes = {}

    @staticmethod
    def _normaliser_luminosite(luminosite):
        """Convertit la lecture série Arduino ('742' ou 'N/A') en entier ou None."""
        if luminosite is None or luminosite == "N/A":
            return None
        try:
            val = int(luminosite)
            return val if 0 <= val <= 1023 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _mesure_dht_valide(temperature, humidite):
        """Filtre les lectures corrompues ou nulles du capteur DHT11."""
        if temperature is None or humidite is None:
            return False
        return (-20.0 <= float(temperature) <= 100.0) and (0.0 <= float(humidite) <= 100.0)

    def _peut_journaliser(self, type_evenement):
        maintenant = time.monotonic()
        dernier = self._dernieres_alertes.get(type_evenement, 0.0)
        if maintenant - dernier >= self.cooldown_alerte_sec:
            self._dernieres_alertes[type_evenement] = maintenant
            return True
        return False

    def _detecter_derive_statistique(self, temperature):
        if len(self._historique_temp) < 10:
            return False
        moyenne = statistics.mean(self._historique_temp)
        ecart_type = statistics.stdev(self._historique_temp)
        if ecart_type < 0.2:
            return False
        return (abs(temperature - moyenne) / ecart_type) >= self.seuil_zscore

    def traiter_mesure(self, temperature, humidite, luminosite, fumee_detectee=False):
        """
        Valide, enregistre la trame capteur et retourne les alertes + ordres matériels.
        """
        if not self._mesure_dht_valide(temperature, humidite):
            return {"valide": False, "alertes": ["MESURE_DHT_INVALIDE"], "commandes": {}}

        temp = float(temperature)
        hum = float(humidite)
        lum = self._normaliser_luminosite(luminosite)

        self.bd.enregistrer_mesure(temp, hum, lum)

        alertes = []
        activer_alarme = False

        if fumee_detectee:
            activer_alarme = True
            alertes.append("ALERTE_INCENDIE")
            if self._peut_journaliser("ALERTE_INCENDIE"):
                self.bd.enregistrer_evenement(
                    "ALERTE_INCENDIE",
                    f"Fumée détectée par K869051 sur GPIO 27 (T={temp:.1f}°C).",
                )

        if temp > self.seuil_temp_max or temp < self.seuil_temp_min:
            activer_alarme = True
            alertes.append("TEMPERATURE_CRITIQUE")
            if self._peut_journaliser("TEMPERATURE_CRITIQUE"):
                self.bd.enregistrer_evenement(
                    "TEMPERATURE_CRITIQUE",
                    f"Température hors plage [{self.seuil_temp_min}; {self.seuil_temp_max}]°C : {temp:.1f}°C",
                )
        elif self._detecter_derive_statistique(temp):
            alertes.append("DERIVE_THERMIQUE")
            if self._peut_journaliser("DERIVE_THERMIQUE"):
                self.bd.enregistrer_evenement(
                    "DERIVE_THERMIQUE",
                    f"Variation thermique anormale (Z-score >= {self.seuil_zscore}) : {temp:.1f}°C",
                )

        if hum > self.seuil_humidite_max:
            alertes.append("HUMIDITE_ELEVEE")
            if self._peut_journaliser("HUMIDITE_ELEVEE"):
                self.bd.enregistrer_evenement(
                    "HUMIDITE_ELEVEE",
                    f"Humidité excessive : {hum:.1f}%",
                )

        self._historique_temp.append(temp)

        commandes = {
            "ordre_arduino": b"A" if activer_alarme else b"N",
            "ouvrir_porte_urgence": activer_alarme,
            "eclairage_nuit": (lum is not None and lum > self.seuil_obscurite),
        }

        return {"valide": True, "alertes": alertes, "commandes": commandes}