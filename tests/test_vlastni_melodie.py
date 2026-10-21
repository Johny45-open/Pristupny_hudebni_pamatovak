"""Testy vlastních melodií — registr, validace, výběr, serializace.

Čistý Python (bez Qt a bez diskového zápisu — tomu je věnován
test_uloziste_melodie.py).
"""

from __future__ import annotations

import json

import pytest

import melodies


@pytest.fixture(autouse=True)
def prazdny_registr():
    """Každý test začíná s prázdným registrem vlastních melodií."""
    melodies.VLASTNI_MELODIE.clear()
    yield
    melodies.VLASTNI_MELODIE.clear()


def melodie(nazev="Testovací", druh=None, id_melodie=None, mimo=False,
            tony=None) -> melodies.Melodie:
    return melodies.Melodie(
        id=id_melodie or melodies.nova_id_melodie(),
        nazev=nazev,
        tony=tony if tony is not None else (
            melodies.Ton("C4", 1.0, 0.0), melodies.Ton("E4", 1.0, 0.0)),
        druh=druh or melodies.DRUH_SMUTNA,
        povolit_mimo_stupnici=mimo,
    )


# ==================================================================
# Registr (CRUD + validace)
# ==================================================================

def test_nova_id_je_unikatni_a_s_prefixem():
    ida, idb = melodies.nova_id_melodie(), melodies.nova_id_melodie()
    assert ida != idb
    assert ida.startswith(melodies.PREFIX_ID_VLASTNI)
    melodies.uloz_vlastni_melodie(melodie(id_melodie=ida))
    # Stejné ID se nesmí opakovat ani po naplnění registru.
    assert melodies.nova_id_melodie() not in melodies.VLASTNI_MELODIE


def test_ulozeni_a_nalezeni():
    m = melodie("Moje poprvé", id_melodie="vlastni_a")
    ulozena = melodies.uloz_vlastni_melodie(m)
    assert ulozena is m
    assert melodies.VLASTNI_MELODIE["vlastni_a"] is m
    assert melodies.vlastni_melodie() == [m]


def test_upsert_prepise_stary_zaznam():
    puvodni = melodie("Stará", id_melodie="vlastni_x")
    melodies.uloz_vlastni_melodie(puvodni)
    nova = melodie("Nová", id_melodie="vlastni_x")
    melodies.uloz_vlastni_melodie(nova)
    assert len(melodies.VLASTNI_MELODIE) == 1
    assert melodies.VLASTNI_MELODIE["vlastni_x"].nazev == "Nová"


@pytest.mark.parametrize("problem", [
    "prazdny_nazev", "spatny_druh", "zadne_tony", "spatny_ton",
    "prazdne_id", "mimo_stupnici",
])
def test_neplatna_melodie_odmitnuta(problem):
    pokusy = {
        "prazdny_nazev": lambda: melodie("   "),
        "spatny_druh": lambda: melodie(druh="nesmysl"),
        "zadne_tony": lambda: melodie(tony=()),
        "spatny_ton": lambda: melodie(
            tony=(melodies.Ton("X9", 1.0, 0.0),)),
        "prazdne_id": lambda: melodie(id_melodie="  "),
        "mimo_stupnici": lambda: melodie(
            tony=(melodies.Ton("Cis4", 1.0, 0.0),), mimo=False),
    }
    with pytest.raises(ValueError):
        melodies.uloz_vlastni_melodie(pokusy[problem]())
    assert melodies.VLASTNI_MELODIE == {}


def test_neplatna_nepredefinuje_posledni_platnou():
    """Požadavek: neplatná melodie nesmí přepsat poslední platnou definici."""
    platna = melodie("Platná", id_melodie="vlastni_p")
    melodies.uloz_vlastni_melodie(platna)

    spatna = melodies.Melodie(
        id="vlastni_p", nazev="Poškozená", tony=(), druh=melodies.DRUH_SMUTNA)
    with pytest.raises(ValueError):
        melodies.uloz_vlastni_melodie(spatna)

    assert melodies.VLASTNI_MELODIE["vlastni_p"] is platna


def test_ton_mimo_stupnici_jen_s_povolenim():
    mimo = melodie("S tónem mimo", tony=(melodies.Ton("Cis4", 1.0, 0.0),),
                   mimo=True)
    melodies.uloz_vlastni_melodie(mimo)         # s příznakem projde
    chyby, varovani = melodies.over_pred_ulozenim(mimo)
    assert chyby == []
    assert varovani, "mimo stupnici má být alespoň varování"


def test_smazani():
    m = melodie(id_melodie="vlastni_s")
    melodies.uloz_vlastni_melodie(m)
    assert melodies.smaz_vlastni_melodie("vlastni_s") is True
    assert melodies.smaz_vlastni_melodie("vlastni_s") is False
    assert melodies.vlastni_melodie() == []


def test_vlastni_melodie_podle_druhu_a_serazene():
    melodies.uloz_vlastni_melodie(
        melodie("Zebra", id_melodie="vlastni_1"))
    melodies.uloz_vlastni_melodie(
        melodie("anna", id_melodie="vlastni_2"))
    melodies.uloz_vlastni_melodie(
        melodie("Vítězná věc", id_melodie="vlastni_3",
                druh=melodies.DRUH_VITEZNA))

    smutne = melodies.vlastni_melodie(melodies.DRUH_SMUTNA)
    assert [m.nazev for m in smutne] == ["anna", "Zebra"]   # casefold
    assert [m.id for m in melodies.vlastni_melodie(
        melodies.DRUH_VITEZNA)] == ["vlastni_3"]

    with pytest.raises(ValueError):
        melodies.vlastni_melodie("nesmysl")


def test_nabidka_melodii_obsahuje_vlastni():
    melodies.uloz_vlastni_melodie(
        melodie("Moje smutná", druh=melodies.DRUH_SMUTNA))
    melodii_smutnych = melodies.nabidka_melodii(melodies.DRUH_SMUTNA)
    zaklad = melodies.ZAKLADNI_SMUTNE
    assert len(melodii_smutnych) == len(zaklad) + 1
    popisky = dict(melodii_smutnych)
    id_vlastni = next(iter(melodies.VLASTNI_MELODIE))
    assert popisky[id_vlastni].endswith("(vlastní)")
    # Vítězná nabídka vlastní smutnou melodii neobsahuje.
    assert id_vlastni not in dict(
        melodies.nabidka_melodii(melodies.DRUH_VITEZNA))


def test_je_dostupna_melodie():
    melodies.uloz_vlastni_melodie(melodie(id_melodie="vlastni_d"))
    assert melodies.je_dostupna_melodie(melodies.DRUH_SMUTNA, "vlastni_d")
    assert not melodies.je_dostupna_melodie(melodies.DRUH_VITEZNA,
                                           "vlastni_d")
    assert melodies.je_dostupna_melodie(melodies.DRUH_SMUTNA, None)
    assert not melodies.je_dostupna_melodie(melodies.DRUH_SMUTNA,
                                           "vlastni_neexistuje")
    assert melodies.je_dostupna_melodie(
        melodies.DRUH_SMUTNA, melodies.VYCHOZI_ID[melodies.DRUH_SMUTNA])


def test_ziskej_melodii_pouzije_vlastni_a_transponuje():
    m = melodies.Melodie(
        id="vlastni_c", nazev="Vlastní C", druh=melodies.DRUH_SMUTNA,
        tony=(melodies.Ton("C4", 1.0, 0.0), melodies.Ton("E4", 1.0, 0.0)),
    )
    melodies.uloz_vlastni_melodie(m)

    volba = melodies.ziskej_melodii("G", melodies.DRUH_SMUTNA, "vlastni_c")
    assert volba.zdroj == "vlastni"
    assert volba.varovani is None
    # Transpozice drží tóny v herním rejstříku (stejně jako u
    # přednastavených melodií) — C4/E4 se v G dur ozvou jako G3/H3.
    assert [t.nazev for t in volba.melodie.tony] == ["G3", "H3"]
    assert volba.melodie.id == "vlastni_c"
    assert volba.melodie.druh == melodies.DRUH_SMUTNA


def test_ziskej_melodii_cizi_druh_spada_na_vychozi():
    melodies.uloz_vlastni_melodie(melodie(
        id_melodie="vlastni_jen_vitezna", druh=melodies.DRUH_VITEZNA))
    volba = melodies.ziskej_melodii("C", melodies.DRUH_SMUTNA,
                                    "vlastni_jen_vitezna")
    assert volba.zdroj != "vlastni"
    assert volba.varovani and "výchozí" in volba.varovani


def test_ziskej_melodii_smazana_vlastni_nespadne():
    """Smazané ID — bez pádu, bezpečná náhrada a varování."""
    volba = melodies.ziskej_melodii("C", melodies.DRUH_SMUTNA,
                                    "vlastni_zmizela")
    assert volba.zdroj in ("transpozice", "zalozni")
    assert volba.varovani and "výchozí" in volba.varovani


# ==================================================================
# Serializace (JSON tvar)
# ==================================================================

def test_serializace_kol():
    m = melodie("Ke kolu", id_melodie="vlastni_k",
                tony=(melodies.Ton("D4", 0.5, 0.25),))
    data = melodies.melodie_do_dict(m)
    assert data["id"] == "vlastni_k"
    assert data["druh"] == melodies.DRUH_SMUTNA
    assert data["tony"] == [{"nazev": "D4", "delka": 0.5, "pauza": 0.25}]
    zpet = melodies.melodie_z_dict(data)
    assert zpet == m
    # Výsledek musí být JSON-ovatelný.
    json.dumps(data, ensure_ascii=False)


def test_melodie_z_dict_chyby():
    s = melodies.melodie_do_dict(melodie(id_melodie="vlastni_z"))
    del s["id"]
    with pytest.raises(ValueError):
        melodies.melodie_z_dict(s)

    s = melodies.melodie_do_dict(melodie(id_melodie="vlastni_z"))
    del s["tony"]
    with pytest.raises(ValueError):
        melodies.melodie_z_dict(s)

    s = melodies.melodie_do_dict(melodie(id_melodie="vlastni_z"))
    s["tony"] = "ne seznam"
    with pytest.raises(ValueError):
        melodies.melodie_z_dict(s)

    s = melodies.melodie_do_dict(melodie(id_melodie="vlastni_z"))
    s["tony"] = [{"delka": 1.0, "pauza": 0.0}]        # bez názvu tónu
    with pytest.raises(ValueError):
        melodies.melodie_z_dict(s)

    s = melodies.melodie_do_dict(melodie(id_melodie="vlastni_z"))
    s["tony"] = [{"nazev": "C4", "delka": "jedna", "pauza": 0.0}]
    with pytest.raises(ValueError):
        melodies.melodie_z_dict(s)

    s = melodies.melodie_do_dict(melodie(id_melodie="vlastni_z"))
    s["druh"] = "cokoli"
    with pytest.raises(ValueError):
        melodies.melodie_z_dict(s)

    with pytest.raises(ValueError):
        melodies.melodie_z_dict(["neni slovnik"])


def test_vlastni_json_roundtrip():
    melodies.uloz_vlastni_melodie(melodie(
        "První", id_melodie="vlastni_1", druh=melodies.DRUH_SMUTNA))
    melodies.uloz_vlastni_melodie(melodie(
        "Druhá", id_melodie="vlastni_2", druh=melodies.DRUH_VITEZNA))

    text = melodies.vlastni_do_jsonu()
    nactene, chyby, neplatne_id = melodies.vlastni_z_jsonu(text)
    assert chyby == [] and neplatne_id == []
    assert nactene == melodies.VLASTNI_MELODIE


def test_vlastni_json_poskozene_data():
    nactene, chyby, neplatne_id = melodies.vlastni_z_jsonu(
        "tohle není { json")
    assert nactene is None
    assert chyby and "přečíst" in chyby[0]
    assert neplatne_id == []

    nactene, chyby, _ = melodies.vlastni_z_jsonu('"jen text"')
    assert nactene is None
    assert chyby and "neočekávaný tvar" in chyby[0]

    nactene, chyby, _ = melodies.vlastni_z_jsonu("42")
    assert nactene is None
    assert chyby


def test_vlastni_json_neplatny_zaznam_vynehan():
    platna = melodies.melodie_do_dict(melodie(
        "Platná", id_melodie="vlastni_ok", druh=melodies.DRUH_SMUTNA))
    neplatna = melodies.melodie_do_dict(melodie(
        "Neplatná", id_melodie="vlastni_bad", druh=melodies.DRUH_SMUTNA))
    neplatna["tony"] = []                            # poškozený záznam

    nactene, chyby, neplatne_id = melodies.vlastni_z_jsonu(
        json.dumps([platna, neplatna], ensure_ascii=False))
    assert nactene is not None
    assert list(nactene) == ["vlastni_ok"]
    assert len(chyby) == 1 and "záznam č. 2" in chyby[0]
    assert neplatne_id == ["vlastni_bad"]


def test_vlastni_json_tvar_slovnik_id_z_klice():
    zaznam = melodies.melodie_do_dict(melodie(
        "Z klíče", id_melodie="vlastni_klic", druh=melodies.DRUH_SMUTNA))
    del zaznam["id"]
    nactene, chyby, neplatne_id = melodies.vlastni_z_jsonu(
        json.dumps({"vlastni_klic": zaznam}, ensure_ascii=False))
    assert chyby == [] and neplatne_id == []
    assert "vlastni_klic" in nactene
    assert nactene["vlastni_klic"].id == "vlastni_klic"
