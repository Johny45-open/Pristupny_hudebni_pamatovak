"""Melodie pro Hudební pamatovák — přednastavené i uživatelské.

Dva zdroje melodií:
1. Přednastavené (tyto soubory) — vyvíjí je autor v tónině C,
   automaticky se transponují do zvolené tóniny.
2. VLASTNÍ (uživatelské) melodie — vytváří je uživatel přímo
   v aplikaci (dialog Správce melodií), ukládají se trvale přes
   ``uloziste`` do JSON souboru. Spravují se funkcemi níže,
   do zdrojového kódu zasahovat nemusí.

Zásady:
- Melodie se definují ZÁKLADNĚ v tónině C a automaticky se transponují
  do zvolené tóniny (15 kopií udržovat nemusíte).
- Pro konkrétní tóninu lze definovat NEZÁVISLOU individuální melodii,
  která má před transpozicí vždy přednost.
- Tóny mimo stupnici jsou povoleny jen explicitním příznakem
  ``povolit_mimo_stupnici=True``; jinak je melodie odmítnuta.
- Pokud je definice neplatná nebo chybí, použije se bezpečný fallback
  a volající dostane informaci o použité náhradě.

Žádné externí zvukové soubory — jen textové definice. Modul zůstává
čistý Python bez Qt (serializace používá jen standardní ``json``).
"""

from __future__ import annotations

import json
import uuid
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
    """Kompletní definice melodie.

    ``druh`` je vyplněný u vlastních (uživatelských) melodií;
    u přednastavených zůstává prázdný (druh určuje složník, ve kterém
    melodie leží).
    """

    id: str
    nazev: str                      # český popisek pro UI
    tony: tuple[Ton, ...]
    tempo_bpm: float = 100.0
    mezertonova_pauza_s: float = 0.12
    povolit_mimo_stupnici: bool = False
    druh: str = ""


@dataclass
class VolbaMelodie:
    """Výsledek výběru melodie pro tóninu."""

    melodie: Melodie
    tonina: str
    druh: str
    zdroj: str      # "vlastni" | "individualni" | "transpozice" | "zalozni"
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
# Vlastní (uživatelské) melodie — spravuje je aplikace, ne vývojář
# ---------------------------------------------------------------------------
#
# Registr drží melodie definované v tónině C (stejně jako základní
# sada). Trvale je ukládá a načítá modul ``uloziste`` (JSON soubor).
# Přednastavené melodie jsou v samostatných slovnících — poškození
# vlastních dat je nikdy neohrozí.

# Prefix ID, aby se vlastní melodie nepletly s přednastavenými.
PREFIX_ID_VLASTNI = "vlastni_"

VLASTNI_MELODIE: dict[str, Melodie] = {}


def nova_id_melodie() -> str:
    """Vygeneruje volné ID pro novou vlastní melodii."""
    while True:
        kandidat = f"{PREFIX_ID_VLASTNI}{uuid.uuid4().hex[:10]}"
        if kandidat not in VLASTNI_MELODIE:
            return kandidat


def over_pred_ulozenim(melodie: Melodie) -> tuple[list[str], list[str]]:
    """Zkontroluje vlastní melodii PŘED uložením. Vrací (chyby, varovani)."""
    chyby: list[str] = []
    varovani: list[str] = []

    if not isinstance(melodie.id, str) or not melodie.id.strip():
        chyby.append("melodie musí mít ID")
    if not isinstance(melodie.nazev, str) or not melodie.nazev.strip():
        chyby.append("melodie musí mít název")
    if melodie.druh not in DRUHY:
        chyby.append(
            f"druh musí být jeden z {', '.join(DRUHY)}, je {melodie.druh!r}")

    # Vlastní melodie se definují v C — validace jako u přednastavených.
    chyby_m, varovani_m = validuj_melodii(melodie, "C")
    chyby.extend(chyby_m)
    varovani.extend(varovani_m)
    return chyby, varovani


def uloz_vlastni_melodie(melodie: Melodie) -> Melodie:
    """Uloží (vloží nebo přepíše) vlastní melodii podle jejího ID.

    Neplatnou melodii odmítne (ValueError) — poslední platná definice
    s tímto ID tím pádem zůstane nedotčená.
    """
    chyby, _ = over_pred_ulozenim(melodie)
    if chyby:
        raise ValueError("; ".join(chyby))
    VLASTNI_MELODIE[melodie.id] = melodie
    return melodie


def smaz_vlastni_melodie(id_melodie: str) -> bool:
    """Smaže vlastní melodii. Vrací True, pokud existovala."""
    return VLASTNI_MELODIE.pop(id_melodie, None) is not None


def vlastni_melodie(druh: str | None = None) -> list[Melodie]:
    """Seznam vlastních melodií (volitelně jen daného druhu), podle názvu."""
    if druh is not None and druh not in DRUHY:
        raise ValueError(f"Neznámý druh melodie: {druh!r}")
    seznam = [m for m in VLASTNI_MELODIE.values()
              if druh is None or m.druh == druh]
    return sorted(seznam, key=lambda m: m.nazev.casefold())


# --- Serializace (JSON; bez Qt, odolná proti poškozeným datům) --------------


def melodie_do_dict(melodie: Melodie) -> dict:
    """Převede melodii na JSON-ovatelný slovník."""
    return {
        "id": melodie.id,
        "druh": melodie.druh,
        "nazev": melodie.nazev,
        "tempo_bpm": melodie.tempo_bpm,
        "mezertonova_pauza_s": melodie.mezertonova_pauza_s,
        "povolit_mimo_stupnici": bool(melodie.povolit_mimo_stupnici),
        "tony": [
            {"nazev": t.nazev, "delka": t.delka, "pauza": t.pauza}
            for t in melodie.tony
        ],
    }


def _cislo(data: dict, klic: str, vychozi: float | None = None) -> float:
    """Číslo ze slovníku; chybějící použije výchozí, neplatné hodí ValueError."""
    hodnota = data.get(klic, vychozi)
    if isinstance(hodnota, bool) or not isinstance(hodnota, (int, float)):
        raise ValueError(f"položka {klic!r} není číslo: {hodnota!r}")
    return float(hodnota)


def melodie_z_dict(data: object) -> Melodie:
    """Obnoví melodii ze slovníku. Při problému hodí ValueError (česky)."""
    if not isinstance(data, dict):
        raise ValueError(f"záznam melodie není slovník: {type(data).__name__}")

    for klic in ("id", "nazev", "tony"):
        if klic not in data:
            raise ValueError(f"chybí povinná položka {klic!r}")

    tony_data = data["tony"]
    if not isinstance(tony_data, list):
        raise ValueError("položka 'tony' není seznam")
    tony: list[Ton] = []
    for i, zaznam in enumerate(tony_data, start=1):
        if not isinstance(zaznam, dict):
            raise ValueError(f"tón {i} není slovník")
        nazev = zaznam.get("nazev")
        if not isinstance(nazev, str) or not nazev.strip():
            raise ValueError(f"tón {i} nemá platný název")
        tony.append(Ton(
            nazev=nazev.strip(),
            delka=_cislo(zaznam, "delka", 1.0),
            pauza=_cislo(zaznam, "pauza", 0.0),
        ))

    melodie = Melodie(
        id=str(data["id"]),
        nazev=str(data["nazev"]),
        tony=tuple(tony),
        tempo_bpm=_cislo(data, "tempo_bpm", 100.0),
        mezertonova_pauza_s=_cislo(data, "mezertonova_pauza_s", 0.12),
        povolit_mimo_stupnici=bool(data.get("povolit_mimo_stupnici", False)),
        druh=str(data.get("druh", "")),
    )
    chyby, _ = over_pred_ulozenim(melodie)
    if chyby:
        raise ValueError("; ".join(chyby))
    return melodie


def vlastni_do_jsonu() -> str:
    """Celý registr vlastních melodií jako JSON text (UTF-8, čitelný)."""
    seznam = [melodie_do_dict(m) for m in vlastni_melodie()]
    return json.dumps(seznam, ensure_ascii=False, indent=2)


def vlastni_z_jsonu(
        text: str,
) -> tuple[dict[str, Melodie] | None, list[str], list[str]]:
    """Převede JSON text na slovník vlastních melodií.

    Vrací ``(slovnik, chyby, neplatne_id)``:

    - ``slovnik is None`` → text není čitelný JSON; volající NESMÍ
      přepisovat stávající registr (ochrana poslední platné verze),
    - ``chyby`` obsahují srozumitelná hlášení k jednotlivým záznamům
      (neplatné záznamy se vynechají, platné se použijí),
    - ``neplatne_id`` = ID, u kterých záznam selhal (pokud šlo ID ze
      záznamu vyčíst) — volající díky nim může nechat platnou verzi
      z paměti.
    """
    try:
        nacteno = json.loads(text)
    except (ValueError, TypeError) as e:
        return (None,
                [f"JSON s vlastními melodiemi se nepodařilo přečíst: {e}"],
                [])

    if isinstance(nacteno, dict):
        # Tvar {"id": {…}} — ID vezmeme z klíče, pokud chybí v záznamu.
        polozky = []
        for klic, hodnota in nacteno.items():
            if isinstance(hodnota, dict) and "id" not in hodnota:
                hodnota = {**hodnota, "id": klic}
            polozky.append(hodnota)
    elif isinstance(nacteno, list):
        polozky = nacteno
    else:
        return (None,
                ["JSON s vlastními melodiemi má neočekávaný tvar "
                 "(očekáván seznam nebo slovník)."],
                [])

    vysledek: dict[str, Melodie] = {}
    chyby: list[str] = []
    neplatne_id: list[str] = []
    for i, polozka in enumerate(polozky, start=1):
        try:
            melodie = melodie_z_dict(polozka)
        except ValueError as e:
            chyby.append(f"záznam č. {i}: {e}")
            if isinstance(polozka, dict) and isinstance(polozka.get("id"), str):
                neplatne_id.append(polozka["id"])
            continue
        vysledek[melodie.id] = melodie
    return vysledek, chyby, neplatne_id


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
    """Seznam (id, český název) pro výběrové pole v nastavení.

    Obsahuje přednastavené melodie i vlastní (uživatelské) daného druhu.
    """
    if druh not in DRUHY:
        raise ValueError(f"Neznámý druh melodie: {druh!r}")
    zaklad = ZAKLADNI_SMUTNE if druh == DRUH_SMUTNA else ZAKLADNI_VITEZNE
    polozky = [(mid, m.nazev) for mid, m in zaklad.items()]
    polozky += [(m.id, f"{m.nazev} (vlastní)")
                for m in vlastni_melodie(druh)]
    return polozky


def je_dostupna_melodie(druh: str, id_melodie: str | None) -> bool:
    """True, pokud ID odpovídá nějaké nabízené melodii daného druhu."""
    if not id_melodie:
        return True
    return any(mid == id_melodie for mid, _ in nabidka_melodii(druh))


def ziskej_melodii(tonina: str, druh: str, id_melodie: str | None = None) -> VolbaMelodie:
    """Vyhledá melodii pro tóninu.

    Postup:
    1. vlastní (uživatelská) melodie daného druhu — transpozice z C,
    2. individuální definice pro (tonina, druh, id) — má přednost,
    3. transpozice základní melodie z C do tóniny,
    4. transpozice výchozí melodie daného druhu (id chybí/neplatí),
    5. pevná záložní melodie + varování.

    Neplatné nebo smazané ID nikdy nespadne — použije se bezpečná náhrada.
    """
    theory.over_toninu(tonina)
    if druh not in DRUHY:
        raise ValueError(f"Neznámý druh melodie: {druh!r}")
    id_pozadovane = id_melodie or VYCHOZI_ID[druh]

    # Chybové hlášky z odmítnuté vlastní/individuální definice se
    # připojí k varování náhrady, aby uživatel viděl důvod.
    varovani_vlastni: str | None = None
    varovani_ind: str | None = None

    def _spoj(*zpravy: str | None) -> str | None:
        casti = [z for z in (varovani_vlastni, varovani_ind, *zpravy) if z]
        return "; ".join(casti) or None

    # 1) Vlastní (uživatelské) melodie — definované v C, transponují se.
    vlastni = VLASTNI_MELODIE.get(id_pozadovane)
    if vlastni is not None and vlastni.druh == druh:
        kandidat = transponuj_melodii(vlastni, tonina)
        chyby, varovani = validuj_melodii(kandidat, tonina)
        if not chyby:
            return VolbaMelodie(
                melodie=kandidat, tonina=tonina, druh=druh,
                zdroj="vlastni", varovani="; ".join(varovani) or None,
            )
        varovani_vlastni = ("Vlastní melodii se nepodařilo použít: "
                            + "; ".join(chyby))

    # 2) Individuální definice
    jednotlivec = INDIVIDUALNI_MELODIE.get((tonina, druh, id_pozadovane))
    if jednotlivec is not None:
        chyby, varovani = validuj_melodii(jednotlivec, tonina)
        if not chyby:
            return VolbaMelodie(
                melodie=jednotlivec, tonina=tonina, druh=druh,
                zdroj="individualni",
                varovani=_spoj("; ".join(varovani) or None),
            )
        # Neplatnou individuální melodii nepoužijeme, zkusíme transpozici.
        varovani_ind = ("Individuální melodii se nepodařilo použít: "
                        + "; ".join(chyby))

    # 3) Transpozice základní melodie
    zaklad = ZAKLADNI_VITEZNE if druh == DRUH_VITEZNA else ZAKLADNI_SMUTNE
    zaklad_melodie = zaklad.get(id_pozadovane)
    if zaklad_melodie is not None:
        kandidat = transponuj_melodii(zaklad_melodie, tonina)
        chyby, varovani = validuj_melodii(kandidat, tonina)
        if not chyby:
            return VolbaMelodie(
                melodie=kandidat, tonina=tonina, druh=druh,
                zdroj="transpozice", varovani=_spoj("; ".join(varovani) or None),
            )

    # 4) Výchozí melodie daného druhu
    vychozi = zaklad.get(VYCHOZI_ID[druh])
    if vychozi is not None and id_pozadovane != VYCHOZI_ID[druh]:
        kandidat = transponuj_melodii(vychozi, tonina)
        chyby, varovani = validuj_melodii(kandidat, tonina)
        if not chyby:
            msg = f"Použita výchozí melodie „{vychozi.nazev}“."
            doplneni = "; ".join(varovani)
            if doplneni:
                msg += " " + doplneni
            return VolbaMelodie(
                melodie=kandidat, tonina=tonina, druh=druh,
                zdroj="zalozni", varovani=_spoj(msg),
            )

    # 5) Pevná záložní melodie (poslední jistota)
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
        varovani=_spoj(f"Použita záložní melodie „{zalozni.nazev}“."),
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
