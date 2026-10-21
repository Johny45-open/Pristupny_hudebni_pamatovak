"""Přístupná oznámení — dvě nezávislé cesty + nastavitelný hlasový výstup.

1. Primární cesta: ``accessible_output2`` (SAPI/NSAPI) — hlasitá
   oznámení, která slyší NVDA i JAWS, i když by Qt přístupnost
   selhala.
2. Doplňková cesta: zaměřitelný stavový panel v GUI — jeho text
   (včetně přístupného názvu) je vždy čitelný odečítačem, i když
   hlasový výstup zcela selže. Panel nabízí i akci
   „Zopakovat poslední hlášení“.

Ochrana proti duplicitám: stejný text se nehlásí dvakrát za sebou.
Oznámení NIKDY nemění fokus.

Rozlišení „čtečka vs. systémový hlas“ (ověřeno proti
``accessible_output2`` 0.17):
- aktivní odečítač = výstup se známým názvem čtečky, u kterého
  ``is_active()`` vrátí True bez výjimky;
- samotná dostupnost ``Auto()`` NEBO přítomnost systémového hlasu
  (``sapi5``, ``is_system_output() == True``) se za potvrzení
  čtečky NEPOVAŽUJE;
- chybí-li potvrzení čtečky, režim ``jen_odecitas`` zůstane zticha
  (text jde dál do stavového panelu).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# ---------------------------------------------------------------------------
# Režimy hlasového výstupu (jednoznačné, uživatelsky popsané)
# ---------------------------------------------------------------------------

REZIM_VYPNUTO = "vypnuto"
"""Hlas je zakázaný. Oznámení chodí jen na stavový panel."""

REZIM_JEN_ODECITAC = "jen_odecitas"
"""Hlasitě mluví JEN potvrzená aktivní čtečka obrazovky.

Bez potvrzené čtečky aplikace nehlasitě nemluví (i kdyby byl
dostupný systémový hlas SAPI) — text ale vždy zůstane na panelu.
"""

REZIM_VCETNE_SYSTEMU = "vcetne_systemu"
"""Hlas i bez čtečky: přednost má potvrzená čtečka, jinak systémový hlas.

Toto je výchozí režim (odpovídá chování před zavedením režimů).
"""

REZIMY_HLASU: tuple[str, ...] = (
    REZIM_VYPNUTO, REZIM_JEN_ODECITAC, REZIM_VCETNE_SYSTEMU,
)

POPISKY_REZIMU: dict[str, str] = {
    REZIM_VYPNUTO: "Hlas vypnut (jen text na stavovém panelu)",
    REZIM_JEN_ODECITAC: "Hlas jen s potvrzenou čtečkou obrazovky",
    REZIM_VCETNE_SYSTEMU: "Hlas i bez čtečky (systémový hlas)",
}

# Názvy výstupů accessible_output2, jejichž is_active() spolehlivě
# potvrzuje běžící čtečku obrazovky. SAPI (sapi4/sapi5), Linux TTS
# ani VoiceOver se mezi čtečky nepočítají.
ZNAME_ODECITACE = frozenset({
    "NVDA",             # nvda.py — nvdaController_testIfRunning()
    "jaws",             # jaws.py — SayString / okno JFWUI2
    "System Access",    # system_access.py — SA_IsRunning()
    "Dolphin",          # dolphin.py
    "PC Talker",        # pc_talker.py
    "Window-Eyes",      # window_eyes.py
    "ZDSR",             # zdsr.py
})


class PanelHlaseni(Protocol):
    """Rozhraní stavového panelu v GUI."""

    def aktualizuj_hlaseni(self, text: str) -> None: ...


# ---------------------------------------------------------------------------
# Nastavení a stav hlasu
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NastaveniHlasu:
    """Nastavení hlasového výstupu (ukládá se trvale přes uloziste)."""

    rezim: str = REZIM_VCETNE_SYSTEMU

    def over(self) -> None:
        if self.rezim not in REZIMY_HLASU:
            raise ValueError(
                f"Neznámý režim hlasového výstupu: {self.rezim!r}")


@dataclass(frozen=True)
class StavHlasu:
    """Výsledek detekce hlasového výstupu."""

    rezim: str
    odecitas: str | None      # potvrzená aktivní čtečka (název výstupu)
    system_dostupny: bool     # aktivní systémový hlas (SAPI apod.)
    nejaky_vystup: bool       # existuje vůbec nějaký dostupný výstup
    chyba: str | None = None  # chyba knihovny / výstupu


# ---------------------------------------------------------------------------
# Oznamovac
# ---------------------------------------------------------------------------


class Oznamovac:
    """Spojuje hlasový výstup a stavový panel, hlídá duplicity."""

    def __init__(self) -> None:
        self._panel: PanelHlaseni | None = None
        self._vystup = None
        self._chyba: str | None = None
        self._rezim: str = REZIM_VCETNE_SYSTEMU
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

    def nastav_rezim(self, rezim: str) -> None:
        """Nastaví režim hlasového výstupu (viz ``REZIMY_HLASU``)."""
        if rezim not in REZIMY_HLASU:
            raise ValueError(f"Neznámý režim hlasového výstupu: {rezim!r}")
        self._rezim = rezim

    @property
    def rezim(self) -> str:
        return self._rezim

    # ------------------------------------------------------------------
    # Detekce: čtečka vs. systémový hlas
    # ------------------------------------------------------------------

    def _kandidati(self) -> list[tuple[object, bool]]:
        """Seznam (výstup, je_aktivní) — nikdy nevyhazuje výjimku.

        Pro skutečný ``Auto`` bereme ``outputs`` a ptáme se každý
        výstup zvlášť (u ``sapi4`` metoda ``is_active`` chybí — ověřeno).
        Pro atrapy bez ``outputs`` (testy) použijeme
        ``get_first_available_output()`` — tam dostupnost předpokládáme.
        """
        vystup = self._vystup
        if vystup is None:
            return []

        outs = getattr(vystup, "outputs", None)
        if isinstance(outs, (list, tuple)) and outs:
            return [(o, self._je_aktivni(o)) for o in outs]

        # Záložní cesta (výstup bez seznamu outputs).
        try:
            prvni = vystup.get_first_available_output()
        except Exception:   # noqa: BLE001
            return []
        if prvni is None:
            return []
        # Dostupnost už potvrdil volající; jen reagujeme na is_active(False).
        return [(prvni, self._je_aktivni(prvni, vychozi=True))]

    @staticmethod
    def _je_aktivni(vystup, vychozi: bool = False) -> bool:
        """True jen pokud výstup aktivitu potvrdí (bez výjimky)."""
        if not hasattr(vystup, "is_active"):
            # Metoda chybí (sapi4, atrapa) — potvrdit nelze.
            return vychozi
        try:
            return bool(vystup.is_active())
        except Exception:   # noqa: BLE001
            return False

    @staticmethod
    def _je_odecitas(vystup) -> bool:
        """True jen pro známou čtečku, která potvrdila aktivitu."""
        nazev = getattr(vystup, "name", None)
        return nazev in ZNAME_ODECITACE

    @staticmethod
    def _je_system(vystup) -> bool:
        try:
            return bool(vystup.is_system_output())
        except Exception:   # noqa: BLE001
            return bool(getattr(vystup, "system_output", False))

    def stav_hlasu(self) -> StavHlasu:
        """Aktuální detekce: potvrzená čtečka / systémový hlas / nic."""
        if self._vystup is None:
            return StavHlasu(
                rezim=self._rezim, odecitas=None, system_dostupny=False,
                nejaky_vystup=False, chyba=self._chyba,
            )
        odecitas: str | None = None
        system = False
        nejaky = False
        for vystup, aktivni in self._kandidati():
            if not aktivni:
                continue
            nejaky = True
            if odecitas is None and self._je_odecitas(vystup):
                odecitas = getattr(vystup, "name", None)
            if self._je_system(vystup):
                system = True
        return StavHlasu(
            rezim=self._rezim, odecitas=odecitas, system_dostupny=system,
            nejaky_vystup=nejaky, chyba=self._chyba,
        )

    def _cil_vystupu(self):
        """Výstup, kterým se má mluvit pro aktuální režim (nebo None)."""
        if self._rezim == REZIM_VYPNUTO:
            return None
        kandidati = [(o, a) for o, a in self._kandidati() if a]
        if self._rezim == REZIM_JEN_ODECITAC:
            # Bez potvrzené čtečky řeč NENÍ — viz dokumentace režimu.
            for vystup, _ in kandidati:
                if self._je_odecitas(vystup):
                    return vystup
            return None
        # REZIM_VCETNE_SYSTEMU: čtečka → systémový hlas → jiný výstup.
        for vystup, _ in kandidati:
            if self._je_odecitas(vystup):
                return vystup
        for vystup, _ in kandidati:
            if self._je_system(vystup):
                return vystup
        for vystup, _ in kandidati:
            return vystup
        return None

    @property
    def hlas_dostupny(self) -> bool:
        """True, pokud pro AKTUÁLNÍ režim existuje výstup, který může mluvit."""
        if self._vystup is None:
            return False
        return self._cil_vystupu() is not None

    @property
    def popis_dostupnosti(self) -> str:
        """Český popis stavu hlasu pro panel, hlášení i dialog nastavení."""
        if self._rezim == REZIM_VYPNUTO:
            return ("Hlasový výstup je vypnutý v nastavení; "
                    "hlášení zůstává na stavovém panelu.")
        if self._vystup is None:
            return f"Hlasový výstup není k dispozici ({self._chyba})."
        stav = self.stav_hlasu()

        casti: list[str] = []
        if stav.odecitas:
            casti.append(f"Potvrzena aktivní čtečka obrazovky: "
                         f"{stav.odecitas}.")
            if stav.system_dostupny:
                casti.append("Systémový hlas je také dostupný.")
        elif stav.system_dostupny:
            casti.append("Čtečka obrazovky není potvrzena; "
                         "dostupný je pouze systémový hlas.")
        elif stav.nejaky_vystup:
            casti.append("Čtečka obrazovky není potvrzena "
                         "a systémový hlas není dostupný.")
        else:
            casti.append("Není dostupný žádný hlasový výstup; "
                         "oznámení zůstávají na stavovém panelu.")

        if stav.rezim == REZIM_JEN_ODECITAC and not stav.odecitas:
            casti.append("V režimu „jen s čtečkou“ aplikace teď "
                         "hlasitě nemluví.")
        return " ".join(casti)

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

    def zkusebni_hlaseni(
        self,
        text: str = "Zkušební hlášení hlasového výstupu. Toto je test řeči.",
    ) -> bool:
        """Zkušební hláška pro nastavení — mluví i při opakování textu.

        Stavový panel se NEPŘEPISUJE (nesmí zmizet poslední herní hlášení).
        Vrací True, pokud se skutečně promluvilo.
        """
        return self._mluv(text, vzdy=True)

    def _mluv(self, text: str, vzdy: bool = False) -> bool:
        if self._rezim == REZIM_VYPNUTO:
            return False
        cil = self._cil_vystupu()
        if cil is None:
            return False
        try:
            cil.speak(text, interrupt=True)
            return True
        except Exception as e:   # noqa: BLE001
            self._chyba = f"{type(e).__name__}: {e}"
            return False
