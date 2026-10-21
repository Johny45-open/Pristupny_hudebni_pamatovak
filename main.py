"""Hudební pamatovák — vstupní bod aplikace.

Spuštění:  python main.py
"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

import uloziste
from game_logic import HerniLogika
from gui.main_window import HlavniOkno
from notify import Oznamovac
from sound import ZvukovyMotor
from stats import SpravceStatistik


def vytvor_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("HudebniPamatovak")
    app.setApplicationDisplayName("Hudební pamatovák")
    app.setOrganizationName("PristupnyHudebniPamatovak")
    return app


def main() -> int:
    app = vytvor_app()

    # Načtení uloženého nastavení (QSettings, INI v profilu uživatele).
    nastaveni = uloziste.nacti_nastaveni()

    # Zvuk — bez zařízení aplikace běží v tichém režimu, nepadá.
    motor = ZvukovyMotor()

    # Přístupná oznámení (accessible_output2 + stavový panel jako fallback).
    oznamovac = Oznamovac()

    spravce = SpravceStatistik(interval_cil=nastaveni.interval_statistik)
    logika = HerniLogika(nastaveni=nastaveni, spravce=spravce)

    okno = HlavniOkno(logika, motor, oznamovac, nastaveni)
    okno.show()

    # Uvolnění zvuku až po ukončení smyčky událostí.
    app.aboutToQuit.connect(motor.uvolni)

    okno._oznam(
        "Hudební pamatovák je připraven. Spusťte novou hru klávesou F2. "
        + motor.popis_rezimu() + " " + oznamovac.popis_dostupnosti,
        hlasite=False,
    )

    kod = app.exec()

    # Bezpečnostní kontrola: worker musí být po ukončení smyčky hotový.
    if okno._worker is not None:
        okno._worker.wait(3000)
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
