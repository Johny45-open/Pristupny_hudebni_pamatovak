"""Herní logika Hudebního pamatováku.

Čistý Python bez Qt a zvuku — testovatelný samostatně.

Pravidla kola (schválená specifikace):
- aplikace vygeneruje sekvenci stupňů zvolené durové stupnice,
- vstupy hráče se vyhodnocují pouze ve stavu ``HRAC_VSTUPUJE``
  (tzn. nikdy během přehrávání — to logika odmítne),
- každý přijatý vstup se započte právě jednou,
- chybný vstup spotřebí právě jeden pokus, přehraje se smutná melodie
  a při zbývajících pokusech se hráč vrátí na začátek celé sekvence,
- vyčerpání všech pokusů = neúspěšné kolo,
- úplné zopakování sekvence = úspěšné kolo,
- opakované přehrání sekvence je pouze zvukový výstup a do logiky
  vůbec nevstupuje (nemění skóre ani pokusy).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

import theory
from stats import SpravceStatistik, VysledekIntervalu


def _pocet_pokusu_text(n: int) -> str:
    """Český text pro počet pokusů (1 pokus, 2–4 pokusy, 5+ pokusů)."""
    if n == 1:
        return "1 pokus"
    if 2 <= n <= 4:
        return f"{n} pokusy"
    return f"{n} pokusů"


def _pocet_tonu_text(n: int) -> str:
    """Český text pro počet zbývajících tónů."""
    if n == 1:
        return "1 tón"
    if 2 <= n <= 4:
        return f"{n} tóny"
    return f"{n} tónů"


class StavKola(Enum):
    CEKA_NA_PREHRANI = "ceka_na_prehrani"     # sekvence se má / právě hraje
    HRAC_VSTUPUJE = "hrac_vstupuje"           # hráč může zadávat tóny
    DOKONCENO_USPECH = "dokonceno_uspech"
    DOKONCENO_NEUSPECH = "dokonceno_neuspech"


@dataclass
class VysledekVstupu:
    """Výsledek vyhodnocení jednoho vstupu hráče."""

    prijat: bool                    # False = vstup byl odmítnut (neplatný stav)
    spravne: bool | None
    ocekavany_stupen: int | None
    zadany_stupen: int | None
    pokusy_zbyva: int
    pozice: int
    delka: int
    kolo_dokonceno: bool            # True = kolo právě skončilo
    uspech: bool | None             # výsledek kola, jen pokud kolo_dokonceno
    hlaska: str
    interval: VysledekIntervalu | None = None   # snímek pro dialog statistik
    odmena_dosažena: bool = False
    ztezena_hra: bool = False


@dataclass
class NastaveniHry:
    """Nastavení platné pro další kola (mění se v nastavení hry)."""

    tonina: str = "C"
    oktava: int = 4
    delka_sekvence: int = 4
    pocet_pokusu: int = 3
    interval_statistik: int = 5
    odmena_po_kolech: int = 5
    absolutni_sluch: bool = False
    expertnimode: bool = False
    id_smutne_melodie: str = "kratka_sestupna"
    id_vitezne_melodie: str = "kratka_fanfara"
    rezim: str = "tony"   # "tony" nebo "akordy"
    vyvojarsky_rezim: bool = False

    def over(self) -> None:
        theory.over_toninu(self.tonina)
        if self.oktava not in (3, 4, 5):
            raise ValueError(f"Októva musí být 3, 4 nebo 5, je {self.oktava}")
        if not 2 <= self.delka_sekvence <= 12:
            raise ValueError(
                f"Délka sekvence musí být 2–12, je {self.delka_sekvence}")
        if not 1 <= self.pocet_pokusu <= 10:
            raise ValueError(
                f"Počet pokusů musí být 1–10, je {self.pocet_pokusu}")
        if self.interval_statistik < 1:
            raise ValueError("Interval statistik musí být kladné celé číslo")
        if self.odmena_po_kolech < 1:
            raise ValueError("Odměna po úspěšných kolech musí být kladné celé číslo")
        if not isinstance(self.absolutni_sluch, bool):
            raise ValueError("Absolutní sluch musí být pravdivostní hodnota")
        if self.rezim not in ("tony", "akordy"):
            raise ValueError(f"Neplatný režim hry: {self.rezim!r}")
        if not isinstance(self.vyvojarsky_rezim, bool):
            raise ValueError("Vývojářský režim musí být pravdivostní hodnota")

    def zmenit_na_expert(self) -> None:
        """Nastaví expertní mód: ztíží parametry hry."""
        self.expertnimode = True
        self.delka_sekvence = min(12, self.delka_sekvence + 2)
        self.pocet_pokusu = max(1, self.pocet_pokusu - 1)


class HerniLogika:
    """Stroj stavů kola + napojení na statistiky."""

    def __init__(
        self,
        nastaveni: NastaveniHry | None = None,
        spravce: SpravceStatistik | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.nastaveni = nastaveni or NastaveniHry()
        self.nastaveni.over()
        self.spravce = spravce or SpravceStatistik(
            interval_cil=self.nastaveni.interval_statistik)
        self.rng = rng or random.Random()

        self.stav: StavKola = StavKola.CEKA_NA_PREHRANI
        self.sekvence: list[int] = []      # stupně 0-6
        self.obraty: list[int] = []        # obraty 0-2 pro akordy
        self.pozice: int = 0               # kolikátý tón hráč právě opakuje
        self.pokusy_zbyva: int = 0
        self.pokusy_celkem: int = 0
        self.kolo_cislo: int = 0           # dokončená kola v této hře
        self.aktualni_streak: int = 0      # počet po sobě jdoucích úspěšných kol

    def zmenit_nastaveni(self, **zmeny) -> None:
        """Aplikuje nastavení pro DALŠÍ kola (současné kolo neovlivní)."""
        nove = NastaveniHry(**{**self.nastaveni.__dict__, **zmeny})
        nove.over()
        self.nastaveni = nove
        if "interval_statistik" in zmeny:
            self.spravce.zmenit_cil_intervalu(nove.interval_statistik)

    def nova_hra(self) -> None:
        """Bezpečně resetuje stav hry (kolo, pokusy, pozici).

        Nastavení ani statistiky (celkové i intervalové) nemění.
        """
        self.stav = StavKola.CEKA_NA_PREHRANI
        self.sekvence = []
        self.obraty = []
        self.pozice = 0
        self.pokusy_zbyva = 0
        self.pokusy_celkem = 0
        self.kolo_cislo = 0
        self.aktualni_streak = 0

    def zahaj_kolo(self) -> list[int]:
        """Vygeneruje novou náhodnou sekvenci a připraví kolo.

        Vrací sekvenci stupňů (0-6). Do té doby, než GUI zavolá
        ``sekvence_prehrana()``, jsou vstupy hráče odmítány.
        """
        n = self.nastaveni.delka_sekvence
        self.sekvence = [self.rng.randrange(7) for _ in range(n)]
        self.obraty = [self.rng.randrange(3) for _ in range(n)] if self.nastaveni.rezim == "akordy" else [0] * n
        self.pozice = 0
        self.pokusy_celkem = self.nastaveni.pocet_pokusu
        self.pokusy_zbyva = self.pokusy_celkem
        self.stav = StavKola.CEKA_NA_PREHRANI
        return list(self.sekvence)

    def sekvence_prehrana(self) -> bool:
        """Označí, že sekvence dohrála a hráč může zadávat tóny.

        Volá se jen po dokončeném přehrání (ne po opakovaném přehrání
        uprostřed kola — to stav nemění).
        """
        if self.stav != StavKola.CEKA_NA_PREHRANI:
            return False
        self.stav = StavKola.HRAC_VSTUPUJE
        return True

    def midi_sekvence(self) -> list[int] | list[tuple[int, ...]]:
        """Sekvence převedená na MIDI výšky nebo akordy podle tóniny a oktávy a obratů."""
        if self.nastaveni.rezim == "akordy":
            return [
                tuple(theory.akord_stupne(self.nastaveni.tonina, s, self.nastaveni.oktava, obrat=o))
                for s, o in zip(self.sekvence, self.obraty)
            ]
        stup = theory.stupnice(self.nastaveni.tonina, self.nastaveni.oktava)
        return [stup[s][1] for s in self.sekvence]

    def vyvojarsky_prehled_sekvence(self) -> list[str]:
        """Vrátí detailní popis sekvence pro vývojářský režim."""
        if not getattr(self.nastaveni, "vyvojarsky_rezim", False):
            return []
        if self.nastaveni.rezim != "akordy":
            return [
                theory.nazev_pro_tlacitko(self.nastaveni.tonina, s, self.nastaveni.oktava)[0]
                for s in self.sekvence
            ]
        return [
            theory.popis_akordu_detail(self.nastaveni.tonina, s, self.nastaveni.oktava, o)
            for s, o in zip(self.sekvence, self.obraty)
        ]

    def tlacitka(self) -> list[tuple[str, int]]:
        """Sedm tlačítek: [(přístupný název, MIDI), ...]."""
        if self.nastaveni.rezim == "akordy":
            rez = []
            for s in range(7):
                nazev_akordu = theory.nazev_akordu_stupne(self.nastaveni.tonina, s)
                stup = theory.stupnice(self.nastaveni.tonina, self.nastaveni.oktava)
                _, midi_koorene = stup[s]
                rez.append((f"Akord {nazev_akordu}", midi_koorene))
            return rez
        return [
            theory.nazev_pro_tlacitko(
                self.nastaveni.tonina, s, self.nastaveni.oktava)
            for s in range(7)
        ]

    def ocekavany_ton(self) -> tuple[str, int] | None:
        """(název, MIDI) tónu nebo akordu, který hráč právě má zopakovat."""
        if self.stav != StavKola.HRAC_VSTUPUJE:
            return None
        stupen = self.sekvence[self.pozice]
        if self.nastaveni.rezim == "akordy":
            nazev_akordu = theory.nazev_akordu_stupne(self.nastaveni.tonina, stupen)
            stup = theory.stupnice(self.nastaveni.tonina, self.nastaveni.oktava)
            _, midi = stup[stupen]
            return f"Akord {nazev_akordu}", midi
        else:
            stup = theory.stupnice(self.nastaveni.tonina, self.nastaveni.oktava)
            nazev, midi = stup[stupen]
            return f"{nazev}{midi // 12 - 1}", midi

    # ------------------------------------------------------------------
    # Vstup hráče
    # ------------------------------------------------------------------

    def zpracuj_vstup(self, stupen: int) -> VysledekVstupu:
        """Vyhodnotí právě jeden vstup hráče (stupeň 0-6).

        Mimo stav ``HRAC_VSTUPUJE`` je vstup odmítnut a nezapočte se.
        """
        def prazdny(hlaska: str) -> VysledekVstupu:
            return VysledekVstupu(
                prijat=False, spravne=None, ocekavany_stupen=None,
                zadany_stupen=None, pokusy_zbyva=self.pokusy_zbyva,
                pozice=self.pozice, delka=len(self.sekvence),
                kolo_dokonceno=False, uspech=None, hlaska=hlaska,
            )

        if not 0 <= stupen <= 6:
            return prazdny(f"Neplatný stupeň: {stupen}")
        if self.stav != StavKola.HRAC_VSTUPUJE:
            return prazdny("Teď se nehraje — vstup nebyl přijat.")

        ocekavany = self.sekvence[self.pozice]
        delka = len(self.sekvence)

        if stupen == ocekavany:
            # Správný tón — započte se právě jednou.
            self.spravce.zaznamenej_spravny_ton()
            self.pozice += 1
            if self.pozice >= delka:
                # Úspěšné dokončení celé sekvence.
                self.stav = StavKola.DOKONCENO_USPECH
                self.kolo_cislo += 1
                self.aktualni_streak += 1
                odmena = (self.aktualni_streak > 0 and self.aktualni_streak % self.nastaveni.odmena_po_kolech == 0)
                interval = self.spravce.kolo_dokonceno(uspech=True)
                ztezena = False
                if interval is not None and self.nastaveni.absolutni_sluch:
                    if interval.interval.neuspesna_kola == 0:
                        self.nastaveni.zmenit_na_expert()
                        ztezena = True

                casti_hlasky = ["Gratuluji, sekvence je správně zopakovaná."]
                if odmena:
                    casti_hlasky.append(f"Získáváte odměnu za {self.aktualni_streak} úspěšných kol v řadě!")
                if ztezena:
                    casti_hlasky.append(f"Máte absolutní hudební sluch a zvládli jste všechna kola — hra se stává těžší (délka sekvence: {self.nastaveni.delka_sekvence}, pokusy: {self.nastaveni.pocet_pokusu}).")

                return VysledekVstupu(
                    prijat=True, spravne=True,
                    ocekavany_stupen=ocekavany, zadany_stupen=stupen,
                    pokusy_zbyva=self.pokusy_zbyva, pozice=self.pozice,
                    delka=delka, kolo_dokonceno=True, uspech=True,
                    hlaska=" ".join(casti_hlasky),
                    interval=interval,
                    odmena_dosažena=odmena,
                    ztezena_hra=ztezena,
                )
            zbyva = delka - self.pozice
            return VysledekVstupu(
                prijat=True, spravne=True, ocekavany_stupen=ocekavany,
                zadany_stupen=stupen, pokusy_zbyva=self.pokusy_zbyva,
                pozice=self.pozice, delka=delka, kolo_dokonceno=False,
                uspech=None,
                hlaska=(f"Správně. Zbývá zopakovat {_pocet_tonu_text(zbyva)}."),
            )

        # Chybný tón — započte se právě jednou a spotřebuje jeden pokus.
        self.spravce.zaznamenej_chybny_ton()
        self.pokusy_zbyva -= 1
        if self.pokusy_zbyva <= 0:
            self.stav = StavKola.DOKONCENO_NEUSPECH
            self.kolo_cislo += 1
            self.aktualni_streak = 0
            interval = self.spravce.kolo_dokonceno(uspech=False)
            return VysledekVstupu(
                prijat=True, spravne=False, ocekavany_stupen=ocekavany,
                zadany_stupen=stupen, pokusy_zbyva=0, pozice=self.pozice,
                delka=delka, kolo_dokonceno=True, uspech=False,
                hlaska=("Vyčerpány všechny pokusy, kolo je neúspěšné."),
                interval=interval,
            )

        # Zbývají pokusy → hráč začíná znovu od začátku sekvence.
        self.pozice = 0
        spravne = self.spravce.celkem.spravne_tony
        chybne = self.spravce.celkem.chybne_tony
        return VysledekVstupu(
            prijat=True, spravne=False, ocekavany_stupen=ocekavany,
            zadany_stupen=stupen, pokusy_zbyva=self.pokusy_zbyva,
            pozice=self.pozice, delka=delka, kolo_dokonceno=False,
            uspech=None,
            hlaska=(f"Chyba, správný tón byl očekáván jiný. "
                    f"Zbývá {_pocet_pokusu_text(self.pokusy_zbyva)}, "
                    f"začínáte znovu od začátku. "
                    f"Celkem správně {spravne}, chybně {chybne}."),
        )

    def zopovat_kolo(self) -> bool:
        """Restartuje současné kolo: stejná sekvence, plné pokusy.

        Statistiky se nemění (kolo nebylo dokončeno). Vrátí True,
        pokud restart proběhl (kolo musí být rozehrané nebo právě
        dokončené).
        """
        if not self.sekvence:
            return False
        if self.stav == StavKola.CEKA_NA_PREHRANI:
            return False   # sekvence právě hraje — nic nerestartujeme
        self.pozice = 0
        self.pokusy_zbyva = self.pokusy_celkem
        self.stav = StavKola.CEKA_NA_PREHRANI
        return True

    # ------------------------------------------------------------------
    # Popisy pro GUI
    # ------------------------------------------------------------------

    def popis_stavu(self) -> str:
        if self.stav == StavKola.DOKONCENO_USPECH:
            return "Kolo dokončeno úspěšně."
        if self.stav == StavKola.DOKONCENO_NEUSPECH:
            return "Kolo dokončeno neúspěšně, vyčerpány pokusy."
        if not self.sekvence:
            return "Není rozehrané kolo. Spusťte novou hru."
        if self.stav == StavKola.CEKA_NA_PREHRANI:
            return "Přehrává se nebo se připravuje sekvence tónů."
        return (f"Pozice {self.pozice + 1} z {len(self.sekvence)}, "
                f"zbývá {_pocet_pokusu_text(self.pokusy_zbyva)}.")
