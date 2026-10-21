"""Testy melodií — transpozice, individuální definice, validace, fallback."""

from __future__ import annotations

import pytest

import melodies
import theory


def _vsechny_klice():
    return theory.PORADI_TONIN


def _vsechny_kombinace():
    return [
        (klic, druh, mid)
        for klic in theory.PORADI_TONIN
        for druh in melodies.DRUHY
        for mid, _ in melodies.nabidka_melodii(druh)
    ]


# --- Každá tónina, každý druh, každá přednastavená melodie ------------------

@pytest.mark.parametrize("klic,druh,idm", _vsechny_kombinace())
def test_melodie_pro_kazdou_toninu_je_platna(klic, druh, idm):
    volba = melodies.ziskej_melodii(klic, druh, idm)
    chyby, _ = melodies.validuj_melodii(volba.melodie, klic)
    assert not chyby, f"{klic}/{druh}/{idm}: {chyby}"
    assert volba.varovani is None, f"{klic}/{druh}/{idm}: {volba.varovani}"


@pytest.mark.parametrize("klic,druh,idm", _vsechny_kombinace())
def test_melodie_obsahuje_tony_konkretni_toniny(klic, druh, idm):
    volba = melodies.ziskej_melodii(klic, druh, idm)
    for ton in volba.melodie.tony:
        midi = theory.midi_z_nazvu(ton.nazev)
        assert theory.ton_patri_do_toniny(midi, klic), (klic, ton.nazev)


# --- Transpozice a české názvy ---------------------------------------------

def test_vitezna_fanfara_v_fis_dur():
    volba = melodies.ziskej_melodii("Fis", melodies.DRUH_VITEZNA, "kratka_fanfara")
    assert volba.zdroj == "transpozice"
    assert [t.nazev for t in volba.melodie.tony] == ["Fis4", "Ais4", "Cis5", "Fis5"]


def test_smutna_v_ces_dur_pouziva_zesnizene():
    volba = melodies.ziskej_melodii("Ces", melodies.DRUH_SMUTNA, "dlouhy_smutny")
    assert [t.nazev for t in volba.melodie.tony] == [
        "Ces5", "B4", "As4", "Ges4", "Fes4", "Es4", "Des4", "Ces4"]


def test_h_a_b_v_transpozici():
    # V H dur musí 7. stupeň H dur znít jako Ais a ve F dur jako B.
    volba = melodies.ziskej_melodii("H", melodies.DRUH_VITEZNA, "vzestupna")
    nazvy = [t.nazev for t in volba.melodie.tony]
    assert "H4" in nazvy or "H5" in nazvy
    for nazev in nazvy:
        assert not nazev.startswith("B"), nazev   # H dur neobsahuje bé

    volba_f = melodies.ziskej_melodii("F", melodies.DRUH_VITEZNA, "vzestupna")
    nazvy_f = [t.nazev for t in volba_f.melodie.tony]
    assert "B4" in nazvy_f
    assert not any(n.startswith("H") for n in nazvy_f)


def test_transpozice_zachova_delky_a_tempo():
    zaklad = melodies.ZAKLADNI_VITEZNE["vzestupna"]
    volba = melodies.ziskej_melodii("Es", melodies.DRUH_VITEZNA, "vzestupna")
    assert volba.melodie.tempo_bpm == zaklad.tempo_bpm
    assert [t.delka for t in volba.melodie.tony] == [t.delka for t in zaklad.tony]
    assert [t.pauza for t in volba.melodie.tony] == [t.pauza for t in zaklad.tony]


def test_transpozice_mezi_oktavami():
    # Melodie se nesmí zbytečně vynést mimo rozumný rozsah.
    for klic in theory.PORADI_TONIN:
        volba = melodies.ziskej_melodii(klic, melodies.DRUH_VITEZNA, "slavnostni")
        midisy = [theory.midi_z_nazvu(t.nazev) for t in volba.melodie.tony]
        assert all(48 <= m <= 96 for m in midisy), (klic, midisy)


# --- Individuální definice má přednost --------------------------------------

def test_individualni_definice_ma_prednost():
    klic = "G"
    klice = (klic, melodies.DRUH_VITEZNA, "kratka_fanfara")
    vlastni = melodies.Melodie(
        id="kratka_fanfara",
        nazev="Vlastní fanfára G",
        tony=(melodies.Ton("G4", 0.5), melodies.Ton("D5", 1.0)),
        tempo_bpm=140.0,
    )
    melodies.INDIVIDUALNI_MELODIE[klice] = vlastni
    try:
        volba = melodies.ziskej_melodii(klic, melodies.DRUH_VITEZNA, "kratka_fanfara")
        assert volba.zdroj == "individualni"
        assert volba.melodie is vlastni
        # Jiná tónina tuto definici nepoužije.
        jina = melodies.ziskej_melodii("D", melodies.DRUH_VITEZNA, "kratka_fanfara")
        assert jina.zdroj == "transpozice"
    finally:
        del melodies.INDIVIDUALNI_MELODIE[klice]


def test_neplatna_individualni_definice_se_odmitne():
    klic = "D"
    klice = (klic, melodies.DRUH_SMUTNA, "kratka_sestupna")
    # Tón Fis4 nepatří do D dur? Fis DO D dur patří — použijeme C4 (nepatří).
    spatna = melodies.Melodie(
        id="kratka_sestupna", nazev="Neplatná",
        tony=(melodies.Ton("C4"), melodies.Ton("D4")),
        tempo_bpm=100.0,
    )
    melodies.INDIVIDUALNI_MELODIE[klice] = spatna
    try:
        volba = melodies.ziskej_melodii(klic, melodies.DRUH_SMUTNA, "kratka_sestupna")
        assert volba.zdroj != "individualni"
        assert volba.varovani is not None
        assert "nepodařilo použít" in volba.varovani
        chyby, _ = melodies.validuj_melodii(volba.melodie, klic)
        assert not chyby
    finally:
        del melodies.INDIVIDUALNI_MELODIE[klice]


# --- Validace ---------------------------------------------------------------

def test_ton_mimo_stupnici_bez_povoleni_odmitnut():
    m = melodies.Melodie(
        id="x", nazev="Test",
        tony=(melodies.Ton("Fis4"),),   # Fis nepatří do C dur
        tempo_bpm=100.0,
    )
    chyby, varovani = melodies.validuj_melodii(m, "C")
    assert chyby, "mimo-stupnicový tón musí být odmítnut"
    assert not varovani


def test_ton_mimo_stupnici_s_povolenim_jen_varovani():
    m = melodies.Melodie(
        id="x", nazev="Test",
        tony=(melodies.Ton("Fis4"),),
        tempo_bpm=100.0,
        povolit_mimo_stupnici=True,
    )
    chyby, varovani = melodies.validuj_melodii(m, "C")
    assert not chyby
    assert varovani and "povoleno" in varovani[0]


def test_neplatne_parametry():
    base = dict(id="x", nazev="Test", tony=(melodies.Ton("C4"),))
    chyby, _ = melodies.validuj_melodii(melodies.Melodie(**base, tempo_bpm=0), "C")
    assert any("tempo" in c for c in chyby)
    chyby, _ = melodies.validuj_melodii(
        melodies.Melodie(**base, mezertonova_pauza_s=-0.1), "C")
    assert any("pauza" in c for c in chyby)
    chyby, _ = melodies.validuj_melodii(
        melodies.Melodie(id="x", nazev="Test", tony=()), "C")
    assert any("neobsahuje" in c for c in chyby)
    chyby, _ = melodies.validuj_melodii(
        melodies.Melodie(id="x", nazev="Test",
                         tony=(melodies.Ton("C4", delka=0),)), "C")
    assert any("délka" in c for c in chyby)
    chyby, _ = melodies.validuj_melodii(
        melodies.Melodie(id="x", nazev="Test",
                         tony=(melodies.Ton("X4"),)), "C")
    assert any("tón 1" in c for c in chyby)


# --- Chybějící definice a fallback ------------------------------------------

def test_neznamy_id_melodie_pouzije_vychozi():
    volba = melodies.ziskej_melodii("A", melodies.DRUH_VITEZNA, "neexistuje")
    assert volba.zdroj == "zalozni"
    assert volba.varovani is not None and "výchozí" in volba.varovani
    chyby, _ = melodies.validuj_melodii(volba.melodie, "A")
    assert not chyby


def test_funguje_bez_id_melodie():
    volba = melodies.ziskej_melodii("Es", melodies.DRUH_SMUTNA)
    assert volba.melodie.id == melodies.VYCHOZI_ID[melodies.DRUH_SMUTNA]
    chyby, _ = melodies.validuj_melodii(volba.melodie, "Es")
    assert not chyby


def test_posledni_zaloha_pri_poskozene_zakladni_sadě(monkeypatch):
    # Simulace poškozené základní sady: transpozice selže → záložní melodie.
    monkeypatch.setitem(melodies.ZAKLADNI_SMUTNE, "kratka_sestupna",
                        melodies.Melodie(
                            id="kratka_sestupna", nazev="Poškozená",
                            tony=(melodies.Ton("C4", delka=-1),),
                        ))
    volba = melodies.ziskej_melodii("C", melodies.DRUH_SMUTNA, "kratka_sestupna")
    assert volba.zdroj == "zalozni"
    assert volba.varovani is not None
    chyby, _ = melodies.validuj_melodii(volba.melodie, "C")
    assert not chyby


def test_neznamy_druh():
    with pytest.raises(ValueError):
        melodies.ziskej_melodii("C", "neznamy")
    with pytest.raises(ValueError):
        melodies.nabidka_melodii("neznamy")


# --- Časový plán pro zvuk ----------------------------------------------------

def test_casovy_plan_mase_spravne_doby():
    volba = melodies.ziskej_melodii("C", melodies.DRUH_VITEZNA, "kratka_fanfara")
    plan = melodies.casovy_plan(volba.melodie)
    assert len(plan) == len(volba.melodie.tony)
    assert all(k.zvuk_s > 0 for k in plan)
    assert all(k.pauza_s >= 0 for k in plan)
    assert melodies.doba_celkem(volba.melodie) == sum(
        k.zvuk_s + k.pauza_s for k in plan)


def test_vyber_melodie_se_meni_podle_toniny():
    """Přepnutí tóniny musí změnit vybranou melodii (jiné výšky)."""
    c = melodies.ziskej_melodii("C", melodies.DRUH_VITEZNA, "kratka_fanfara")
    g = melodies.ziskej_melodii("G", melodies.DRUH_VITEZNA, "kratka_fanfara")
    midisy_c = [theory.midi_z_nazvu(t.nazev) for t in c.melodie.tony]
    midisy_g = [theory.midi_z_nazvu(t.nazev) for t in g.melodie.tony]
    assert midisy_c != midisy_g


def test_vyber_jine_id_melodie_zmeni_zvuk():
    a = melodies.ziskej_melodii("C", melodies.DRUH_SMUTNA, "kratka_sestupna")
    b = melodies.ziskej_melodii("C", melodies.DRUH_SMUTNA, "dlouhy_smutny")
    assert a.melodie.id != b.melodie.id
    assert len(a.melodie.tony) != len(b.melodie.tony)
