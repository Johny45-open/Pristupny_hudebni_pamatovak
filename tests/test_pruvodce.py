"""Testy čisté logiky průvodce rytmem (bez Qt a zvuku).

Ověřují hlavně:
- přepočet dob na sekundy podle skutečné interpretace v `melodies`,
- že nástupy rytmické varianty odpovídají nástupům `casovy_plan`
  (různé délky tónů, explicitní pauzy, různá tempa, mezertonová pauza),
- že se mezitónová pauza nezapočítá dvakrát,
- odpočítání se 4 údery po jedné době a spojení „před/po“ s pauzou,
- platnost vzorových fanfár a ochrana `VZOROVE_FANFARY` při kopii.
"""

from __future__ import annotations

import dataclasses

import pytest

import melodies
import pruvodce


# ---------------------------------------------------------------------------
# Pomocné
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def prazdny_registr_vlastnich():
    """Testy nesmí zaplavit registr vlastních melodií."""
    melodies.VLASTNI_MELODIE.clear()
    yield
    melodies.VLASTNI_MELODIE.clear()


def onsets(kroky) -> list[float]:
    """Okamžiky nástupů jednotlivých kroků (sekundy od začátku)."""
    cas = 0.0
    vysledek = []
    for k in kroky:
        vysledek.append(cas)
        cas += k.zvuk_s + k.pauza_s
    return vysledek


def celkem(kroky) -> float:
    return sum(k.zvuk_s + k.pauza_s for k in kroky)


def blizko(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def snimek_vzoru() -> dict:
    """Hluboká kopie registru vzorů pro porovnání před/po."""
    return {k: dataclasses.asdict(v)
            for k, v in melodies.VZOROVE_FANFARY.items()}


# Melodie pokrývající požadavky: různé délky, explicitní pauzy, různá tempa.
PRIKLADOVE = [
    # (id, Melodie, poznámka)
    ("casovani", melodies.Melodie(
        id="_t1", nazev="Různé délky", druh=melodies.DRUH_VITEZNA,
        tony=(melodies.Ton("C4", 1.0, 0.0), melodies.Ton("E4", 0.5, 0.5),
              melodies.Ton("G4", 2.0, 0.0), melodies.Ton("C5", 0.25, 1.5)),
        tempo_bpm=96.0, mezertonova_pauza_s=0.12),
     "různé délky + explicitní pauzy"),
    ("rychle", melodies.Melodie(
        id="_t2", nazev="Rychlé osminky", druh=melodies.DRUH_VITEZNA,
        tony=(melodies.Ton("C4", 0.125), melodies.Ton("D4", 0.125),
              melodies.Ton("E4", 0.5)),
        tempo_bpm=240.0, mezertonova_pauza_s=0.05),
     "krátké tóny při vysokém tempu"),
    ("pomaly", melodies.Melodie(
        id="_t3", nazev="Pomalá fanfára", druh=melodies.DRUH_VITEZNA,
        tony=(melodies.Ton("G4", 0.5), melodies.Ton("C5", 4.0, 1.0)),
        tempo_bpm=60.0, mezertonova_pauza_s=0.2),
     "dlouhé tóny při nízkém tempu"),
    ("mensi_nez_impuls", melodies.Melodie(
        id="_t4", nazev="Tón kratší než impuls", druh=melodies.DRUH_VITEZNA,
        tony=(melodies.Ton("C4", 0.05), melodies.Ton("E4", 0.05, 0.05)),
        tempo_bpm=240.0, mezertonova_pauza_s=0.0),
     "D < I — impuls se zkrátí na trvání kroku"),
]


# ===================================================================
# Přepočet dob na sekundy
# ===================================================================

def test_doba_a_prepocty_odpovidaji_vzorci():
    assert blizko(pruvodce.doba_s(120), 0.5)
    assert blizko(pruvodce.doba_s(100), 0.6)
    assert blizko(pruvodce.doba_s(90), 60 / 90)

    # delka * 60 / BPM
    assert blizko(pruvodce.delka_tonu_s(0.75, 120), 0.375)
    assert blizko(pruvodce.delka_tonu_s(1, 100), 0.6)
    # pauza * 60 / BPM + mezertonová pauza (v sekundách)
    assert blizko(pruvodce.pauza_tonu_s(0.5, 120, 0.12), 0.37)
    assert blizko(pruvodce.pauza_tonu_s(1.0, 120, 0.0), 0.5)

    assert pruvodce.prepocti_doby(0.75, 0.5, 120, 0.12) == \
        pytest.approx((0.375, 0.37))


def test_prepocty_odmitaji_neplatne_hodnoty():
    with pytest.raises(ValueError):
        pruvodce.doba_s(0)
    with pytest.raises(ValueError):
        pruvodce.delka_tonu_s(-0.5, 120)
    with pytest.raises(ValueError):
        pruvodce.pauza_tonu_s(-0.5, 120)
    with pytest.raises(ValueError):
        pruvodce.pauza_tonu_s(0.5, 120, -0.1)


def test_prepocty_sedi_s_casovym_planem():
    """Stejné vstupy → stejné sekundy jako při skutečném přehrávání."""
    m = melodies.Melodie(
        id="_t5", nazev="Ověření s casovy_plan", druh=melodies.DRUH_VITEZNA,
        tony=(melodies.Ton("C4", 1.25, 0.75),), tempo_bpm=140.0,
        mezertonova_pauza_s=0.17)
    krok = melodies.casovy_plan(m)[0]
    zvuk_s, pauza_s = pruvodce.prepocti_doby(
        1.25, 0.75, 140.0, 0.17)
    assert blizko(krok.zvuk_s, zvuk_s)
    assert blizko(krok.pauza_s, pauza_s)


# ===================================================================
# Nástupy rytmické varianty = nástupy původní melodie
# ===================================================================

@pytest.mark.parametrize("id_melodie,poznamka", [(p[0], p[2]) for p in PRIKLADOVE])
def test_nastupy_rytmu_odpovidaji_casovemu_planu(id_melodie, poznamka):
    melodie = next(p[1] for p in PRIKLADOVE if p[0] == id_melodie)
    puvodni = melodies.casovy_plan(melodie)
    rytmus = pruvodce.kroky_rytmu(melodie)

    assert len(rytmus) == len(puvodni)
    assert all(k.impuls for k in rytmus), "rytmus musí být z impulzů"
    assert all(not k.impuls for k in puvodni), "casovy_plan se nesmí změnit"

    # 1) Stejné okamžiky nástupů (vč. mezertonové pauzy jednou).
    for a, b in zip(onsets(puvodni), onsets(rytmus)):
        assert blizko(a, b), f"nástup nesedí ({poznamka}): {a} != {b}"

    # 2) Celková délka se nezmění → pauza se nezapočítá dvakrát.
    assert blizko(celkem(rytmus), celkem(puvodni))

    # 3) Přesný předpis: I = min(0.08, D), pauza = max(0, D + P - I).
    for d, r in zip(puvodni, rytmus):
        ocekavany_impuls = min(pruvodce.DELKA_IMPSULU_S, d.zvuk_s)
        assert blizko(r.zvuk_s, ocekavany_impuls)
        assert blizko(r.pauza_s,
                      max(0.0, d.zvuk_s + d.pauza_s - ocekavany_impuls))
        # Nástup dalšího kroku = D + P (impuls + jeho pauza).
        assert blizko(r.zvuk_s + r.pauza_s, d.zvuk_s + d.pauza_s)


def test_mezertonova_pauza_se_nezapocita_dvakrat():
    m = melodies.Melodie(
        id="_t6", nazev="Jeden tón", druh=melodies.DRUH_VITEZNA,
        tony=(melodies.Ton("C4", 1.0, 0.0),), tempo_bpm=120.0,
        mezertonova_pauza_s=0.12)
    puvodni = melodies.casovy_plan(m)[0]
    r = pruvodce.kroky_rytmu(m)[0]

    # Původně: zvuk 0,5 s + pauza 0,12 s = 0,62 s.
    assert blizko(puvodni.zvuk_s, 0.5)
    assert blizko(puvodni.pauza_s, 0.12)
    # Po impulzu: 0,08 + 0,54 = 0,62 s — mezertonová pauza je obsažena jednou.
    assert blizko(r.zvuk_s, 0.08)
    assert blizko(r.pauza_s, 0.54)
    assert blizko(r.zvuk_s + r.pauza_s, 0.62)


def test_kroky_rytmu_odmitaji_neplatnou_delku():
    melodie = PRIKLADOVE[0][1]
    with pytest.raises(ValueError):
        pruvodce.kroky_rytmu(melodie, delka_impulsu_s=0)
    with pytest.raises(ValueError):
        pruvodce.kroky_rytmu(melodie, delka_impulsu_s=-0.1)


# ===================================================================
# Odpočítání — 4 údery po jedné době
# ===================================================================

def test_odpocet_ma_ctyri_udery_po_jedne_dobe():
    tempo = 120.0
    doba = pruvodce.doba_s(tempo)
    zaklad = [melodies.KrokPrehravani(60, 0.5, 0.1)]
    kroky = pruvodce.kroky_s_odpocet(zaklad, tempo)

    assert len(kroky) == pruvodce.UDERY_ODPOCETU + len(zaklad)
    odpocet = kroky[:pruvodce.UDERY_ODPOCETU]
    assert all(k.impuls for k in odpocet), "odpočítání = zvukové údery"

    # Rozestupy mezi údery = přesně 1 doba (vč. přechodu na první krok).
    n = onsets(kroky)
    for i in range(pruvodce.UDERY_ODPOCETU):
        assert blizko(n[i + 1] - n[i], doba), f"úder {i} nesedí"

    # Původní kroky jsou na konci beze změny a se stejnými nástupy.
    assert kroky[pruvodce.UDERY_ODPOCETU:] == zaklad


def test_odpocet_pri_vysokem_tempu_nekouše_dozvuk():
    # Při 240 BPM je doba 0,25 s > impulsu — rozestup zůstává 0,25 s.
    kroky = pruvodce.kroky_s_odpocet([], 240.0)
    n = onsets(kroky)
    assert blizko(n[1] - n[0], 0.25)


def test_odpocet_odmita_zaporny_pocet():
    with pytest.raises(ValueError):
        pruvodce.kroky_s_odpocet([], 120, pocet=-1)


# ===================================================================
# Spojení „před“ a „po“ s výraznou pauzou
# ===================================================================

def test_spoj_kroky_vklada_pauzu_a_nemeni_vstupy():
    prvni = [melodies.KrokPrehravani(60, 0.2, 0.1),
             melodies.KrokPrehravani(62, 0.3, 0.2)]
    druhy = [melodies.KrokPrehravani(64, 0.1, 0.1),
             melodies.KrokPrehravani(65, 0.4, 0.0)]
    prvni_pred = list(prvni)
    druhy_pred = list(druhy)

    spojeno = pruvodce.spoj_kroky(prvni, druhy)

    assert len(spojeno) == 4
    assert prvni == prvni_pred, "vstup se nesmí změnit"
    assert druhy == druhy_pred

    # Přesná pauza mezi sekvencemi (přičtená k poslední pauze první části).
    prvni_celkem = 0.2 + 0.1 + 0.3 + 0.2
    assert blizko(spojeno[1].pauza_s,
                  0.2 + pruvodce.PAUZA_MEZI_POROVNANIM_S)
    n = onsets(spojeno)
    assert blizko(n[2], prvni_celkem + pruvodce.PAUZA_MEZI_POROVNANIM_S)

    # Vnitřní intervaly druhé části zůstávají.
    assert blizko(n[3] - n[2], 0.1 + 0.1)


def test_spoj_kroky_s_prazdnou_sekvenci():
    kroky = [melodies.KrokPrehravani(60, 0.1, 0.0)]
    assert pruvodce.spoj_kroky([], kroky) == kroky
    assert pruvodce.spoj_kroky(kroky, []) == kroky
    with pytest.raises(ValueError):
        pruvodce.spoj_kroky(kroky, kroky, pauza_mezi_s=-1.0)


# ===================================================================
# Vzorové fanfáry — platnost a ochrana originálu
# ===================================================================

def test_vzorove_fanfary_jsou_platne_a_v_hre_neni():
    vzory = melodies.vzorove_fanfary()
    assert len(vzory) == 3
    assert set(melodies.VZOROVE_FANFARY) == {v.id for v in vzory}

    for v in vzory:
        chyby, _ = melodies.over_pred_ulozenim(v)
        assert chyby == [], f"vzor {v.id} je neplatný: {chyby}"
        assert v.id.startswith(melodies.VZOR_PREFIX_ID)
        assert v.druh == melodies.DRUH_VITEZNA
        assert v.tony, "vzor musí mít tóny"
        # Vzory nesmí být v nabídce melodií pro hru.
        assert v.id not in dict(melodies.nabidka_melodii(melodies.DRUH_VITEZNA))
        assert v.id not in dict(melodies.nabidka_melodii(melodies.DRUH_SMUTNA))

    assert melodies.vzor("vzor_neexistuje") is None


def test_vzor_jako_vlastni_vytvari_kopii_s_novym_id():
    vzor = melodies.vzorove_fanfary()[0]
    pred = snimek_vzoru()

    kopie = melodies.vzor_jako_vlastni(vzor.id)

    assert kopie.id != vzor.id
    assert kopie.id.startswith(melodies.PREFIX_ID_VLASTNI)
    assert "vlastní úprava" in kopie.nazev
    assert "(vzor)" not in kopie.nazev
    # Obsah se nemění…
    assert kopie.tony == vzor.tony
    assert kopie.tempo_bpm == vzor.tempo_bpm
    assert kopie.mezertonova_pauza_s == vzor.mezertonova_pauza_s
    # …a vzory v registru zůstávají beze změny.
    assert snimek_vzoru() == pred
    # Kopie se sama od sebe neukládá do vlastních melodií.
    assert kopie.id not in melodies.VLASTNI_MELODIE


def test_ulozeni_kopie_vzoru_original_nechybi():
    vzor = melodies.vzorove_fanfary()[1]
    pred = snimek_vzoru()

    kopie = melodies.vzor_jako_vlastni(vzor.id)
    ulozena = melodies.uloz_vlastni_melodie(kopie)

    assert ulozena.id in melodies.VLASTNI_MELODIE
    assert vzor.id not in melodies.VLASTNI_MELODIE, \
        "vzor se nesmí objevit mezi vlastními melodiemi"
    assert snimek_vzoru() == pred

    # A vzor zůstává mimo nabídku pro hru.
    assert vzor.id not in dict(melodies.nabidka_melodii(melodies.DRUH_VITEZNA))


def test_vzor_jako_vlastni_odmita_nezname_id():
    with pytest.raises(ValueError):
        melodies.vzor_jako_vlastni("vzor_neznami")


# ===================================================================
# Rytmické příklady
# ===================================================================

def test_priklady_maji_popis_a_sedici_udaje():
    assert len(pruvodce.PRIKLADY) == 3
    for p in pruvodce.PRIKLADY:
        assert p.nazev and p.popis
        assert p.melodie.tony
        # Příklady nejsou melodie k uložení — kontrolujeme jen tóny/časy.
        chyby, _ = melodies.validuj_melodii(p.melodie, "C")
        assert chyby == []
        # Délka tónu v příkladu odpovídá popisu (60 / tempo × délka).
        assert pruvodce.doba_s(p.melodie.tempo_bpm) > 0

    # Konkrétní čísla z popisů.
    ctvrtky = pruvodce.priklad("stejne_ctvrtky")
    assert blizko(pruvodce.delka_tonu_s(1, ctvrtky.melodie.tempo_bpm), 0.6)
    trojky = pruvodce.priklad("vitezny_ritmus")
    assert blizko(pruvodce.delka_tonu_s(1.5, trojky.melodie.tempo_bpm), 0.75)

    assert pruvodce.priklad("neexistuje") is None
