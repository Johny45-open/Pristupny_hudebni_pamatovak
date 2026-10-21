"""Testy workeru — skutečné ukončení vlákna, kooperativní přerušení.

Bez zvukového zařízení: tichý režim simuluje délky tónů, takže testy
fungují i na stroji bez zvukové karty.
"""

from __future__ import annotations

import time

import pytest

from melodies import KrokPrehravani
from player_worker import Prehravac, Uloha
from sound import ZvukovyMotor, generuj_vlnu

import numpy as np


@pytest.fixture(scope="module")
def motor():
    return ZvukovyMotor()


def zpracuj(app, sekundy: float) -> None:
    konec = time.monotonic() + sekundy
    while time.monotonic() < konec:
        app.processEvents()
        time.sleep(0.005)


def cekaj_konec(worker, app, timeout: float = 5.0) -> bool:
    konec = time.monotonic() + timeout
    while not worker.isFinished() and time.monotonic() < konec:
        app.processEvents()
        time.sleep(0.005)
    zpracuj(app, 0.15)   # propustit signály
    return worker.isFinished()


# --- Generování zvuku (bez zařízení) ----------------------------------------

def test_generovani_vlny():
    vlna = generuj_vlnu(69, 0.2)
    assert vlna.dtype == np.int16
    assert vlna.ndim == 2 and vlna.shape[1] == 2
    assert vlna.shape[0] == int(0.2 * 44100)
    assert np.max(np.abs(vlna)) <= 32767
    assert np.max(np.abs(vlna)) > 0, "signál nesmí být nula"
    assert not np.isnan(vlna.astype(float)).any()


def test_generovani_neplatna_delka():
    with pytest.raises(ValueError):
        generuj_vlnu(60, 0)


def test_tichy_rezim_vraci_none():
    motor = ZvukovyMotor()
    motor.dostupny = False   # vynucený tichý režim
    assert motor.vytvor_zvuk(60, 0.2) is None
    assert motor.kanal is None
    motor.zastav_kanal()     # nesmí spadnout
    motor.zastav_vse()


# --- Životní cyklus workeru --------------------------------------------------

def test_worker_dokonci_ulohu_a_skutecne_skonci(qapp, motor):
    kroky = [KrokPrehravani(60, 0.05, 0.01)] * 3
    worker = Prehravac(motor, Uloha("ton", tuple(kroky), "test"))
    vysledky = []
    worker.dokonceno.connect(lambda t, p: vysledky.append((t, p)))
    worker.start()
    assert cekaj_konec(worker, qapp), "worker nedoběhl"
    assert worker.wait(3000) is True, "wait() musí potvrdit konec vlákna"
    assert worker.isFinished() is True
    assert vysledky == [("ton", False)]


def test_preruseni_je_rychle_a_skutecne(qapp, motor):
    """Přerušení musí zastavit přehrávání i worker do 1 sekundy."""
    kroky = [KrokPrehravani(60, 0.05, 0.0)] * 80   # ≥ 4 s
    worker = Prehravac(motor, Uloha("sekvence", tuple(kroky), "dlouhá"))
    vysledky = []
    worker.dokonceno.connect(lambda t, p: vysledky.append((t, p)))
    worker.start()
    zpracuj(qapp, 0.15)      # ať se rozjede
    assert not worker.isFinished()

    zacatek = time.monotonic()
    worker.prerus()
    assert worker.wait(1000) is True, "worker se musí ukončit do 1 s"
    trva = time.monotonic() - zacatek
    assert trva < 1.0, f"ukončení trvalo {trva:.2f} s"
    assert worker.isFinished() is True
    zpracuj(qapp, 0.1)
    assert vysledky == [("sekvence", True)], "signál musí hlásit přerušení"

    # Skutečné zastavení přehrávání: kanál nesmí běžet.
    if motor.dostupny and motor.kanal is not None:
        assert motor.kanal.get_busy() is False


def test_preruseni_pred_startem(qapp, motor):
    kroky = [KrokPrehravani(60, 0.05, 0.0)] * 2
    worker = Prehravac(motor, Uloha("ton", tuple(kroky), "test"))
    worker.prerus()
    worker.start()
    assert cekaj_konec(worker, qapp)
    assert worker.wait(3000) is True


def test_worker_v_tichem_rezimu(qapp):
    motor = ZvukovyMotor()
    motor.dostupny = False
    kroky = [KrokPrehravani(60, 0.05, 0.02)] * 3
    worker = Prehravac(motor, Uloha("sekvence", tuple(kroky), "tichý"))
    vysledky = []
    worker.dokonceno.connect(lambda t, p: vysledky.append((t, p)))
    worker.start()
    assert cekaj_konec(worker, qapp)
    assert worker.wait(3000) is True
    assert vysledky == [("sekvence", False)]
