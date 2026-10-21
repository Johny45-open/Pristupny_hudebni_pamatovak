"""Testy trvalého ukládání — reálné QSettings, reálný JSON soubor.

Žádné mocky úložiště: testy čtou a ověřují skutečně zapsané soubory.
Ověřené chování PyQt6 6.11 (viz docstring uloziste.py):
- QSettings(org, app) → nativní formát (na Windows registr, žádný soubor),
- QSettings(IniFormat, UserScope, org, app) → skutečný .ini soubor.
"""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QSettings

import melodies
import notify
import uloziste


@pytest.fixture(autouse=True)
def prazdny_registr():
    melodies.VLASTNI_MELODIE.clear()
    yield
    melodies.VLASTNI_MELODIE.clear()


@pytest.fixture
def ini_nastaveni(tmp_path):
    """Reálný INI soubor — JSON s melodiemi má ležet vedle něj."""
    return QSettings(str(tmp_path / "nastaveni.ini"),
                     QSettings.Format.IniFormat)


def nativni_nastaveni() -> QSettings:
    """QSettings v nativním formátu (fileName nekončí na .ini)."""
    return QSettings(QSettings.Format.NativeFormat,
                     QSettings.Scope.UserScope,
                     uloziste.ORGANIZACE, uloziste.APLIKACE)


def melodie(id_melodie, nazev="Testovací", druh=None, mimo=False):
    return melodies.Melodie(
        id=id_melodie,
        nazev=nazev,
        tony=(melodies.Ton("C4", 1.0, 0.0), melodies.Ton("E4", 0.5, 0.25)),
        druh=druh or melodies.DRUH_SMUTNA,
        povolit_mimo_stupnici=mimo,
        tempo_bpm=120.0,
    )


# ==================================================================
# Určení cesty k JSON souboru
# ==================================================================

def test_cesta_k_melodiim_vedle_ini(ini_nastaveni, tmp_path):
    assert ini_nastaveni.fileName().lower().endswith(".ini")
    cesta = uloziste.cesta_k_melodiim(ini_nastaveni)
    assert cesta == tmp_path / uloziste.NAZEV_SOUBORU_MELODII


def test_cesta_k_melodiim_u_nativniho_formatu(tmp_path):
    """Nativní formát není soubor — melodie jdou do dat aplikace."""
    s = nativni_nastaveni()
    assert not s.fileName().lower().endswith(".ini")
    cesta = uloziste.cesta_k_melodiim(s, adresar_dat=tmp_path)
    assert cesta == tmp_path / uloziste.NAZEV_SOUBORU_MELODII


def test_vychozi_adresar_ma_slozku_aplikace(monkeypatch, tmp_path):
    """Bez jména aplikace Qt vrací jen %APPDATA% — doplní se organizace."""
    cil = tmp_path / "Roaming"

    class FakeQStandardPaths:
        class StandardLocation:
            AppDataLocation = 0

        @staticmethod
        def writableLocation(_loc):
            return str(cil)

    monkeypatch.setattr(uloziste, "QStandardPaths", FakeQStandardPaths)

    cesta = uloziste.cesta_k_melodiim(nativni_nastaveni())
    assert cesta == (cil / uloziste.ORGANIZACE / uloziste.APLIKACE
                     / uloziste.NAZEV_SOUBORU_MELODII)

    # Když Qt už jméno aplikace obsahuje, nezdvojuje se.
    cil = tmp_path / "Roaming" / uloziste.APLIKACE
    cesta = uloziste.cesta_k_melodiim(nativni_nastaveni())
    assert cesta == cil / uloziste.NAZEV_SOUBORU_MELODII
    assert cesta.parts.count(uloziste.APLIKACE) == 1


# ==================================================================
# Skutečný zápis a načtení
# ==================================================================

def test_skutecny_zapis_a_nacteni(ini_nastaveni, tmp_path):
    puvodni = [melodie("vlastni_1", "První"),
               melodie("vlastni_2", "Druhá", druh=melodies.DRUH_VITEZNA)]
    for m in puvodni:
        melodies.uloz_vlastni_melodie(m)

    cesta = uloziste.uloz_vlastni_melodie(ini_nastaveni)
    assert cesta.exists() and cesta.is_file()
    obsah = json.loads(cesta.read_text(encoding="utf-8"))
    # Řazení podle názvu (jako v nabídkách), proto hledáme podle id.
    assert {zaznam["id"] for zaznam in obsah} == {"vlastni_1", "vlastni_2"}
    zaznam_1 = next(z for z in obsah if z["id"] == "vlastni_1")
    zaznam_2 = next(z for z in obsah if z["id"] == "vlastni_2")
    assert zaznam_1["druh"] == melodies.DRUH_SMUTNA
    assert zaznam_2["druh"] == melodies.DRUH_VITEZNA
    assert zaznam_1["nazev"] == "První"
    assert zaznam_1["tony"][0] == {"nazev": "C4", "delka": 1.0, "pauza": 0.0}

    # Vymažeme paměť a znovu načteme ze souboru (žádný mock).
    melodies.VLASTNI_MELODIE.clear()
    zmeneno, chyby = uloziste.nacti_vlastni_melodie(ini_nastaveni)
    assert zmeneno is True and chyby == []
    assert melodies.VLASTNI_MELODIE == {m.id: m for m in puvodni}


def test_zapis_nezanecha_docasny_soubor(ini_nastaveni, tmp_path):
    melodies.uloz_vlastni_melodie(melodie("vlastni_tmp"))
    uloziste.uloz_vlastni_melodie(ini_nastaveni)
    zbytky = list(tmp_path.glob("*.tmp"))
    assert zbytky == [], f"zůstaly dočasné soubory: {zbytky}"


def test_neplatna_melodie_nezmeni_soubor(ini_nastaveni, tmp_path):
    """Neplatná melodie nesmí přepsat poslední platnou definici."""
    melodies.uloz_vlastni_melodie(melodie("vlastni_ok", "Platná"))
    uloziste.uloz_vlastni_melodie(ini_nastaveni)
    predchozi = (tmp_path / uloziste.NAZEV_SOUBORU_MELODII).read_bytes()

    # Přímým zápisem do registru vložíme neplatnou melodii.
    melodies.VLASTNI_MELODIE["vlastni_bad"] = melodies.Melodie(
        id="vlastni_bad", nazev="", tony=(),
        druh=melodies.DRUH_SMUTNA)
    with pytest.raises(ValueError, match="nezměněn"):
        uloziste.uloz_vlastni_melodie(ini_nastaveni)

    assert (tmp_path / uloziste.NAZEV_SOUBORU_MELODII).read_bytes() \
        == predchozi, "soubor se nesmí změnit"
    assert not list(tmp_path.glob("*.tmp"))


def test_poskozeny_json_necha_data_intaktni(ini_nastaveni, tmp_path):
    """Poškozený JSON: registr se nemění, přednastavené melodie zůstávají."""
    melodies.uloz_vlastni_melodie(melodie("vlastni_ok", "Poškozený scénář"))
    uloziste.uloz_vlastni_melodie(ini_nastaveni)
    uloziste.nacti_vlastni_melodie(ini_nastaveni)   # načteno do paměti
    platny_pred = dict(melodies.VLASTNI_MELODIE)

    soubor = tmp_path / uloziste.NAZEV_SOUBORU_MELODII
    soubor.write_text("{{ tohle není JSON", encoding="utf-8")

    zmeneno, chyby = uloziste.nacti_vlastni_melodie(ini_nastaveni)
    assert zmeneno is False
    assert chyby and "přečíst" in chyby[0]
    assert melodies.VLASTNI_MELODIE == platny_pred, \
        "poškozený soubor nesmí zahodit platnou paměť"

    # Přednastavené melodie jsou nedotčené úplně vždy.
    volba = melodies.ziskej_melodii("C", melodies.DRUH_SMUTNA)
    assert volba.melodie.tony


def test_neplatny_zaznam_nepreplachne_platnou_verzi(ini_nastaveni,
                                                    tmp_path):
    """Soubor s poškozeným záznamem nesmí přetlačit platnou verzi z paměti."""
    dobra = melodie("vlastni_x", "Dobrá verze")
    melodies.uloz_vlastni_melodie(dobra)
    uloziste.uloz_vlastni_melodie(ini_nastaveni)
    melodies.VLASTNI_MELODIE.clear()
    uloziste.nacti_vlastni_melodie(ini_nastaveni)
    assert melodies.VLASTNI_MELODIE["vlastni_x"].nazev == "Dobrá verze"

    # Do souboru zapíšeme záznam se stejným ID, ale prázdnými tóny.
    poskozeny = melodies.melodie_do_dict(dobra)
    poskozeny["nazev"] = "Rozbitá verze"
    poskozeny["tony"] = []
    (tmp_path / uloziste.NAZEV_SOUBORU_MELODII).write_text(
        json.dumps([poskozeny], ensure_ascii=False), encoding="utf-8")

    zmeneno, chyby = uloziste.nacti_vlastni_melodie(ini_nastaveni)
    assert zmeneno is True
    assert chyby and "záznam č. 1" in chyby[0]
    assert melodies.VLASTNI_MELODIE["vlastni_x"].nazev == "Dobrá verze", \
        "neplatná verze nesmí přepsat poslední platnou"


def test_chybejici_soubor_neje_chyba(ini_nastaveni, tmp_path):
    assert not (tmp_path / uloziste.NAZEV_SOUBORU_MELODII).exists()
    zmeneno, chyby = uloziste.nacti_vlastni_melodie(ini_nastaveni)
    assert (zmeneno, chyby) == (False, [])


def test_zapis_probiha_pres_docasny_soubor(ini_nastaveni, tmp_path,
                                           monkeypatch):
    """Zápis jde přes .tmp + os.replace; při selhání zůstane starý soubor."""
    melodies.uloz_vlastni_melodie(melodie("vlastni_stara"))
    uloziste.uloz_vlastni_melodie(ini_nastaveni)
    predchozi = (tmp_path / uloziste.NAZEV_SOUBORU_MELODII).read_bytes()

    def padici_replace(*_args, **_kwargs):
        raise OSError("disk je plný")

    monkeypatch.setattr(uloziste.os, "replace", padici_replace)
    melodies.uloz_vlastni_melodie(melodie("vlastni_nova"))
    with pytest.raises(OSError, match="disk je plný"):
        uloziste.uloz_vlastni_melodie(ini_nastaveni)
    monkeypatch.undo()

    assert (tmp_path / uloziste.NAZEV_SOUBORU_MELODII).read_bytes() \
        == predchozi, "po chybě musí zůstat poslední platný soubor"
    assert not list(tmp_path.glob("*.tmp")), \
        "dočasný soubor se po chybě musí uklidit"


# ==================================================================
# Nastavení hlasového výstupu
# ==================================================================

def test_nastaveni_hlasu_roundtrip(ini_nastaveni, tmp_path):
    for rezim in notify.REZIMY_HLASU:
        uloziste.uloz_nastaveni_hlasu(notify.NastaveniHlasu(rezim=rezim),
                                      ini_nastaveni)
        # Čtení přes NOVÝ objekt = skutečné přečtení ze souboru.
        nacteno = QSettings(str(tmp_path / "nastaveni.ini"),
                            QSettings.Format.IniFormat)
        assert uloziste.nacti_nastaveni_hlasu(nacteno).rezim == rezim


def test_nastaveni_hlasu_vychoz_a_neplatna_hodnota(ini_nastaveni):
    assert uloziste.nacti_nastaveni_hlasu(ini_nastaveni) == \
        notify.NastaveniHlasu()
    ini_nastaveni.setValue(uloziste.KLIC_HLASU, "nesmysl")
    ini_nastaveni.sync()
    assert uloziste.nacti_nastaveni_hlasu(ini_nastaveni) == \
        notify.NastaveniHlasu(), "neplatná hodnota → výchozí režim"


def test_uloz_nastaveni_hlasu_odmita_neplatny_rezim(ini_nastaveni):
    with pytest.raises(ValueError):
        uloziste.uloz_nastaveni_hlasu(
            notify.NastaveniHlasu(rezim="nesmysl"), ini_nastaveni)
