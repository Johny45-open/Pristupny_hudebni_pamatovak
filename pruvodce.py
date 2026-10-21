"""Průvodce rytmem — přepočty dob, rytmické klepání a odpočítání.

Modul je čistý Python bez Qt a zvuku (stejně jako ``melodies``).
Vychází ze SKUTEČNÉ interpretace jednotek v ``melodies.casovy_plan``:

- ``Ton.delka`` (délka tónu) i ``Ton.pauza`` (pauza po tónu) jsou
  v DOBÁCH; 1 doba = ``60 / tempo_bpm`` sekund,
- ``zvuk_s  = delka * 60 / tempo_bpm``,
- ``pauza_s = pauza * 60 / tempo_bpm + mezertonova_pauza_s``
  (mezertonová pauza se přičítá v SEKUNDÁCH, na tempo se neváže).

Z toho plyne i zde použitý princip rytmického klepání: každý tón
melodie se nahradí krátkým impulzem, ale interval do dalšího nástupu
zůstává stejný. Je-li původní krok ``D`` (zvuk) + ``P`` (pauza) a
impuls trvá ``I``, pauza po impulsu je ``max(0, D + P - I)`` —
mezitónová pauza se tak nezapočítá dvakrát.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import melodies

# Délka rytmického klepu (sekundy). Krátká, aby vynikl nástup tónu.
DELKA_IMPSULU_S = 0.08

# Počet úderů odpočítání před začátkem přehrávání.
UDERY_ODPOCETU = 4

# Pauza mezi „před“ a „po“ při porovnávání rytmu (sekundy).
PAUZA_MEZI_POROVNANIM_S = 1.5

# Neutrálná výška pro odpočítávací klepy (impuls se stejně hraje
# jako klep, výška se nepoužívá).
_MIDI_ODPOCETU = 60


# ---------------------------------------------------------------------------
# Přepočet dob na sekundy
# ---------------------------------------------------------------------------


def doba_s(tempo_bpm: float) -> float:
    """Délka jedné doby v sekundách (60 / tempo)."""
    if tempo_bpm <= 0:
        raise ValueError(f"Tempo musí být kladné, je {tempo_bpm}")
    return 60.0 / tempo_bpm


def delka_tonu_s(delka: float, tempo_bpm: float) -> float:
    """Délka tónu v sekundách (délka v dobách × doba)."""
    if delka < 0:
        raise ValueError(f"Délka tónu nesmí být záporná: {delka}")
    return delka * doba_s(tempo_bpm)


def pauza_tonu_s(
        pauza: float,
        tempo_bpm: float,
        mezertonova_pauza_s: float = 0.0,
) -> float:
    """Pauza po tónu v sekundách (pauza v dobách + mezertonová v sekundách)."""
    if pauza < 0:
        raise ValueError(f"Pauza nesmí být záporná: {pauza}")
    if mezertonova_pauza_s < 0:
        raise ValueError(f"Mezertonová pauza nesmí být záporná: "
                         f"{mezertonova_pauza_s}")
    return pauza * doba_s(tempo_bpm) + mezertonova_pauza_s


def prepocti_doby(
        delka: float,
        pauza: float,
        tempo_bpm: float,
        mezertonova_pauza_s: float = 0.0,
) -> tuple[float, float]:
    """Přepočet zadaných dob na sekundy. Vrací (zvuk_s, pauza_s).

    Odpovídá přesně tomu, co při přehrávání použije ``casovy_plan``.
    """
    return (
        delka_tonu_s(delka, tempo_bpm),
        pauza_tonu_s(pauza, tempo_bpm, mezertonova_pauza_s),
    )


# ---------------------------------------------------------------------------
# Rytmické klepání (impulzy) a odpočítání
# ---------------------------------------------------------------------------


def kroky_rytmu(
        melodie: melodies.Melodie,
        delka_impulsu_s: float = DELKA_IMPSULU_S,
) -> list[melodies.KrokPrehravani]:
    """Rytmická verze melodie: místo tónů krátké klepy.

    Vychází z ``melodies.casovy_plan``, takže nástupy jednotlivých
    kroků vyjdou STEJNĚ jako u původní melodie:

    - ``zvuk_s`` impulsu = ``min(delka_impulsu_s, D)`` (impuls nikdy
      nepřesáhne trvání původního kroku),
    - ``pauza_s`` = ``max(0, D + P - I)`` — interval do dalšího
      nástupu zůstává ``D + P``.

    ``delka_impulsu_s`` musí být kladná (jinak ValueError).
    """
    if delka_impulsu_s <= 0:
        raise ValueError(f"Délka impulsu musí být kladná: {delka_impulsu_s}")
    kroky: list[melodies.KrokPrehravani] = []
    for krok in melodies.casovy_plan(melodie):
        impuls = min(delka_impulsu_s, krok.zvuk_s)
        kroky.append(melodies.KrokPrehravani(
            midi=krok.midi,
            zvuk_s=impuls,
            pauza_s=max(0.0, krok.zvuk_s + krok.pauza_s - impuls),
            impuls=True,
        ))
    return kroky


def kroky_s_odpocet(
        kroky: list[melodies.KrokPrehravani],
        tempo_bpm: float,
        pocet: int = UDERY_ODPOCETU,
) -> list[melodies.KrokPrehravani]:
    """Připředá krokům odpočítání — ``pocet`` zvukových úderů.

    Rozestup mezi údery (i mezi posledním úderem a prvním krokem)
    odpovídá přesně jedné době zvoleného tempa. Jedná se o zvukové
    údery (klepy), ne o hlasem vyslovené počítání.
    """
    if pocet < 0:
        raise ValueError(f"Počet úderů odpočítání nesmí být záporný: {pocet}")
    doba = doba_s(tempo_bpm)
    impuls = min(DELKA_IMPSULU_S, doba)
    odpocet = [
        melodies.KrokPrehravani(
            midi=_MIDI_ODPOCETU,
            zvuk_s=impuls,
            pauza_s=max(0.0, doba - impuls),
            impuls=True,
        )
        for _ in range(pocet)
    ]
    return odpocet + list(kroky)


def spoj_kroky(
        prvni: list[melodies.KrokPrehravani],
        druhy: list[melodies.KrokPrehravani],
        pauza_mezi_s: float = PAUZA_MEZI_POROVNANIM_S,
) -> list[melodies.KrokPrehravani]:
    """Spojí dva sekvence kroků s výraznou pauzou mezi nimi.

    Pauza se přičte k pauze posledního kroku první sekvence
    (nehrá se žádný tón navíc — jen ticho).
    """
    if pauza_mezi_s < 0:
        raise ValueError(f"Pauza mezi sekvencemi nesmí být záporná: "
                         f"{pauza_mezi_s}")
    prvni_l = list(prvni)
    druhy_l = list(druhy)
    if not prvni_l:
        return druhy_l
    if not druhy_l:
        return prvni_l
    posledni = prvni_l[-1]
    prvni_l[-1] = replace(posledni, pauza_s=posledni.pauza_s + pauza_mezi_s)
    return prvni_l + druhy_l


# ---------------------------------------------------------------------------
# Krátké rytmické příklady (s českým popisem pro průvodce)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RytmickyPriklad:
    """Jeden ukázkový rytmus s vysvětlením."""

    id: str
    nazev: str
    popis: str
    melodie: melodies.Melodie


PRIKLADY: tuple[RytmickyPriklad, ...] = (
    RytmickyPriklad(
        id="stejne_ctvrtky",
        nazev="Stejné čtvrtky",
        popis=("Čtyři tóny stejné délky — každý trvá jednu dobu. "
               "Při 100 úderech za minutu je jedna doba dlouhá "
               "0,60 sekundy, takže každý tón zní 0,60 s."),
        melodie=melodies.Melodie(
            id="_priklad_ctvrtky",
            nazev="Stejné čtvrtky",
            tony=(melodies.Ton("C4", 1.0), melodies.Ton("D4", 1.0),
                  melodies.Ton("E4", 1.0), melodies.Ton("F4", 1.0)),
            tempo_bpm=100.0,
        ),
    ),
    RytmickyPriklad(
        id="osminky_a_ctvrtky",
        nazev="Osminky a čtvrtky",
        popis=("Dvě rychlé osminky (půl doby) a dvě čtvrtky (celá doba). "
               "Při 120 úderech za minutu je doba 0,50 s — osminka tedy "
               "zní 0,25 s a čtvrta 0,50 s."),
        melodie=melodies.Melodie(
            id="_priklad_osminky",
            nazev="Osminky a čtvrtky",
            tony=(melodies.Ton("G4", 0.5), melodies.Ton("G4", 0.5),
                  melodies.Ton("C5", 1.0), melodies.Ton("C5", 1.0)),
            tempo_bpm=120.0,
        ),
    ),
    RytmickyPriklad(
        id="vitezny_ritmus",
        nazev="Vítězný rytmus 3 + 3 + 2",
        popis=("Rytmus rozdělený na tři stejné části: dvě dlouhé doby "
               "1,5 doby a jedna krátká 1 doba. Při 120 úderech za minutu "
               "to je 0,75 s, 0,75 s a 0,50 s — vzniká „skáčavý“ drajv."),
        melodie=melodies.Melodie(
            id="_priklad_332",
            nazev="Vítězný rytmus 3 + 3 + 2",
            tony=(melodies.Ton("C4", 1.5), melodies.Ton("E4", 1.5),
                  melodies.Ton("G4", 1.0)),
            tempo_bpm=120.0,
        ),
    ),
)


def priklad(id_prikladu: str) -> RytmickyPriklad | None:
    """Rytmický příklad podle ID, nebo None."""
    for p in PRIKLADY:
        if p.id == id_prikladu:
            return p
    return None
