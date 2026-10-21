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

    # Načtení uloženého nastavení (QSettings — na Windows registr,
    # viz uloziste) a nastavení hlasového výstupu.
    nastaveni = uloziste.nacti_nastaveni()
    nastaveni_hlasu = uloziste.nacti_nastaveni_hlasu()

    # Vlastní melodie z JSON souboru. Poškozená data nikdy nezruší
    # přednastavené melodie — jen se ohlásí.
    _, chyby_melodii = uloziste.nacti_vlastni_melodie()

    # Zvuk — bez zařízení aplikace běží v tichém režimu, nepadá.
    motor = ZvukovyMotor()

    # Přístupná oznámení (accessible_output2 + stavový panel jako fallback).
    oznamovac = Oznamovac()

    spravce = SpravceStatistik(interval_cil=nastaveni.interval_statistik)
    logika = HerniLogika(nastaveni=nastaveni, spravce=spravce)

    okno = HlavniOkno(logika, motor, oznamovac, nastaveni,
                      nastaveni_hlasu=nastaveni_hlasu)
    okno.show()

    # Uvolnění zvuku až po ukončení smyčky událostí.
    app.aboutToQuit.connect(motor.uvolni)

    casti = []
    if chyby_melodii:
        casti.append(
            "Při načítání vlastních melodií nastal problém: "
            + "; ".join(chyby_melodii) + ".")
    casti.append(
        "Hudební pamatovák je připraven. Spusťte novou hru klávesou F2. "
        + motor.popis_rezimu() + " " + oznamovac.popis_dostupnosti)
    okno._oznam(" ".join(casti), hlasite=False)

    kod = app.exec()

    # Bezpečnostní kontrola: worker musí být po ukončení smyčky hotový.
    if okno._worker is not None:
        okno._worker.wait(3000)
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
