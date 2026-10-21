"""Hudební teorie pro Hudební pamatovák.

Modul obsahuje:
- všech 15 podporovaných durových tónin v českém názvosloví,
- explicitní názvy stupňů stupnice (žádný odvoz z MIDI modul 12 —
  enharmonicky shodné tóny mohou mít odlišná jména, např. Eis vs. F),
- převody mezi českými názvy tónů a MIDI výškami,
- transpozici a validaci příslušnosti tónu k tónině.

České názvosloví: H = B přirozené, B = B snížené (bé).
Modul je čistý Python bez závislostí na Qt a zvuku.
"""

from __future__ import annotations

import re

# Intervaly durové stupnice v půltónech od základního tónu.
INTERVALY_DUR = (0, 2, 4, 5, 7, 9, 11)

# Kanonické (výchozí) názvy pro 12 půltónů, česky, ostré varianty.
# Používá se jen jako záloha, když tón nepatří do žádné tóniny.
KANONICKE_NAZVY = {
    0: "C", 1: "Cis", 2: "D", 3: "Dis", 4: "E", 5: "F",
    6: "Fis", 7: "G", 8: "Gis", 9: "A", 10: "Ais", 11: "H",
}

# Základní (přirozený) půltón pro dané písmeno v českém zápisu.
# "B" = B snížené (bé), "H" = B přirozené.
_ZAKLADNI_TON = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "H": 11, "B": 10,
}

_NAZEV_RE = re.compile(r"^([CDEFGAHB])(is|es|s)?(\d{1,2})$")


def _rozloz_nazev(nazev: str) -> tuple[int, int, str]:
    """Rozloží název bez oktávy na (přirozený půltón, předznamenání, tvar).

    Předznamenání: +1 ostrý ("is"), -1 snížený ("es"/"s"), 0 přirozený.
    Vrací půltón NEnormalizovaný (může být -1 nebo 12), aby seděla oktáva.
    """
    if not nazev:
        raise ValueError("Prázdný název tónu")
    pismeno = nazev[0]
    if pismeno not in _ZAKLADNI_TON:
        raise ValueError(f"Neplatné písmeno tónu v {nazev!r}")
    zbytek = nazev[1:]
    zaklad = _ZAKLADNI_TON[pismeno]
    if zbytek == "is":
        return zaklad, +1, "is"
    if zbytek in ("es", "s"):
        return zaklad, -1, zbytek
    if zbytek == "":
        return zaklad, 0, ""
    raise ValueError(f"Neplatná předznamenání v {nazev!r}")


def midi_z_nazvu(nazev: str) -> int:
    """Převede český název tónu s oktavou (např. "Fis4", "B3", "Ces4") na MIDI.

    Vyhodí ValueError pro neplatný tvar.
    """
    m = _NAZEV_RE.match(nazev.strip())
    if not m:
        raise ValueError(f"Neplatný název tónu: {nazev!r}")
    jmeno, oktava = m.group(1) + (m.group(2) or ""), int(m.group(3))
    zaklad, alter, _ = _rozloz_nazev(jmeno)
    return 12 * (oktava + 1) + zaklad + alter


def _oktava_pro_nazev(jmeno_bez_oktavy: str, midi: int) -> int:
    """Vypočítá oktávu, která má být připsána k názvu pro dané MIDI.

    Vychází z přirozené (nepředznamenané) výšky písmene:
    např. Ces5 = B4 = 71 → přirozené C je 72 → oktáva 5.
    """
    _, alter, _ = _rozloz_nazev(jmeno_bez_oktavy)
    prirozene = midi - alter
    return prirozene // 12 - 1


def nazev_tonu_z_midi(midi: int, tonina: str | None = None) -> str:
    """Vrátí český název tónu pro MIDI výšku včetně oktávy.

    Pokud je zadána tónina a tón do ní patří, použije se název
    ze stupnice této tóniny (správný enharmonický zápis).
    Jinak kanonické ostře-zapsané jméno.
    """
    pc = midi % 12
    if tonina is not None:
        for nazev, midi_stupne in stupnice(tonina, oktava=4):
            if midi_stupne % 12 == pc:
                return f"{nazev}{_oktava_pro_nazev(nazev, midi)}"
    return f"{KANONICKE_NAZVY[pc]}{midi // 12 - 1}"


# ---------------------------------------------------------------------------
# Patnáct tónin: název -> (základní tón, názvy stupňů 1-7)
# Názvy stupňů jsou explicitní, aby byl zápis enharmonicky správný.
# ---------------------------------------------------------------------------

TONINY: dict[str, tuple[str, tuple[str, ...]]] = {
    "C":   ("C",   ("C", "D", "E", "F", "G", "A", "H")),
    "G":   ("G",   ("G", "A", "H", "C", "D", "E", "Fis")),
    "D":   ("D",   ("D", "E", "Fis", "G", "A", "H", "Cis")),
    "A":   ("A",   ("A", "H", "Cis", "D", "E", "Fis", "Gis")),
    "E":   ("E",   ("E", "Fis", "Gis", "A", "H", "Cis", "Dis")),
    "H":   ("H",   ("H", "Cis", "Dis", "E", "Fis", "Gis", "Ais")),
    "Fis": ("Fis", ("Fis", "Gis", "Ais", "H", "Cis", "Dis", "Eis")),
    "Cis": ("Cis", ("Cis", "Dis", "Eis", "Fis", "Gis", "Ais", "His")),
    "F":   ("F",   ("F", "G", "A", "B", "C", "D", "E")),
    "B":   ("B",   ("B", "C", "D", "Es", "F", "G", "A")),
    "Es":  ("Es",  ("Es", "F", "G", "As", "B", "C", "D")),
    "As":  ("As",  ("As", "B", "C", "Des", "Es", "F", "G")),
    "Des": ("Des", ("Des", "Es", "F", "Ges", "As", "B", "C")),
    "Ges": ("Ges", ("Ges", "As", "B", "Ces", "Des", "Es", "F")),
    "Ces": ("Ces", ("Ces", "Des", "Es", "Fes", "Ges", "As", "B")),
}

PORADI_TONIN: tuple[str, ...] = tuple(TONINY.keys())

# Popisky pro UI (česky, bez mezinárodních dvojznaček).
POPISKY_TONIN: dict[str, str] = {k: f"{k} dur" for k in TONINY}


def over_toninu(tonina: str) -> None:
    if tonina not in TONINY:
        raise ValueError(f"Neznámá tónina: {tonina!r}")


def pultony_zakladniho_tonu(tonina: str) -> int:
    """Půltónový index (0-11) základního tónu tóniny, normalizovaný."""
    return raw_pultony_zakladniho_tonu(tonina) % 12


def raw_pultony_zakladniho_tonu(tonina: str) -> int:
    """Půltónový index základního tónu bez normalizace (-1 až 12).

    Nesnormalizovaná hodnota zaručuje správnou oktávu
    u tónin s enharmonicky „přesahujícím“ základem (Ces, H#).
    """
    over_toninu(tonina)
    zaklad, _, _ = _rozloz_nazev(TONINY[tonina][0])
    _, alter, _ = _rozloz_nazev(TONINY[tonina][0])
    return zaklad + alter


def midi_zakladniho_tonu(tonina: str, oktava: int) -> int:
    """MIDI výška základního tónu tóniny v dané oktávě."""
    return 12 * (oktava + 1) + raw_pultony_zakladniho_tonu(tonina)


def stupnice(tonina: str, oktava: int = 4) -> list[tuple[str, int]]:
    """Sedm stupňů durové stupnice tóniny: [(název, MIDI), ...].

    Názvy odpovídají správnému notovému zápisu tóniny,
    MIDI výšky jdou od základního tónu směrem vzhůru.
    """
    over_toninu(tonina)
    _, nazvy = TONINY[tonina]
    zaklad = midi_zakladniho_tonu(tonina, oktava)
    return [
        (nazvy[i], zaklad + INTERVALY_DUR[i])
        for i in range(7)
    ]


def ton_patri_do_toniny(midi: int, tonina: str) -> bool:
    """True, pokud má tón stejný půltón jako některý stupeň tóniny."""
    pc = midi % 12
    return any(m % 12 == pc for _, m in stupnice(tonina, oktava=4))


def transponuj_midi(midi: int, semitony: int) -> int:
    return midi + semitony


def transponuj_nazev(nazev: str, semitony: int, tonina: str | None = None) -> str:
    """Transponuje český název tónu (s oktavou) o daný počet půltónů.

    Pokud je známá cílová tónina a týče-se výsledek její stupnice,
    použije se její správný enharmonický název.
    """
    midi = midi_z_nazvu(nazev) + semitony
    return nazev_tonu_z_midi(midi, tonina)


def nazev_stupne(tonina: str, stupen: int, oktava: int = 4) -> str:
    """Název tónu stupně stupnice (0-6) včetně oktávy."""
    if not 0 <= stupen <= 6:
        raise ValueError(f"Stupeň musí být 0-6, dostal jsem {stupen}")
    nazev, midi = stupnice(tonina, oktava)[stupen]
    return f"{nazev}{_oktava_pro_nazev(nazev, midi)}"


def nazev_pro_tlacitko(tonina: str, stupen: int, oktava: int) -> tuple[str, int]:
    """Vrátí (přístupný název tlačítka, MIDI) pro stupeň tóniny.

    Např. ("Tón Cis, oktáva 5", 73) pro Fis dur, stupeň 5, oktáva 4.
    """
    nazev, midi = stupnice(tonina, oktava)[stupen]
    okt = _oktava_pro_nazev(nazev, midi)
    return f"Tón {nazev}, oktáva {okt}", midi
