"""Přístupná oznámení — dvě nezávislé cesty + fallback.

1. Primární cesta: ``accessible_output2`` (SAPI/NSAPI) — hlasitá
   oznámení, která slyší NVDA i JAWS, i když by Qt přístupnost
   selhala.
2. Doplňková cesta: zaměřitelný stavový panel v GUI — jeho text
   (včetně přístupného názvu) je vždy čitelný odečítačem, i když
   hlasový výstup zcela selže. Panel nabízí i akci
   „Zopakovat poslední hlášení“.

Ochrana proti duplicitám: stejný text se nehlásí dvakrát za sebou.
Oznámení NIKDY nemění fokus.
"""

from __future__ import annotations

from typing import Protocol


class PanelHlaseni(Protocol):
    """Rozhraní stavového panelu v GUI."""

    def aktualizuj_hlaseni(self, text: str) -> None: ...


class Oznamovac:
    """Spojuje hlasový výstup a stavový panel, hlídá duplicity."""

    def __init__(self) -> None:
        self._panel: PanelHlaseni | None = None
        self._vystup = None
        self._chyba: str | None = None
        self.posledni_text: str = ""

        try:
            from accessible_output2.outputs.auto import Auto
            self._vystup = Auto()
        except Exception as e:   # noqa: BLE001 — knihovna nemusí být k dispozici
            self._chyba = f"{type(e).__name__}: {e}"
            self._vystup = None

    # ------------------------------------------------------------------
    # Nastavení
    # ------------------------------------------------------------------

    def nastav_panel(self, panel: PanelHlaseni) -> None:
        self._panel = panel

    @property
    def hlas_dostupny(self) -> bool:
        """True, pokud je právě aktivní nějaký hlasový odečítač."""
        if self._vystup is None:
            return False
        try:
            return self._vystup.get_first_available_output() is not None
        except Exception:   # noqa: BLE001
            return False

    @property
    def popis_dostupnosti(self) -> str:
        if self._vystup is None:
            return f"Hlasový výstup není k dispozici ({self._chyba})."
        if self.hlas_dostupny:
            return "Hlasový výstup je připraven."
        return ("Hlasový výstup je nainstalovaný, ale žádný odečítač "
                "obrazovky teď není aktivní.")

    # ------------------------------------------------------------------
    # Oznamování
    # ------------------------------------------------------------------

    def oznam(self, text: str, hlasite: bool = True) -> bool:
        """Oznámí text.

        - vždy ho zapíše do stavového panelu (přístupná náhradní cesta),
        - pokud ``hlasite`` a je dostupný hlasový výstup, ohlásí ho i hlasitě,
        - stejný text jako minule se opakuje jen do panelu, ne hlasitě
          (ochrana proti dvojí řeči).
        Vrací True, pokud šlo o nové (neduplicitní) hlášení.
        """
        novy = text != self.posledni_text
        self.posledni_text = text

        if self._panel is not None:
            self._panel.aktualizuj_hlaseni(text)

        if hlasite and novy:
            self._mluv(text)
        return novy

    def zopakuj(self) -> bool:
        """Zopakuje poslední hlášení hlasitě (přes F6 / tlačítko)."""
        if not self.posledni_text:
            return False
        self._mluv(self.posledni_text, vzdy=True)
        return True

    def _mluv(self, text: str, vzdy: bool = False) -> bool:
        if self._vystup is None:
            return False
        try:
            self._vystup.speak(text, interrupt=True)
            return True
        except Exception as e:   # noqa: BLE001
            self._chyba = f"{type(e).__name__}: {e}"
            return False
