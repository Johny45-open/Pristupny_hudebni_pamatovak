"""Programově definované melodie pro Hudební pamatovák.

Vývojář zde definuje vlastní vítězné a smutné melodie pro jednotlivé
tóniny, aniž by musel měnit herní logiku, GUI ani zvukový engine.

Zásady:
- Melodie se definují ZÁKLADNĚ v tónině C a automaticky se transponují
  do zvolené tóniny (15 kopií udržovat nemusíte).
- Pro konkrétní tóninu lze definovat NEZÁVISLOU individuální melodii,
  která má před transpozicí vždy přednost.
- Tóny mimo stupnici jsou povoleny jen explicitním příznakem
  ``povolit_mimo_stupnici=True``; jinak je melodie odmítnuta.
- Pokud je definice neplatná nebo chybí, použije se bezpečný fallback
  a volající dostane informaci o použité náhradě.

Žádné externí zvukové soubory — jen textové definice.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import theory

# Druhy melodií.
DRUH_VITEZNA = "vitezna"
DRUH_SMUTNA = "smutna"
DRUHY = (DRUH_VITEZNA, DRUH_SMUTNA)

# ---------------------------------------------------------------------------
# Datové typy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ton:
    """Jeden tón melodie.

    nazev:      český název s oktavou, např. "C4", "Fis4", "B3", "H5"
    delka:      délka tónu v taktech (> 0)
    pauza:      pauza po tónu v taktu (>= 0)
    """

    nazev: str
    delka: float = 1.0
    pauza: float = 0.0


@dataclass(frozen=True)
class Melodie:
    """Kompletní definice melodie."""

    id: str
    nazev: str                      # český popisek pro UI
    tony: tuple[Ton, ...]
    tempo_bpm: float = 100.0
    mezertonova_pauza_s: float = 0.12
    povolit_mimo_stupnici: bool = False


@dataclass
class VolbaMelodie:
    """Výsledek výběru melodie pro tóninu."""

    melodie: Melodie
    tonina: str
    druh: str
    zdroj: str                      # "individualni" | "transpozice" | "zalozni"
    varovani: str | None = None     # informace o použité náhradě


# ---------------------------------------------------------------------------
# Základní přednastavené melodie — definované jednou, v tónině C
# ---------------------------------------------------------------------------

ZAKLADNI_SMUTNE: dict[str, Melodie] = {
    "kratka_sestupna": Melodie(
        id="kratka_sestupna",
        nazev="Krátké sestupné tóny",
        tony=(Ton("A4"), Ton("G4"), Ton("F4"), Ton("E4")),
        tempo_bpm=90.0,
    ),
    "pomala_sestupna": Melodie(
        id="pomala_sestupna",
        nazev="Pomalá sestupná melodie",
        tony=(Ton("A4", 1.0), Ton("G4", 1.0), Ton("F4", 1.0),
              Ton("D4", 1.0), Ton("C4", 2.0)),
        tempo_bpm=65.0,
    ),
    "dlouhy_smutny": Melodie(
        id="dlouhy_smutny",
        nazev="Delší smutný motiv",
        tony=(Ton("C5"), Ton("H4"), Ton("A4"), Ton("G4"),
              Ton("F4"), Ton("E4"), Ton("D4"), Ton("C4", 2.0)),
        tempo_bpm=72.0,
    ),
}

ZAKLADNI_VITEZNE: dict[str, Melodie] = {
    "kratka_fanfara": Melodie(
        id="kratka_fanfara",
        nazev="Krátká vítězná fanfára",
        tony=(Ton("C4", 0.5), Ton("E4", 0.5), Ton("G4", 0.5), Ton("C5", 1.0)),
        tempo_bpm=120.0,
    ),
    "vzestupna": Melodie(
        id="vzestupna",
        nazev="Vzestupná melodie",
        tony=(Ton("C4"), Ton("D4"), Ton("E4"), Ton("F4"),
              Ton("G4"), Ton("A4"), Ton("H4"), Ton("C5", 1.5)),
        tempo_bpm=100.0,
    ),
    "slavnostni": Melodie(
        id="slavnostni",
        nazev="Výraznější slavnostní motiv",
        tony=(Ton("C4", 1.0), Ton("G4", 0.5), Ton("C5", 0.5),
              Ton("E5", 1.0), Ton("G5", 2.0)),
        tempo_bpm=96.0,
        mezertonova_pauza_s=0.08,
    ),
}

VYCHOZI_ID = {
    DRUH_SMUTNA: "kratka_sestupna",
    DRUH_VITEZNA: "kratka_fanfara",
}

# Poslední záloha, když je základní sada poškozená (nemělo by nastat).
PREPOJNA: dict[str, Melodie] = {
    DRUH_SMUTNA: Melodie(
        id="_zalozni_smutna", nazev="Záložní smutná melodie",
        tony=(Ton("G4"), Ton("E4"), Ton("C4", 2.0)),
    ),
    DRUH_VITEZNA: Melodie(
        id="_zalozni_vitezna", nazev="Záložní vítězná melodie",
        tony=(Ton("C4"), Ton("E4"), Ton("G4", 2.0)),
    ),
}

# ---------------------------------------------------------------------------
# Individuální definice pro konkrétní tóniny — MAJÍ PŘEDNOST před transpozicí.
# Klíč: (tonina, druh, id_melodie). Uveďte jen to, co se má lišit.
#
# Příklad (stačí odkomentovat a upravit):
#   ("Fis", DRUH_VITEZNA, "kratka_fanfara"): Melodie(
#       id="kratka_fanfara",
#       nazev="Fanfára pro Fis dur",
#       tony=(Ton("Fis4", 0.5), Ton("Cis5", 0.5), Ton("Fis5", 1.0)),
#       tempo_bpm=126.0,
#   ),
# ---------------------------------------------------------------------------

INDIVIDUALNI_MELODIE: dict[tuple[str, str, str], Melodie] = {}


# ---------------------------------------------------------------------------
# Validace
# ---------------------------------------------------------------------------


def validuj_melodii(melodie: Melodie, tonina: str) -> tuple[list[str], list[str]]:
    """Validuje melodii pro danou tóninu.

    Vrací (chyby, varovani).
    - chyby: melodie je nepoužitelná (špatné parametry, tóny mimo
      stupnici bez explicitního povolení, nečitelný název).
    - varovani: melodie je použitelná, ale např. obsahuje tóny mimo
      stupnici při povoleném příznaku.
    """
    chyby: list[str] = []
    varovani: list[str] = []

    if melodie.tempo_bpm <= 0:
        chyby.append(f"tempo musí být kladné, je {melodie.tempo_bpm}")
    if melodie.mezertonova_pauza_s < 0:
        chyby.append(f"mezertonová pauza nesmí být záporná: {melodie.mezertonova_pauza_s}")
    if not melodie.tony:
        chyby.append("melodie neobsahuje žádné tóny")

    for i, ton in enumerate(melodie.tony, start=1):
        try:
            midi = theory.midi_z_nazvu(ton.nazev)
        except ValueError as e:
            chyby.append(f"tón {i}: {e}")
            continue
        if ton.delka <= 0:
            chyby.append(f"tón {i} ({ton.nazev}): délka musí být kladná, je {ton.delka}")
        if ton.pauza < 0:
            chyby.append(f"tón {i} ({ton.nazev}): pauza nesmí být záporná, je {ton.pauza}")
        if not theory.ton_patri_do_toniny(midi, tonina):
            popis = (f"tón {i} ({ton.nazev}) nepatří do tóniny "
                     f"{theory.POPISKY_TONIN[tonina]}")
            if melodie.povolit_mimo_stupnici:
                varovani.append(popis + " — povoleno explicitním příznakem")
            else:
                chyby.append(popis + " — není povoleno")

    return chyby, varovani


# ---------------------------------------------------------------------------
# Transpozice
# ---------------------------------------------------------------------------


def transponuj_melodii(melodie: Melodie, tonina: str) -> Melodie:
    """Transponuje melodii definovanou v C do cílové tóniny.

    Transpozice probíhá o rozdíl základních tónů (s poklesem o oktávu,
    pokud by se melodie zbytečně zvedla), názvy tónů se přepočítají
    podle cílové tóniny, takže zůstane správný enharmonický zápis.
    """
    theory.over_toninu(tonina)
    delta = theory.pultony_zakladniho_tonu(tonina)
    if delta > 6:
        delta -= 12
    nove_tony = []
    for ton in melodie.tony:
        midi = theory.midi_z_nazvu(ton.nazev) + delta
        nove_tony.append(replace(ton, nazev=theory.nazev_tonu_z_midi(midi, tonina)))
    return replace(melodie, tony=tuple(nove_tony))


# ---------------------------------------------------------------------------
# Výběr melodie
# ---------------------------------------------------------------------------


def nabidka_melodii(druh: str) -> list[tuple[str, str]]:
    """Seznam (id, český název) pro výběrové pole v nastavení."""
    if druh not in DRUHY:
        raise ValueError(f"Neznámý druh melodie: {druh!r}")
    zaklad = ZAKLADNI_SMUTNE if druh == DRUH_SMUTNA else ZAKLADNI_VITEZNE
    return [(mid, m.nazev) for mid, m in zaklad.items()]


def ziskej_melodii(tonina: str, druh: str, id_melodie: str | None = None) -> VolbaMelodie:
    """Vyhledá melodii pro tóninu.

    Postup:
    1. individuální definice pro (tonina, druh, id) — má přednost,
    2. transpozice základní melodie z C do tóniny,
    3. transpozice výchozí melodie daného druhu (id chybí/neplatí),
    4. pevná záložní melodie + varování.
    """
    theory.over_toninu(tonina)
    if druh not in DRUHY:
        raise ValueError(f"Neznámý druh melodie: {druh!r}")
    id_pozadovane = id_melodie or VYCHOZI_ID[druh]

    # 1) Individuální definice
    jednotlivec = INDIVIDUALNI_MELODIE.get((tonina, druh, id_pozadovane))
    if jednotlivec is not None:
        chyby, varovani = validuj_melodii(jednotlivec, tonina)
        if not chyby:
            return VolbaMelodie(
                melodie=jednotlivec, tonina=tonina, druh=druh,
                zdroj="individualni",
                varovani="; ".join(varovani) or None,
            )
        # Neplatnou individuální melodii nepoužijeme, zkusíme transpozici.
        varovani_ind = ("Individuální melodii se nepodařilo použít: "
                        + "; ".join(chyby))

    # 2) Transpozice základní melodie
    zaklad = ZAKLADNI_VITEZNE if druh == DRUH_VITEZNA else ZAKLADNI_SMUTNE
    zaklad_melodie = zaklad.get(id_pozadovane)
    if zaklad_melodie is not None:
        kandidat = transponuj_melodii(zaklad_melodie, tonina)
        chyby, varovani = validuj_melodii(kandidat, tonina)
        if not chyby:
            msg = "; ".join(varovani)
            if jednotlivec is not None:
                msg = (varovani_ind + ("; " + msg if msg else ""))
            return VolbaMelodie(
                melodie=kandidat, tonina=tonina, druh=druh,
                zdroj="transpozice", varovani=msg or None,
            )

    # 3) Výchozí melodie daného druhu
    vychozi = zaklad.get(VYCHOZI_ID[druh])
    if vychozi is not None and id_pozadovane != VYCHOZI_ID[druh]:
        kandidat = transponuj_melodii(vychozi, tonina)
        chyby, varovani = validuj_melodii(kandidat, tonina)
        if not chyby:
            msg = f"Použita výchozí melodie „{vychozi.nazev}“."
            doplneni = "; ".join(varovani)
            if doplneni:
                msg += " " + doplneni
            if jednotlivec is not None:
                msg = varovani_ind + "; " + msg
            return VolbaMelodie(
                melodie=kandidat, tonina=tonina, druh=druh,
                zdroj="zalozni", varovani=msg,
            )

    # 4) Pevná záložní melodie (poslední jistota)
    zalozni = PREPOJNA[druh]
    kandidat = transponuj_melodii(zalozni, tonina)
    chyby, varovani = validuj_melodii(kandidat, tonina)
    if chyby:
        # Transpozice záložní selhala — vezmeme ji v základní podobě.
        kandidat, chyby2 = zalozni, validuj_melodii(zalozni, "C")[0]
        if chyby2:
            raise RuntimeError(
                f"Záložní melodie je neplatná: {'; '.join(chyby2)}")
    return VolbaMelodie(
        melodie=kandidat, tonina=tonina, druh=druh,
        zdroj="zalozni",
        varovani=f"Použita záložní melodie „{zalozni.nazev}“.",
    )


# ---------------------------------------------------------------------------
# Převod melodie na časový plán pro zvukový engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KrokPrehravani:
    """Jeden krok přehrávání: MIDI výška + doby v sekundách."""

    midi: int
    zvuk_s: float
    pauza_s: float


def casovy_plan(melodie: Melodie) -> list[KrokPrehravani]:
    """Přepočte melodii na seznam kroků pro zvukový engine."""
    za_takt = 60.0 / melodie.tempo_bpm
    kroky: list[KrokPrehravani] = []
    for ton in melodie.tony:
        midi = theory.midi_z_nazvu(ton.nazev)
        kroky.append(KrokPrehravani(
            midi=midi,
            zvuk_s=ton.delka * za_takt,
            pauza_s=ton.pauza * za_takt + melodie.mezertonova_pauza_s,
        ))
    return kroky


def doba_celkem(melodie: Melodie) -> float:
    """Celková délka melodie v sekundách (pro testy a odhad čekání)."""
    return sum(k.zvuk_s + k.pauza_s for k in casovy_plan(melodie))
