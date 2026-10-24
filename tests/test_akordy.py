"""Testy nového režimu Akordy, obratů a vývojářského režimu."""

from __future__ import annotations

import random
import pytest

import theory
from sound import generuj_akord, ZvukovyMotor
from game_logic import HerniLogika, NastaveniHry, StavKola


def test_teorie_akordy_stupne():
    # V C dur, stupeň 0 (C) by měl mít trojzvuk C, E, G (C4=60, E4=64, G4=67)
    midi_tony = theory.akord_stupne("C", 0, oktava=4, obrat=0)
    assert midi_tony == [60, 64, 67]

    nazev = theory.nazev_akordu_stupne("C", 0)
    assert nazev == "C dur"


def test_teorie_akordy_obraty():
    # Základní tvar C dur: [60, 64, 67] (C, E, G)
    # 1. obrat (sextakord): [64, 67, 72] (E, G, C)
    assert theory.akord_stupne("C", 0, oktava=4, obrat=1) == [64, 67, 72]
    # 2. obrat (kvartsextakord): [67, 72, 76] (G, C, E)
    assert theory.akord_stupne("C", 0, oktava=4, obrat=2) == [67, 72, 76]

    detail = theory.popis_akordu_detail("C", 0, oktava=4, obrat=1)
    assert "C dur" in detail
    assert "1. obrat" in detail


def test_teorie_akordy_mollove_a_zmensene():
    # V C dur, stupeň 1 (D) je mollový trojzvuk D, F, A (D4=62, F4=65, A4=69)
    assert theory.akord_stupne("C", 1, oktava=4) == [62, 65, 69]
    assert theory.nazev_akordu_stupne("C", 1) == "D mol"

    # Stupeň 6 (H) v C dur je zmenšený trojzvuk H, D, F (H4=71, D5=74, F5=77)
    assert theory.akord_stupne("C", 6, oktava=4) == [71, 74, 77]
    assert theory.nazev_akordu_stupne("C", 6) == "H zmenšený"


def test_generovani_akordu_zvuk():
    signal = generuj_akord([60, 64, 67], 0.1)
    assert signal is not None
    assert signal.ndim == 2
    assert signal.shape[1] == 2
    assert len(signal) > 0


def test_zvukovy_motor_vytvor_akord():
    motor = ZvukovyMotor()
    akord = motor.vytvor_akord((60, 64, 67), 0.1)
    if motor.dostupny:
        assert akord is not None
    else:
        assert akord is None
    motor.uvolni()


def test_herni_logika_rezim_akordy_a_vyvojarsky():
    nastaveni = NastaveniHry(rezim="akordy", tonina="C", delka_sekvence=3, pocet_pokusu=2, vyvojarsky_rezim=True)
    log = HerniLogika(nastaveni=nastaveni, rng=random.Random(42))
    
    seq = log.zahaj_kolo()
    assert len(seq) == 3
    
    # Ověření, že midi_sekvence vrací tuples s MIDI tóny akordů
    midi_seq = log.midi_sekvence()
    assert len(midi_seq) == 3
    for akord_midi in midi_seq:
        assert isinstance(akord_midi, tuple)
        assert len(akord_midi) == 3

    # Vývojářský přehled sekvence
    prehled = log.vyvojarsky_prehled_sekvence()
    assert len(prehled) == 3
    for p in prehled:
        assert isinstance(p, str)
        assert len(p) > 0

    # Ověření tlačítek
    tlacitka = log.tlacitka()
    assert len(tlacitka) == 7
    for nazev, midi in tlacitka:
        assert nazev.startswith("Akord ")
        assert isinstance(midi, int)

    # Zahájení hádání
    log.sekvence_prehrana()
    assert log.stav is StavKola.HRAC_VSTUPUJE

    # Zkouška správného vstupu na první pozici
    spravny = seq[0]
    v = log.zpracuj_vstup(spravny)
    assert v.prijat
    assert v.spravne is True
