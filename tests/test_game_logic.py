"""Testy herní logiky — deterministická náhodnost, bez GUI a zvuku."""

from __future__ import annotations

import random

import pytest

import theory
from game_logic import HerniLogika, NastaveniHry, StavKola
from stats import SpravceStatistik


def vytvor(seed: int = 1234, **zmeny) -> HerniLogika:
    nastaveni = NastaveniHry(**zmeny)
    return HerniLogika(nastaveni=nastaveni, rng=random.Random(seed))


def spravny_vstup(log: HerniLogika) -> int:
    return log.sekvence[log.pozice]


def nespravny_vstup(log: HerniLogika) -> int:
    return (log.sekvence[log.pozice] + 1) % 7


# --- Generování sekvence ----------------------------------------------------

@pytest.mark.parametrize("delka", [2, 4, 7, 12])
def test_delka_sekvence(delka):
    log = vytvor(delka_sekvence=delka)
    seq = log.zahaj_kolo()
    assert len(seq) == delka == log.nastaveni.delka_sekvence


def test_vsechny_tony_patri_do_toniny_a_do_tlacitek():
    for tonina in theory.PORADI_TONIN:
        log = vytvor(tonina=tonina, oktava=4, delka_sekvence=12, seed=7)
        log.zahaj_kolo()
        tlacitka_midis = [m for _, m in log.tlacitka()]
        for midi in log.midi_sekvence():
            assert theory.ton_patri_do_toniny(midi, tonina), (tonina, midi)
            assert midi in tlacitka_midis, (tonina, midi)


def test_stupnice_toniny_ma_spravne_nazvy():
    log = vytvor(tonina="Fis", oktava=4)
    nazvy = [n for n, _ in log.tlacitka()]
    assert nazvy == ["Tón Fis, oktáva 4", "Tón Gis, oktáva 4",
                     "Tón Ais, oktáva 4", "Tón H, oktáva 4",
                     "Tón Cis, oktáva 5", "Tón Dis, oktáva 5",
                     "Tón Eis, oktáva 5"]


def test_nahodnost_ale_determinismus_pri_stejnem_seed():
    a = vytvor(seed=42).zahaj_kolo()
    b = vytvor(seed=42).zahaj_kolo()
    c = vytvor(seed=43).zahaj_kolo()
    assert a == b
    assert a != c   # velmi pravděpodobně; kdyby ne, test nic nepokazí


# --- Vyhodnocování vstupů ---------------------------------------------------

def test_spravny_ton_je_spravny():
    log = vytvor()
    log.zahaj_kolo()
    log.sekvence_prehrana()
    v = log.zpracuj_vstup(spravny_vstup(log))
    assert v.prijat and v.spravne is True
    assert v.pokusy_zbyva == log.nastaveni.pocet_pokusu   # pokus se neubral
    assert log.stav is StavKola.HRAC_VSTUPUJE


def test_spravny_ton_se_zapocite_prave_jednou():
    log = vytvor()
    log.zahaj_kolo()
    log.sekvence_prehrana()
    log.zpracuj_vstup(spravny_vstup(log))
    assert log.spravce.celkem.spravne_tony == 1
    assert log.spravce.interval.spravne_tony == 1


def test_spatny_ton_je_chyba_a_snizi_pokus():
    log = vytvor()
    log.zahaj_kolo()
    log.sekvence_prehrana()
    vychozi = log.nastaveni.pocet_pokusu
    v = log.zpracuj_vstup(nespravny_vstup(log))
    assert v.prijat and v.spravne is False
    assert v.pokusy_zbyva == vychozi - 1
    assert log.spravce.celkem.chybne_tony == 1
    assert log.spravce.celkem.spravne_tony == 0


def test_chyba_vraci_na_zacatek_sekvence():
    log = vytvor(delka_sekvence=5)
    log.zahaj_kolo()
    log.sekvence_prehrana()
    log.zpracuj_vstup(spravny_vstup(log))
    log.zpracuj_vstup(spravny_vstup(log))
    assert log.pozice == 2
    v = log.zpracuj_vstup(nespravny_vstup(log))
    assert v.pozice == 0, "po chybě se hráč vrací na začátek"
    assert v.kolo_dokonceno is False
    assert log.stav is StavKola.HRAC_VSTUPUJE


def test_kazdy_vstup_je_zapocten_prave_jednou():
    log = vytvor(pocet_pokusu=3, delka_sekvence=2)
    log.zahaj_kolo()
    log.sekvence_prehrana()
    log.zpracuj_vstup(nespravny_vstup(log))   # 1 chyba
    log.zpracuj_vstup(spravny_vstup(log))     # 1 správně
    log.zpracuj_vstup(nespravny_vstup(log))   # 2. chyba
    assert log.spravce.celkem.chybne_tony == 2
    assert log.spravce.celkem.spravne_tony == 1
    assert log.pokusy_zbyva == 1


def test_vycerpani_pokusu_oznaci_kolo_jako_neuspesne():
    log = vytvor(pocet_pokusu=3, delka_sekvence=4)
    log.zahaj_kolo()
    log.sekvence_prehrana()
    for _ in range(3):
        v = log.zpracuj_vstup(nespravny_vstup(log))
    assert v.kolo_dokonceno is True
    assert v.uspech is False
    assert log.stav is StavKola.DOKONCENO_NEUSPECH
    assert log.spravce.celkem.neuspesna_kola == 1
    assert v.interval is not None or log.spravce.interval_cil > 1


def test_kolo_nelze_dokoncit_chybou_s_zbyvajicimi_pokusy():
    """Chyba se zbývajícími pokusy NESMÍ dokončit kolo ani spustit dialog."""
    log = vytvor(pocet_pokusu=3, delka_sekvence=3, interval_statistik=1)
    log.zahaj_kolo()
    log.sekvence_prehrana()
    v = log.zpracuj_vstup(nespravny_vstup(log))
    assert v.kolo_dokonceno is False
    assert v.uspech is None
    assert v.interval is None, "intervalový dialog nesmí být naplánován"
    assert log.spravce.celkem.dokoncena_kola == 0


def test_uplne_zopakovani_je_uspesne_kolo():
    log = vytvor(pocet_pokusu=3, delka_sekvence=4, interval_statistik=100)
    log.zahaj_kolo()
    log.sekvence_prehrana()
    for _ in range(4):
        v = log.zpracuj_vstup(spravny_vstup(log))
    assert v.kolo_dokonceno is True
    assert v.uspech is True
    assert log.stav is StavKola.DOKONCENO_USPECH
    assert log.spravce.celkem.uspesna_kola == 1
    assert log.spravce.celkem.spravne_tony == 4
    assert log.spravce.celkem.chybne_tony == 0


# --- Odmítání vstupu mimo hru -----------------------------------------------

def test_vstup_pred_prehranim_je_odmitnut():
    log = vytvor()
    log.zahaj_kolo()
    v = log.zpracuj_vstup(0)
    assert v.prijat is False
    assert log.spravce.celkem.spravne_tony == 0
    assert log.spravce.celkem.chybne_tony == 0


def test_vstup_po_dokonceni_kola_je_odmitnut():
    log = vytvor(pocet_pokusu=1, delka_sekvence=2, interval_statistik=100)
    log.zahaj_kolo()
    log.sekvence_prehrana()
    log.zpracuj_vstup(nespravny_vstup(log))   # kolo skončilo
    pocet_chyb = log.spravce.celkem.chybne_tony
    v = log.zpracuj_vstup(0)
    assert v.prijat is False
    assert log.spravce.celkem.chybne_tony == pocet_chyb


def test_neplatny_stupen_je_odmitnut():
    log = vytvor()
    log.zahaj_kolo()
    log.sekvence_prehrana()
    assert log.zpracuj_vstup(7).prijat is False
    assert log.zpracuj_vstup(-1).prijat is False
    assert log.spravce.celkem.dokoncena_kola == 0


# --- Opakování kola a nová hra ----------------------------------------------

def test_zopovat_kolo_restartuje_bez_zmeny_statistik():
    log = vytvor(pocet_pokusu=3, delka_sekvence=4, interval_statistik=100)
    log.zahaj_kolo()
    log.sekvence_prehrana()
    log.zpracuj_vstup(spravny_vstup(log))
    log.zpracuj_vstup(nespravny_vstup(log))
    before = (log.spravce.celkem.spravne_tony, log.spravce.celkem.chybne_tony,
              log.spravce.celkem.dokoncena_kola, log.pokusy_celkem)
    seq_pred = list(log.sekvence)
    assert log.zopovat_kolo() is True
    assert log.pozice == 0
    assert log.pokusy_zbyva == log.pokusy_celkem
    assert log.sekvence == seq_pred, "sekvence se při restartu nemění"
    assert log.stav is StavKola.CEKA_NA_PREHRANI
    after = (log.spravce.celkem.spravne_tony, log.spravce.celkem.chybne_tony,
             log.spravce.celkem.dokoncena_kola, log.pokusy_celkem)
    assert before == after


def test_zopovat_kolo_bez_sekvence():
    log = vytvor()
    assert log.zopovat_kolo() is False


def test_opakovani_sekvence_nemeni_skore():
    """Přehrání sekvence znovu nevstupuje do logiky → nic se nezmění."""
    log = vytvor(pocet_pokusu=3, delka_sekvence=3, interval_statistik=100)
    log.zahaj_kolo()
    log.sekvence_prehrana()
    log.zpracuj_vstup(spravny_vstup(log))
    before = (log.spravce.celkem.spravne_tony, log.spravce.celkem.chybne_tony,
              log.pokusy_zbyva, log.pozice, log.stav)
    # GUI při opakování volá jen zvukové přehrání; logika se nevolá.
    # Ověříme, že i volání sekvence_prehrana mimo stav CEKA nic nemění.
    assert log.sekvence_prehrana() is False
    after = (log.spravce.celkem.spravne_tony, log.spravce.celkem.chybne_tony,
             log.pokusy_zbyva, log.pozice, log.stav)
    assert before == after


def test_nova_hra_resetuje_stav_a_zachova_nastaveni_i_statistiky():
    log = vytvor(pocet_pokusu=3, delka_sekvence=4, tonina="G",
                 interval_statistik=100)
    log.zahaj_kolo()
    log.sekvence_prehrana()
    log.zpracuj_vstup(nespravny_vstup(log))
    log.zpracuj_vstup(nespravny_vstup(log))
    log.zpracuj_vstup(nespravny_vstup(log))   # kolo neúspěšné
    assert log.stav is StavKola.DOKONCENO_NEUSPECH

    log.nova_hra()
    assert log.stav is StavKola.CEKA_NA_PREHRANI
    assert log.sekvence == []
    assert log.pozice == 0
    assert log.pokusy_zbyva == 0
    assert log.kolo_cislo == 0
    # Nastavení zůstalo.
    assert log.nastaveni.tonina == "G"
    assert log.nastaveni.pocet_pokusu == 3
    # Statistiky zůstaly (jsou kumulativní).
    assert log.spravce.celkem.neuspesna_kola == 1
    assert log.spravce.celkem.chybne_tony == 3


def test_zmena_nastaveni_neovlivni_rozehrane_kolo():
    log = vytvor(pocet_pokusu=3, delka_sekvence=4, tonina="C")
    log.zahaj_kolo()
    log.sekvence_prehrana()
    pocet_pred = log.pokusy_celkem
    seq_pred = list(log.sekvence)
    log.zmenit_nastaveni(tonina="Fis", pocet_pokusu=7, delka_sekvence=6)
    # Rozehrané kolo pokračuje v původním režimu.
    assert log.pokusy_zbyva <= pocet_pred
    assert log.sekvence == seq_pred
    assert log.nastaveni.tonina == "Fis"
    # Další kolo už použije nové nastavení.
    log.zahaj_kolo()
    assert log.pokusy_celkem == 7
    assert len(log.sekvence) == 6
    assert log.nastaveni.tonina == "Fis"


# --- Validace nastavení ------------------------------------------------------

def test_neplatne_nastaveni():
    with pytest.raises(ValueError):
        NastaveniHry(delka_sekvence=1).over()
    with pytest.raises(ValueError):
        NastaveniHry(delka_sekvence=13).over()
    with pytest.raises(ValueError):
        NastaveniHry(pocet_pokusu=0).over()
    with pytest.raises(ValueError):
        NastaveniHry(oktava=6).over()
    with pytest.raises(ValueError):
        NastaveniHry(interval_statistik=0).over()
    with pytest.raises(ValueError):
        NastaveniHry(tonina="XYZ").over()


def test_zmenit_nastaveni_validuje():
    log = vytvor()
    with pytest.raises(ValueError):
        log.zmenit_nastaveni(delka_sekvence=99)
    with pytest.raises(ValueError):
        log.zmenit_nastaveni(interval_statistik=0)
