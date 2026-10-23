"""Testy trvalého ukládání nastavení (QSettings → INI soubor)."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

import uloziste
from game_logic import NastaveniHry


def _nastaveni_ini(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "nastaveni.ini"), QSettings.Format.IniFormat)


def test_kolo_zapis_a_cteni(tmp_path):
    s = _nastaveni_ini(tmp_path)
    nastaveni = NastaveniHry(
        tonina="Fis", oktava=3, delka_sekvence=7, pocet_pokusu=5,
        interval_statistik=9, odmena_po_kolech=3, absolutni_sluch=True,
        id_smutne_melodie="dlouhy_smutny",
        id_vitezne_melodie="slavnostni",
    )
    uloziste.uloz_nastaveni(nastaveni, s)
    nacteno = uloziste.nacti_nastaveni(s)
    assert nacteno == nastaveni
    assert nacteno.tonina == "Fis"
    assert nacteno.odmena_po_kolech == 3
    assert nacteno.absolutni_sluch is True
    assert nacteno.id_vitezne_melodie == "slavnostni"


def test_soubor_existuje_a_je_citelny(tmp_path):
    s = _nastaveni_ini(tmp_path)
    uloziste.uloz_nastaveni(NastaveniHry(tonina="Es"), s)
    obsah = (tmp_path / "nastaveni.ini").read_text(encoding="utf-8")
    assert "Es" in obsah


def test_prazdne_nastaveni_dava_vychozi(tmp_path):
    s = _nastaveni_ini(tmp_path)
    nacteno = uloziste.nacti_nastaveni(s)
    assert nacteno == uloziste.vychozi_nastaveni()


def test_neplatna_tonina_se_odhodi_na_vychozi(tmp_path):
    s = _nastaveni_ini(tmp_path)
    s.setValue("tonina", "XYZ")
    s.setValue("oktava", 99)
    s.sync()
    nacteno = uloziste.nacti_nastaveni(s)
    assert nacteno == uloziste.vychozi_nastaveni()


def test_neplatne_cislo_se_odhodi_na_vychozi(tmp_path):
    s = _nastaveni_ini(tmp_path)
    s.setValue("pocet_pokusu", "abc")
    s.sync()
    nacteno = uloziste.nacti_nastaveni(s)
    assert nacteno.pocet_pokusu == uloziste.vychozi_nastaveni().pocet_pokusu


def test_nastaveni_je_skutecne_na_disku(tmp_path):
    """Druhá instance QSettings (nové načtení) musí vidět uložená data."""
    s1 = _nastaveni_ini(tmp_path)
    uloziste.uloz_nastaveni(NastaveniHry(tonina="B", delka_sekvence=9), s1)
    del s1
    s2 = _nastaveni_ini(tmp_path)
    nacteno = uloziste.nacti_nastaveni(s2)
    assert nacteno.tonina == "B"
    assert nacteno.delka_sekvence == 9
