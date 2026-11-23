import pytest
from utils.traitement_donnees import TraitementDonnees


class BDMemoireStub:
    """Stub respectant le contrat exact de utils/create_db.py et utils/database_pg.py."""

    def __init__(self):
        self.mesures = []
        self.evenements = []

    def enregistrer_mesure(self, temperature, humidite, luminosite):
        self.mesures.append(
            {"temperature": temperature, "humidite": humidite, "luminosite": luminosite}
        )

    def enregistrer_evenement(self, type_evenement, description, resolu=0):
        self.evenements.append(
            {"type_evenement": type_evenement, "description": description, "resolu": resolu}
        )


def test_alerte_incendie_et_ordre_arduino():
    bd = BDMemoireStub()
    pipe = TraitementDonnees(bd, seuil_temp_max=45.0, cooldown_alerte_sec=0)
    res = pipe.traiter_mesure(51.2, 42.0, "742", fumee_detectee=True)

    assert res["valide"] is True
    assert "ALERTE_INCENDIE" in res["alertes"]
    assert "TEMPERATURE_CRITIQUE" in res["alertes"]
    assert res["commandes"]["ordre_arduino"] == b"A"
    assert res["commandes"]["ouvrir_porte_urgence"] is True
    assert res["commandes"]["eclairage_nuit"] is True
    assert bd.mesures[0]["luminosite"] == 742


def test_gestion_luminosite_na_et_rejet_dht():
    bd = BDMemoireStub()
    pipe = TraitementDonnees(bd)

    res_ok = pipe.traiter_mesure(22.5, 50.0, "N/A", fumee_detectee=False)
    assert res_ok["valide"] is True
    assert res_ok["commandes"]["ordre_arduino"] == b"N"
    assert bd.mesures[0]["luminosite"] is None

    res_ko = pipe.traiter_mesure(999.0, 50.0, "300")
    assert res_ko["valide"] is False
    assert len(bd.mesures) == 1