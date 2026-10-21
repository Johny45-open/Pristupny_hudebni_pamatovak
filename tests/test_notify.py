"""Testy přístupných oznámení — panel, opakování, ochrana proti duplicitám.

Dále režimy hlasového výstupu: rozlišení skutečně aktivní čtečky
obrazovky od systémového hlasu (ověřeno proti accessible_output2 0.17).
"""

from __future__ import annotations

import pytest

import notify
from notify import Oznamovac


class FakePanel:
    def __init__(self):
        self.texty: list[str] = []

    def aktualizuj_hlaseni(self, text: str) -> None:
        self.texty.append(text)


class FakeHlas:
    """Náhrada hlasového výstupu — zapisuje volání."""

    def __init__(self):
        self.zavolani: list[tuple] = []

    def get_first_available_output(self):
        return self

    def speak(self, text, interrupt=True, **kwargs):
        self.zavolani.append((text, interrupt))


def test_panel_dostane_kazde_hlaseni():
    o = Oznamovac()
    panel = FakePanel()
    o.nastav_panel(panel)
    o.oznam("První hlášení")
    o.oznam("Druhé hlášení")
    assert panel.texty == ["První hlášení", "Druhé hlášení"]
    assert o.posledni_text == "Druhé hlášení"


def test_fallback_funguje_bez_hlasu():
    """I když hlas selže, text musí být v panelu (přístupná náhradní cesta)."""
    o = Oznamovac()
    o._vystup = None                     # simulate: knihovna není k dispozici
    panel = FakePanel()
    o.nastav_panel(panel)
    vysledek = o.oznam("Chyba, zbývá 2 pokusy")
    assert panel.texty[-1] == "Chyba, zbývá 2 pokusy"
    assert vysledek is True
    assert o.hlas_dostupny is False
    assert "není k dispozici" in o.popis_dostupnosti


def test_opakovani_posledniho_hlaseni():
    o = Oznamovac()
    panel = FakePanel()
    hlas = FakeHlas()
    o._vystup = hlas
    o.nastav_panel(panel)

    o.oznam("Výsledek kola")
    assert hlas.zavolani == [("Výsledek kola", True)]

    # Zopakování znovu promluví, i když se text nezměnil.
    assert o.zopakuj() is True
    assert hlas.zavolani[-1] == ("Výsledek kola", True)
    assert len(hlas.zavolani) == 2
    # Panel se při opakování nezměnil (žádné duplicitní hlášení dovnitř).
    assert panel.texty == ["Výsledek kola"]


def test_neslysi_dvojite_hlaseni_stejneho_textu():
    o = Oznamovac()
    panel = FakePanel()
    hlas = FakeHlas()
    o._vystup = hlas
    o.nastav_panel(panel)

    o.oznam("Stejný text")
    o.oznam("Stejný text")      # duplicita — nemá se promluvit znovu
    assert len(hlas.zavolani) == 1
    assert len(panel.texty) == 2, "panel ale text vždy dostane"


def test_zopakuj_bez_predchoziho_hlaseni():
    o = Oznamovac()
    o._vystup = FakeHlas()
    assert o.zopakuj() is False


def test_chyba_vystupu_nezrusi_panel():
    class KaziciVystup:
        def get_first_available_output(self):
            raise RuntimeError("odečítač spadl")

        def speak(self, *a, **k):
            raise RuntimeError("spadl")

    o = Oznamovac()
    o._vystup = KaziciVystup()
    panel = FakePanel()
    o.nastav_panel(panel)
    assert o.oznam("I tak důležité") is True
    assert panel.texty[-1] == "I tak důležité"
    assert o.zopakuj() is True     # nesmí spadnout


# ==================================================================
# Režimy hlasového výstupu — čtečka vs. systémový hlas
# ==================================================================

class FakeVystup:
    """Náhrada výstupu accessible_output2 (s is_active / is_system_output)."""

    def __init__(self, name, system=False, active=True, pada=False):
        self.name = name
        self._system = system
        self._active = active
        self._pada = pada
        self.zavolani: list[str] = []

    def is_active(self):
        if self._pada:
            raise RuntimeError("is_active spadl")
        return self._active

    def is_system_output(self):
        return self._system

    def speak(self, text, interrupt=True, **kwargs):
        self.zavolani.append(text)


class FakeVystupBezIsActive:
    """Výstup bez metody is_active (jako sapi4 v nainstalované knihovně)."""

    name = "sapi4"
    zavolani: list[str] = []

    def is_system_output(self):
        return True

    def speak(self, text, interrupt=True, **kwargs):
        self.zavolani.append(text)


class FakeAuto:
    """Náhrada Auto() se seznamem outputs jako skutečná knihovna."""

    def __init__(self, outputs):
        self.outputs = outputs

    def get_first_available_output(self):
        for vystup in self.outputs:
            if hasattr(vystup, "is_active"):
                try:
                    if vystup.is_active():
                        return vystup
                except Exception:
                    continue
        return None


def oznamovac_s(outputs) -> tuple[Oznamovac, FakePanel]:
    o = Oznamovac()
    o._vystup = FakeAuto(outputs)
    panel = FakePanel()
    o.nastav_panel(panel)
    return o, panel


def test_rezimy_jsou_jednoznaucne():
    assert notify.REZIMY_HLASU == (
        "vypnuto", "jen_odecitas", "vcetne_systemu")
    assert set(notify.POPISKY_REZIMU) == set(notify.REZIMY_HLASU)
    # Výchozí režim odpovídá chování před zavedením režimů.
    assert notify.NastaveniHlasu().rezim == "vcetne_systemu"
    # Nepovolený režim se odmítne.
    with pytest.raises(ValueError):
        notify.NastaveniHlasu(rezim="nesmysl").over()
    with pytest.raises(ValueError):
        Oznamovac().nastav_rezim("nesmysl")


def test_vypnuto_nemluvi_ale_panel_zustava():
    nvda = FakeVystup("NVDA", active=True)
    o, panel = oznamovac_s([nvda])
    o.nastav_rezim("vypnuto")

    assert o.oznam("Kolo skončilo") is True
    assert panel.texty[-1] == "Kolo skončilo"      # panel vždy
    assert nvda.zavolani == []                      # řeč zticha
    assert o.hlas_dostupny is False
    assert "vypnutý" in o.popis_dostupnosti


def test_samy_sistemovy_hlas_neni_potvrzena_ctecka():
    """SAPI5 (system=True) nesmí stačit k potvrzení čtečky."""
    sapi = FakeVystup("sapi5", system=True, active=True)
    o, _panel = oznamovac_s([sapi])
    stav = o.stav_hlasu()
    assert stav.odecitas is None
    assert stav.system_dostupny is True
    assert "není potvrzena" in o.popis_dostupnosti


def test_jen_odecitas_bez_ctecky_mlci_i_kdyz_je_sapi():
    sapi = FakeVystup("sapi5", system=True, active=True)
    o, panel = oznamovac_s([sapi])
    o.nastav_rezim("jen_odecitas")

    o.oznam("Důležité hlášení")
    assert sapi.zavolani == []
    assert panel.texty[-1] == "Důležité hlášení"   # text zůstává
    assert o.hlas_dostupny is False
    assert "hlasitě nemluví" in o.popis_dostupnosti


def test_jen_odecitas_mlci_kdyz_je_ctecka_neaktivni():
    nvda = FakeVystup("NVDA", active=False)
    sapi = FakeVystup("sapi5", system=True, active=True)
    o, _panel = oznamovac_s([nvda, sapi])
    o.nastav_rezim("jen_odecitas")
    o.oznam("Text")
    assert nvda.zavolani == [] and sapi.zavolani == []
    assert o.stav_hlasu().odecitas is None


def test_jen_odecitas_mlci_pres_neznamy_vystup():
    """Výstup mimo známé čtečky (i aktivní) není potvrzení čtečky."""
    cizi = FakeVystup("NejakaRec", active=True)
    o, _panel = oznamovac_s([cizi])
    o.nastav_rezim("jen_odecitas")
    o.oznam("Text")
    assert cizi.zavolani == []
    assert o.stav_hlasu().odecitas is None


def test_jen_odecitas_mlci_kdyz_odecitas_pada():
    """Nespolehlivé is_active se nepovažuje za potvrzení aktivity."""
    nvda = FakeVystup("NVDA", pada=True)
    sapi = FakeVystup("sapi5", system=True, active=True)
    o, _panel = oznamovac_s([nvda, sapi])
    o.nastav_rezim("jen_odecitas")
    o.oznam("Text")
    assert nvda.zavolani == [] and sapi.zavolani == []
    assert o.stav_hlasu().odecitas is None
    assert o.stav_hlasu().chyba is None


def test_jen_odecitas_mlci_bez_metody_is_active():
    """sapi4 podobné výstupy bez is_active nejsou potvrzení čtečky."""
    sapi4 = FakeVystupBezIsActive()
    o, _panel = oznamovac_s([sapi4])
    o.nastav_rezim("jen_odecitas")
    o.oznam("Text")
    assert sapi4.zavolani == []
    o.nastav_rezim("vcetne_systemu")
    # Bez potvrzení aktivity ale o systémový výstup neopřeme — v
    # výchozím režimu by řeč vyžadovala aktivitu, kterou nelze ověřit.
    o.oznam("Text 2")
    assert len(sapi4.zavolani) == 0


def test_jen_odecitas_mlci_s_atrapou_bez_outputs():
    """Staré atrapy bez seznamu outputs — čtečku nelze potvrdit."""
    o = Oznamovac()
    o._vystup = FakeHlas()
    o.nastav_rezim("jen_odecitas")
    o.oznam("Text")
    assert o._vystup.zavolani == []
    assert o.hlas_dostupny is False
    # Ve výchozím režimu atrapa normálně mluví (zpětná kompatibilita).
    o.nastav_rezim("vcetne_systemu")
    o.oznam("Text 2")
    assert o._vystup.zavolani == [("Text 2", True)]


def test_jen_odecitas_mlci_bez_jakehokoli_vystupu():
    o, panel = oznamovac_s([])
    o.nastav_rezim("jen_odecitas")
    o.oznam("Bez hlasu jde text do panelu")
    assert panel.texty[-1] == "Bez hlasu jde text do panelu"
    assert o.hlas_dostupny is False


def test_vcetne_systemu_uprednostni_potvrzenou_ctecku():
    sapi = FakeVystup("sapi5", system=True, active=True)
    nvda = FakeVystup("NVDA", active=True)
    o, _panel = oznamovac_s([sapi, nvda])
    o.oznam("Mluv přes čtečku")
    assert nvda.zavolani == ["Mluv přes čtečku"]
    assert sapi.zavolani == []


def test_vcetne_systemu_pouzije_sapi_bez_ctecky():
    nvda = FakeVystup("NVDA", active=False)
    sapi = FakeVystup("sapi5", system=True, active=True)
    o, _panel = oznamovac_s([nvda, sapi])
    o.oznam("Systémový hlas")
    assert sapi.zavolani == ["Systémový hlas"]
    assert o.stav_hlasu().odecitas is None
    assert o.stav_hlasu().system_dostupny is True


def test_stav_hlasu_uvede_nazev_ctecky():
    jaws = FakeVystup("jaws", active=True)
    sapi = FakeVystup("sapi5", system=True, active=True)
    o, _panel = oznamovac_s([jaws, sapi])
    stav = o.stav_hlasu()
    assert stav.odecitas == "jaws"
    assert stav.system_dostupny is True
    assert stav.nejaky_vystup is True
    popis = o.popis_dostupnosti
    assert "jaws" in popis and "Systémový hlas" in popis


def test_stav_hlasu_bez_vystupu():
    o = Oznamovac()
    o._vystup = None
    stav = o.stav_hlasu()
    assert stav.odecitas is None
    assert stav.system_dostupny is False
    assert stav.nejaky_vystup is False


def test_zkusebni_hlaseni_neprepisuje_panel():
    nvda = FakeVystup("NVDA", active=True)
    o, panel = oznamovac_s([nvda])
    o.oznam("Poslední herní hlášení")
    pocet_po_oznameni = len(nvda.zavolani)          # běžné hlášení promluvilo

    assert o.zkusebni_hlaseni() is True
    assert panel.texty == ["Poslední herní hlášení"], \
        "zkušební hláška nesmí přepsat panel"
    # Stejný text znovu — zkusebni_hlasení musí mluvit vždy.
    assert o.zkusebni_hlaseni() is True
    assert len(nvda.zavolani) == pocet_po_oznameni + 2
    assert panel.texty == ["Poslední herní hlášení"]


def test_zkusebni_hlaseni_v_rezimu_vypnuto():
    nvda = FakeVystup("NVDA", active=True)
    o, panel = oznamovac_s([nvda])
    o.nastav_rezim("vypnuto")
    assert o.zkusebni_hlaseni() is False
    assert nvda.zavolani == []


def test_zkusebni_hlaseni_v_rezimu_jen_odecitas_bez_ctecky():
    sapi = FakeVystup("sapi5", system=True, active=True)
    o, _panel = oznamovac_s([sapi])
    o.nastav_rezim("jen_odecitas")
    assert o.zkusebni_hlaseni() is False
    assert sapi.zavolani == []
