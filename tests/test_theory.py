"""Testy hudební teorie — všech 15 tónin, české názvosloví, transpozice."""

from __future__ import annotations

import pytest

import theory

POZADANE_TONINY = ["C", "G", "D", "A", "E", "H", "Fis", "Cis",
                   "F", "B", "Es", "As", "Des", "Ges", "Ces"]


def test_podporovanych_presne_15_tonin():
    assert len(theory.PORADI_TONIN) == 15
    assert set(theory.PORADI_TONIN) == set(POZADANE_TONINY)


@pytest.mark.parametrize("tonina", POZADANE_TONINY)
def test_stupnice_mase_7_rozdilnych_stupnu(tonina):
    stup = theory.stupnice(tonina, oktava=4)
    assert len(stup) == 7
    pultony = [m % 12 for _, m in stup]
    assert len(set(pultony)) == 7, "stupnice musí mít 7 různých tónů"


@pytest.mark.parametrize("tonina", POZADANE_TONINY)
def test_stupnice_odpovida_durovemu_intervalu(tonina):
    stup = theory.stupnice(tonina, oktava=4)
    zaklad = stup[0][1]
    ocekavane = [zaklad + i for i in theory.INTERVALY_DUR]
    skutecne = [m for _, m in stup]
    assert skutecne == ocekavane


@pytest.mark.parametrize("tonina", POZADANE_TONINY)
def test_stupnice_vzrusta(tonina):
    stup = theory.stupnice(tonina, oktava=4)
    midis = [m for _, m in stup]
    assert midis == sorted(midis)
    assert midis[-1] - midis[0] == 11


@pytest.mark.parametrize("tonina", POZADANE_TONINY)
def test_vsechny_tony_stupnice_patri_do_toniny(tonina):
    for _, midi in theory.stupnice(tonina, oktava=4):
        assert theory.ton_patri_do_toniny(midi, tonina)


# --- Enharmonicky správný zápis (klíčový rozdíl oproti MIDI % 12) ---------

def test_fis_dur_sedm_stupen_je_eis():
    stup = theory.stupnice("Fis", 4)
    assert [n for n, _ in stup] == ["Fis", "Gis", "Ais", "H", "Cis", "Dis", "Eis"]
    # Eis musí znít jako F (77), ne jako E.
    assert stup[6][1] == 77


def test_ces_dur_sedm_stupen():
    stup = theory.stupnice("Ces", 4)
    assert [n for n, _ in stup] == ["Ces", "Des", "Es", "Fes", "Ges", "As", "B"]
    # Fes musí znít jako E (64), Ces jako B (59).
    assert stup[3][1] == 64
    assert stup[0][1] == 59


def test_cis_dur_sedm_stupen_je_his():
    stup = theory.stupnice("Cis", 4)
    assert stup[6][0] == "His"
    assert stup[6][1] == 72   # H#4 = C5


def test_h_a_b_nejsou_zamienene():
    # H = B přirozené = 71 v oktávě 4, B = B snížené = 70 v oktávě 4.
    assert theory.midi_z_nazvu("H4") == 71
    assert theory.midi_z_nazvu("B4") == 70
    assert theory.stupnice("H", 4)[0][1] == 71
    assert theory.stupnice("B", 4)[0][1] == 70


def test_b_dur_stupnice():
    stup = theory.stupnice("B", 4)
    assert [n for n, _ in stup] == ["B", "C", "D", "Es", "F", "G", "A"]


def test_eis_a_fes_maji_spravnou_oktavu():
    # Název oktávy se musí počítat z přirozené výšky písmene.
    assert theory.nazev_tonu_z_midi(77, "Fis") == "Eis5"   # E#5 = F5
    assert theory.nazev_tonu_z_midi(64, "Ces") == "Fes4"
    assert theory.nazev_tonu_z_midi(71, "Ces") == "Ces5"   # Cb5 = B4


def test_prevod_nazvu_a_zpet():
    for nazev in ("C4", "H4", "B3", "Fis4", "Ces4", "His3", "Es5", "Ais2"):
        midi = theory.midi_z_nazvu(nazev)
        zpet = theory.nazev_tonu_z_midi(midi)
        assert theory.midi_z_nazvu(zpet) == midi, nazev


def test_neplatny_nazev():
    with pytest.raises(ValueError):
        theory.midi_z_nazvu("X4")
    with pytest.raises(ValueError):
        theory.midi_z_nazvu("Cis")
    with pytest.raises(ValueError):
        theory.over_toninu("XYZ")


# --- Oktávy a tlačítka -----------------------------------------------------

@pytest.mark.parametrize("oktava", [3, 4, 5])
@pytest.mark.parametrize("tonina", POZADANE_TONINY)
def test_zakladni_ton_ma_zadanou_oktavu(tonina, oktava):
    midi = theory.midi_zakladniho_tonu(tonina, oktava)
    assert midi // 12 - 1 == oktava or midi % 12 == 11   # u Ces může přesahovat oktávu dolů
    assert midi % 12 == theory.pultony_zakladniho_tonu(tonina)


@pytest.mark.parametrize("tonina", POZADANE_TONINY)
def test_tlacitka_maji_pristupne_nazvy(tonina):
    for stupen in range(7):
        nazev, midi = theory.nazev_pro_tlacitko(tonina, stupen, 4)
        assert nazev.startswith("Tón ")
        assert "oktáva" in nazev
        assert "Tlačítko" not in nazev
        assert isinstance(midi, int)


def test_transpozice_nazvu_drzi_ceske_nazvoslovi():
    # H#4 = C5 = 72 → v Cis dur se správně jmenuje „His4“, ne „Cis5“.
    assert theory.transponuj_nazev("H4", 1, "Cis") == "His4"
    assert theory.transponuj_nazev("B3", 2, "C") == "C4"
    assert theory.transponuj_nazev("Fis4", -6, "C") == "C4"
    assert theory.transponuj_nazev("C4", 2, "D") == "D4"
