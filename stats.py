"""Statistiky hry — intervalové a celkové.

Čistý Python bez Qt a zvuku. Každý vstup hráče se započítá právě jednou;
zvuky přehrávané aplikací se nikdy nevyhodnocují jako vstup.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Statistiky:
    """Počítadla jedné oblasti statistik (interval nebo celkem)."""

    spravne_tony: int = 0
    chybne_tony: int = 0
    uspesna_kola: int = 0
    neuspesna_kola: int = 0

    @property
    def dokoncena_kola(self) -> int:
        return self.uspesna_kola + self.neuspesna_kola

    def reset(self) -> None:
        self.spravne_tony = 0
        self.chybne_tony = 0
        self.uspesna_kola = 0
        self.neuspesna_kola = 0

    def kopie(self) -> "Statistiky":
        return Statistiky(
            spravne_tony=self.spravne_tony,
            chybne_tony=self.chybne_tony,
            uspesna_kola=self.uspesna_kola,
            neuspesna_kola=self.neuspesna_kola,
        )

    def jako_text(self) -> str:
        return (
            f"správně zahrané tóny: {self.spravne_tony}, "
            f"chybně zahrané tóny: {self.chybne_tony}, "
            f"úspěšná kola: {self.uspesna_kola}, "
            f"neúspěšná kola: {self.neuspesna_kola}, "
            f"dokončená kola celkem: {self.dokoncena_kola}"
        )


@dataclass
class VysledekIntervalu:
    """Snímek intervalu při jeho dokončení — pro zobrazení dialogu."""

    interval: Statistiky
    celkem: Statistiky
    pocet_kol: int


class SpravceStatistik:
    """Spravuje intervalové i celkové statistiky.

    Pravidla:
    - každý vyhodnocený vstup hráče se započte právě jednou,
    - dokončené kolo = úspěšné NEBO neúspěšné,
    - po přesně ``interval_cil`` dokončených kolech se vrátí snímek
      intervalu a interval se resetuje; celkové statistiky zůstanou,
    - snímek se vrátí právě jednou (opakované volání nic nevrátí).
    """

    def __init__(self, interval_cil: int = 5) -> None:
        if interval_cil < 1:
            raise ValueError("Interval statistik musí být kladné celé číslo")
        self.celkem = Statistiky()
        self.interval = Statistiky()
        self.interval_cil = interval_cil

    # -- vstupy hráče ------------------------------------------------------

    def zaznamenej_spravny_ton(self) -> None:
        self.celkem.spravne_tony += 1
        self.interval.spravne_tony += 1

    def zaznamenej_chybny_ton(self) -> None:
        self.celkem.chybne_tony += 1
        self.interval.chybne_tony += 1

    # -- dokončení kola -----------------------------------------------------

    def kolo_dokonceno(self, uspech: bool) -> VysledekIntervalu | None:
        """Započte dokončené kolo.

        Pokud tím byl dokončen interval, vrátí snímek a interval
        se ihned resetuje na nové období. V opačném případě None.
        """
        if uspech:
            self.celkem.uspesna_kola += 1
            self.interval.uspesna_kola += 1
        else:
            self.celkem.neuspesna_kola += 1
            self.interval.neuspesna_kola += 1

        if self.interval.dokoncena_kola >= self.interval_cil:
            vysledek = VysledekIntervalu(
                interval=self.interval.kopie(),
                celkem=self.celkem.kopie(),
                pocet_kol=self.interval_cil,
            )
            self.interval.reset()   # nové období, celkové zůstávají
            return vysledek
        return None

    def zmenit_cil_intervalu(self, cil: int) -> None:
        """Změní cíl intervalu pro další období (validace kladného čísla)."""
        if cil < 1:
            raise ValueError("Interval statistik musí být kladné celé číslo")
        self.interval_cil = cil
