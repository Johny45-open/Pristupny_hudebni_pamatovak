"""Programové generování a přehrávání tónů (pygame + numpy).

- Žádné externí zvukové soubory — tóny se generují matematicky.
- Krátké rytmické klepy (``generuj_impuls``) pro průvodce rytmem
  mají vlastní funkci i cache — přehrávání běžných melodií se jím
  nemění.
- Pokud zařízení pro přehrávání není dostupné, modul přechází do
  TICHÉHO REŽIMU a aplikace se nezhroutí (funguje logika i GUI).
- Přehrávání je určeno pro práci ve vlákně (worker), nikoli v GUI.
"""

from __future__ import annotations

import math

import numpy as np

VZORKOVACI_FREKVENCE = 44100
BIT_DEPTH = -16
KANALY = 2

# Ladění: MIDI 69 (A4) = 440 Hz.
def frekvence_pro_midi(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def generuj_vlnu(
    midi: int,
    zvuk_s: float,
    hlasitost: float = 0.45,
    vzorkovaci: int = VZORKOVACI_FREKVENCE,
) -> np.ndarray:
    """Vygeneruje stereo int16 signál jednoho tónu.

    Tón obsahuje základní frekvenci a několik slabších harmonických
    (charakter „piano-like“ tónu) s jednoduchou obálkou náběhu a dozvuku.
    """
    if zvuk_s <= 0:
        raise ValueError(f"Délka tónu musí být kladná: {zvuk_s}")
    n = _pocet_vzorku(zvuk_s, vzorkovaci)
    t = np.arange(n, dtype=np.float64) / vzorkovaci
    f = frekvence_pro_midi(midi)

    signal = np.zeros(n, dtype=np.float64)
    for harm, amplituda in ((1, 1.0), (2, 0.35), (3, 0.18), (4, 0.08)):
        signal += amplituda * np.sin(2.0 * math.pi * f * harm * t)
    signal /= 1.61   # součet amplitud → normalizace

    # Obálka: rychlý náběh (10 ms), pomalejší dozvuk (posledních 15 %).
    obalka = np.ones(n, dtype=np.float64)
    nabeh = min(int(0.010 * vzorkovaci), n)
    if nabeh > 1:
        obalka[:nabeh] = np.linspace(0.0, 1.0, nabeh)
    dozvuk = min(int(0.15 * n), n)
    if dozvuk > 1:
        obalka[n - dozvuk:] *= np.linspace(1.0, 0.0, dozvuk)

    signal *= obalka * hlasitost
    signal = np.clip(signal, -1.0, 1.0)
    stereo = np.empty((n, 2), dtype=np.int16)
    pcm = (signal * 32767.0).astype(np.int16)
    stereo[:, 0] = pcm
    stereo[:, 1] = pcm
    return stereo


def _pocet_vzorku(zvuk_s: float, vzorkovaci: int) -> int:
    return max(1, int(round(zvuk_s * vzorkovaci)))


def generuj_impuls(
        zvuk_s: float = 0.08,
        hlasitost: float = 0.5,
        vzorkovaci: int = VZORKOVACI_FREKVENCE,
) -> np.ndarray:
    """Vygeneruje krátký neutrální rytmický klep (bez výšky tónu).

    Používá se JEN pro přehrávání rytmu v průvodci rytmem. Běžné
    tóny generuje ``generuj_vlnu`` — ta se touto funkcí nijak nemění.
    Signál = deterministický šum s rychlým útlumem + krátká vysoká
    složka pro slyšitelný nápad (charakter „klik“).
    """
    if zvuk_s <= 0:
        raise ValueError(f"Délka impulsu musí být kladná: {zvuk_s}")
    n = _pocet_vzorku(zvuk_s, vzorkovaci)
    t = np.arange(n, dtype=np.float64) / vzorkovaci

    # Deterministický šum (stejný impuls se vždy vygeneruje stejně).
    rng = np.random.default_rng(20241018)
    sumeni = rng.uniform(-1.0, 1.0, n)

    # Společná obálka: rychlý náběh (2 ms) a exponenciální útlum.
    obalka = np.exp(-7.0 * np.linspace(0.0, 1.0, n))
    nabeh = min(int(0.002 * vzorkovaci), n)
    if nabeh > 1:
        obalka[:nabeh] *= np.linspace(0.0, 1.0, nabeh)

    signal = 0.65 * sumeni * obalka
    signal += 0.45 * np.sin(2.0 * math.pi * 1900.0 * t) * obalka
    signal *= hlasitost
    signal = np.clip(signal, -1.0, 1.0)

    stereo = np.empty((n, 2), dtype=np.int16)
    pcm = (signal * 32767.0).astype(np.int16)
    stereo[:, 0] = pcm
    stereo[:, 1] = pcm
    return stereo


class ZvukovyMotor:
    """Spravuje mixer a přehrávání. Bez zvukového zařízení běží tichý režim."""

    def __init__(self) -> None:
        self.dostupny = False
        self.chyba: str | None = None
        self._pygame = None
        self._kanal = None
        self._cache: dict[tuple[int, float], object] = {}
        self._cache_impulsu: dict[float, object] = {}

        try:
            import pygame
            self._pygame = pygame
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(VZORKOVACI_FREKVENCE, BIT_DEPTH, KANALY, 512)
                pygame.mixer.init()
            self.dostupny = pygame.mixer.get_init() is not None
        except Exception as e:    # noqa: BLE001 — musí přežít jakoukoli chybu
            self.dostupny = False
            self.chyba = f"{type(e).__name__}: {e}"

    @property
    def tichy_rezim(self) -> bool:
        return not self.dostupny

    def popis_rezimu(self) -> str:
        if self.dostupny:
            return "Zvuk je zapnutý."
        duvod = self.chyba or "zvukové zařízení není dostupné"
        return f"Tichý režim — zvuk není dostupný ({duvod})."

    def vytvor_zvuk(self, midi: int, zvuk_s: float):
        """Vrátí přehrátelný objekt zvuku, nebo None v tichém režimu."""
        if not self.dostupny:
            return None
        klic = (midi, round(zvuk_s, 3))
        zvuk = self._cache.get(klic)
        if zvuk is None:
            zvuk = self._pygame.sndarray.make_sound(generuj_vlnu(midi, zvuk_s))
            self._cache[klic] = zvuk
        return zvuk

    def vytvor_impuls(self, zvuk_s: float):
        """Vrátí krátký rytmický klep (cache samostatná od tónů).

        Slouží jen pro průvodce rytmem; přehrávání běžných melodií
        (``vytvor_zvuk``) touto metodou prochází nezměněné.
        V tichém režimu vrací None.
        """
        if not self.dostupny:
            return None
        klic = round(zvuk_s, 3)
        zvuk = self._cache_impulsu.get(klic)
        if zvuk is None:
            zvuk = self._pygame.sndarray.make_sound(generuj_impuls(zvuk_s))
            self._cache_impulsu[klic] = zvuk
        return zvuk

    def prehraj(self, zvuk):
        """Spustí zvuk na konkrétním kanálu a vrátí ho (None v tichém režimu)."""
        if zvuk is None:
            return None
        try:
            kanal = zvuk.play()
            self._kanal = kanal
            return kanal
        except Exception:   # noqa: BLE001
            return None

    @property
    def kanal(self):
        return self._kanal

    def zastav_kanal(self):
        """Okamžitě zastaví právě přehrávaný kanál (ne globální mixér)."""
        kanal = self._kanal
        if kanal is not None:
            try:
                kanal.stop()
            except Exception:   # noqa: BLE001
                pass

    def zastav_vse(self):
        """Poslední záloha — globální zastavení (jen při ukončování)."""
        self.zastav_kanal()
        if self.dostupny:
            try:
                self._pygame.mixer.stop()
            except Exception:   # noqa: BLE001
                pass

    def uvolni(self):
        """Uvolní zdroje mixéru při ukončení aplikace."""
        try:
            self._cache.clear()
            self._cache_impulsu.clear()
            if self.dostupny:
                self._pygame.mixer.quit()
        except Exception:   # noqa: BLE001
            pass
