"""Společné testovací fixtury.

- Offscreen platforma (bez fyzické obrazovky a bez myši).
- Bez zvukového zařízení musí testy fungovat (tichý režim).
"""

from __future__ import annotations

import os
import time

# Musí být před prvním importem PyQt6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile     # noqa: E402

from PyQt6.QtCore import QSettings     # noqa: E402

# Všechna QSettings v testech míří do dočasné složky, ne do profilu uživatele.
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                  tempfile.mkdtemp(prefix="pamatovak_qsettings_"))

import pytest     # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """Jedna QApplication pro všechny GUI testy."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def zpracuj_udalosti(app, sekundy: float = 0.05) -> None:
    """Propustí události po danou dobu (náhrada za spaní v GUI)."""
    konec = time.monotonic() + sekundy
    while time.monotonic() < konec:
        app.processEvents()
        time.sleep(0.005)


def cekaj_na_worker(window, app, timeout: float = 8.0) -> bool:
    """Čeká, než worker okna skončí. Vrací True, pokud stihl."""
    konec = time.monotonic() + timeout
    while window._worker is not None and time.monotonic() < konec:
        app.processEvents()
        time.sleep(0.01)
    # Zbývající signály (finished, dokonceno) ještě propustit.
    zpracuj_udalosti(app, 0.1)
    return window._worker is None
