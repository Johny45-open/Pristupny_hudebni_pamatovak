"""Vlákno pro přehrávání zvuku (QThread) s kooperativním přerušením.

Zásady:
- přehrávání NIKDY neběží v hlavním vlákně GUI,
- přerušení je kooperativní: příznak se kontroluje po 20 ms,
  zastavení právě hrajícího zvuku = ``channel.stop()`` (konkrétní kanál),
- worker nikdy nepoužívá ``terminate()`` ani destrukci za běhu,
- GUI spouští vždy jen JEDEN worker současně (souběh je zakázán).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from PyQt6.QtCore import QThread, pyqtSignal

from sound import ZvukovyMotor

KROK_CEKANI_S = 0.02          # čtyřikrát za 100 ms — reakce na přerušení


@dataclass(frozen=True)
class Uloha:
    """Úloha přehrávání: posledek kroků + identifikace pro GUI."""

    typ: str                  # "sekvence" | "vitezna" | "smutna" | "ton" | "ukazka"
    kroky: tuple              # tuple[KrokPrehravani, ...]
    popis: str = ""


class Prehravac(QThread):
    """Worker: přehraje jednu úlohu a skončí.

    Signály:
    - dokonceno(typ, preruseno): úloha doběhla (preruseno=True při přerušení)
    - zmena_stavu(text): průběžný stav pro stavový panel
    """

    dokonceno = pyqtSignal(str, bool)
    zmena_stavu = pyqtSignal(str)

    def __init__(self, motor: ZvukovyMotor, uloha: Uloha, parent=None) -> None:
        super().__init__(parent)
        self._motor = motor
        self._uloha = uloha
        self._priznak_prerusit = False

    # ------------------------------------------------------------------
    # Kooperativní přerušení
    # ------------------------------------------------------------------

    def prerus(self) -> None:
        """Požádá o přerušení a okamžitě zastaví právě hrající kanál."""
        self._priznak_prerusit = True
        self._motor.zastav_kanal()

    @property
    def preruseno(self) -> bool:
        return self._priznak_prerusit

    # ------------------------------------------------------------------
    # Interní čekání (20ms kroky, reaguje na přerušení)
    # ------------------------------------------------------------------

    def _cekaj(self, sekund: float) -> bool:
        """Čeká zadaný čas po 20ms krocích. Vrátí False při přerušení."""
        cil = time.monotonic() + sekund
        while time.monotonic() < cil:
            if self._priznak_prerusit:
                return False
            zbyva = cil - time.monotonic()
            time.sleep(min(KROK_CEKANI_S, max(0.0, zbyva)))
        return not self._priznak_prerusit

    # ------------------------------------------------------------------
    # Hlavní smyčka (běží ve vlákně)
    # ------------------------------------------------------------------

    def run(self) -> None:     # noqa: C901 — přehlednější než rozdělení
        preruseno = False
        try:
            self.zmena_stavu.emit(f"Přehrávám: {self._uloha.popis}")
            for krok in self._uloha.kroky:
                if self._priznak_prerusit:
                    preruseno = True
                    break

                # Vytvoření zvuku (v tichém režimu vrátí None).
                # Impulzní kroky = krátký rytmický klep (průvodce
                # rytmem); běžné tóny jdou stejnou cestou jako dřív.
                if krok.impuls:
                    zvuk = self._motor.vytvor_impuls(krok.zvuk_s)
                else:
                    zvuk = self._motor.vytvor_zvuk(krok.midi, krok.zvuk_s)
                kanal = self._motor.prehraj(zvuk)

                if kanal is not None:
                    # Zvukové zařízení: čekáme, dokud kanál hraje.
                    while kanal.get_busy():
                        if self._priznak_prerusit:
                            self._motor.zastav_kanal()   # channel.stop()
                            preruseno = True
                            break
                        time.sleep(KROK_CEKANI_S)
                    if preruseno:
                        break
                else:
                    # Tichý režim: simulujeme délku tónu, aby časování
                    # a přerušování fungovaly stejně jako se zvukem.
                    if not self._cekaj(krok.zvuk_s):
                        preruseno = True
                        break

                if krok.pauza_s > 0 and not self._cekaj(krok.pauza_s):
                    preruseno = True
                    break
        except Exception as e:   # noqa: BLE001 — chyba nesmí shodit vlákno
            self.zmena_stavu.emit(f"Chyba při přehrávání: {e}")
            preruseno = True
        finally:
            self._motor.zastav_kanal()
            self.dokonceno.emit(self._uloha.typ, preruseno)
