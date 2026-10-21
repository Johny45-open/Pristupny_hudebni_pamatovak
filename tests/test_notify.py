"""Testy přístupných oznámení — panel, opakování, ochrana proti duplicitám."""

from __future__ import annotations

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
