"""Offscreen GUI testy — přístupnost, klávesnice, vlákna, zavírání, dialogy.

Běží bez fyzické obrazovky (QT_QPA_PLATFORM=offscreen) a bez zvukového
zařízení (tichý režim). Žádný test nevyžaduje myš ani odečítač.
"""

from __future__ import annotations

import random
import time

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QSpinBox,
)

from tests.conftest import cekaj_na_worker, zpracuj_udalosti

import melodies
import gui.main_window as gm
from game_logic import HerniLogika, NastaveniHry, StavKola
from gui.main_window import HlavniOkno
from gui.settings_dialog import NastaveniDialog
from gui.stats_dialog import StatsDialog
from notify import Oznamovac
from player_worker import Prehravac
from sound import ZvukovyMotor
from stats import SpravceStatistik, Statistiky


@pytest.fixture(params=[100])
def okno(qapp, request):
    """Hotové hlavní okno s deterministickou logikou."""
    interval = request.param
    nastaveni = NastaveniHry(interval_statistik=interval)
    logika = HerniLogika(
        nastaveni=nastaveni,
        spravce=SpravceStatistik(interval_cil=interval),
        rng=random.Random(20241018),
    )
    motor = ZvukovyMotor()
    okno = HlavniOkno(logika, motor, Oznamovac(), nastaveni)
    # Testy nesmí vyžadovat hlasové zařízení — řeč odpojíme.
    # Panel s textem zůstává plnohodnotnou přístupní cestou.
    okno.oznamovac._vystup = None
    okno.show()
    okno.activateWindow()
    zpracuj_udalosti(qapp, 0.05)
    yield okno
    if okno._worker is not None:
        okno._worker.prerus()
        okno._worker.wait(3000)
    okno._muzu_zavrit = True
    okno.close()
    zpracuj_udalosti(qapp, 0.05)


def hraj(okno, qapp) -> None:
    """Spustí novou hru a počká, až se sekvence dohraje."""
    okno._nova_hra()
    assert okno._worker is not None, "přehrávání se mělo spustit"
    assert cekaj_na_worker(okno, qapp), "worker nedoběhl"
    assert okno.logika.stav is StavKola.HRAC_VSTUPUJE


def spravny_stupen(okno) -> int:
    return okno.logika.sekvence[okno.logika.pozice]


# ==================================================================
# Přístupnost
# ==================================================================

def test_tlacitka_tonu_maji_pristupne_nazvy(okno):
    for tlacitko in okno._tlacitka_tonu:
        nazev = tlacitko.accessibleName()
        assert nazev.startswith("Tón "), nazev
        assert "oktáva" in nazev, nazev
        assert tlacitko.accessibleDescription(), "chybí popis tlačítka"
        # Žádné generické „Tlačítko 1“.
        assert "Tlačítko" not in nazev


def test_nazvy_ovladacich_tlacitek(okno):
    ocekavana = {
        "Nová hra", "Přehrát sekvenci znovu", "Zopakovat aktuální kolo",
        "Nastavení hry", "Statistiky", "Ukončit aplikaci",
        "Zopakovat poslední hlášení", "Pokračovat ve hře",
    }
    nalezena = {okno._t_nova.accessibleName(),
                okno._t_znovu.accessibleName(),
                okno._t_zopovat_kolo.accessibleName(),
                okno._t_nastaveni.accessibleName(),
                okno._t_stats.accessibleName(),
                okno._t_ukoncit.accessibleName(),
                okno.panel.tlacitko_zopakovat.accessibleName(),
                okno._t_pokracovat.accessibleName()}
    assert ocekavana <= nalezena
    for nazev in nalezena:
        assert nazev not in ("Akce", "Tlačítko", ""), nazev


def test_panel_zrcadli_hlaseni(okno):
    okno._oznam("Chyba, zbývá 2 pokusy, začínáte znovu.")
    assert okno.panel.text == "Chyba, zbývá 2 pokusy, začínáte znovu."
    # Při fokusu odečítač přečte samotný obsah, ne jen „Poslední hlášení“.
    assert "Chyba, zbývá 2 pokusy" in okno.panel.accessibleName()
    assert okno.panel.focusPolicy() == okno.panel.focusPolicy().StrongFocus


def test_tlacitko_opakovani_zopakuje_hlaseni(okno, qapp):
    hlas = []
    okno.oznamovac._vystup = type(
        "H", (), {
            "get_first_available_output": lambda self: self,
            "speak": lambda self, text, interrupt=True, **kw: hlas.append(text),
        })()
    okno._oznam("Testovací hlášení pro opakování")
    hlas.clear()
    okno.panel.tlacitko_zopakovat.click()
    assert hlas == ["Testovací hlášení pro opakování"]


def test_popisek_maji_pristupny_prvek_info(okno):
    assert okno._label_info.accessibleName() == "Průběh hry"
    assert okno._label_info.text(), "informace o hře nesmí být prázdné"
    assert okno.panel.accessibleName().startswith("Poslední hlášení")


def test_dialog_nastaveni_ma_buddy_a_popisky(qapp):
    dialog = NastaveniDialog(NastaveniHry())
    # Každé pole musí mít popisek propojený přes setBuddy.
    buddy_pairs = {}
    for label in dialog.findChildren(QLabel):
        if label.buddy() is not None:
            buddy_pairs[id(label.buddy())] = label.text()
    for widget, popisek in ((dialog.tonina, "Tónina:"),
                            (dialog.oktava, "Výchozí oktáva:"),
                            (dialog.pokusy, "Počet pokusů:"),
                            (dialog.delka, "Délka sekvence:"),
                            (dialog.interval, "Interval statistik:"),
                            (dialog.smutna, "Smutná melodie:"),
                            (dialog.vitezna, "Vítězná melodie:")):
        assert widget.accessibleName(), "pole bez přístupného názvu"
        assert id(widget) in buddy_pairs, f"bez buddy: {widget.accessibleName()}"
        assert buddy_pairs[id(widget)] == popisek
    # Validované rozsahy.
    assert dialog.delka.minimum() == 2 and dialog.delka.maximum() == 12
    assert dialog.pokusy.minimum() == 1 and dialog.pokusy.maximum() == 10
    assert dialog.interval.minimum() == 1
    hodnoty = dialog.hodnoty()
    assert hodnoty["tonina"] in ("C", "G", "D", "A", "E", "H", "Fis", "Cis",
                                 "F", "B", "Es", "As", "Des", "Ges", "Ces")


def test_dialog_nastaveni_informuje_o_melodii(qapp):
    dialog = NastaveniDialog(NastaveniHry())
    assert "melodie" in dialog._info.text().lower()
    dialog.tonina.setCurrentIndex(dialog.tonina.findData("Fis"))
    zpracuj_udalosti(qapp, 0.05)
    assert "Fis dur" in dialog._info.text()


def test_dialog_statistik_zobrazi_hodnoty(qapp):
    dialog = StatsDialog(
        Statistiky(spravne_tony=7, chybne_tony=3,
                   uspesna_kola=2, neuspesna_kola=1),
        Statistiky(spravne_tony=20, chybne_tony=5,
                   uspesna_kola=6, neuspesna_kola=2),
        "Období: testovací.")
    assert "7" in dialog.text_intervalu and "3" in dialog.text_intervalu
    assert "20" in dialog.text_celkem
    # Přístupné názvy s obsahem hlídá test
    # test_dialog_statistik_pristupne_nazvy_obsahuji_hodnoty.


def test_dialog_statistik_pristupne_nazvy_obsahuji_hodnoty(qapp):
    """Čtečka čte z QLabel přes UIA jen Name — musí obsahovat i čísla."""
    dialog = StatsDialog(
        Statistiky(spravne_tony=7, chybne_tony=3,
                   uspesna_kola=2, neuspesna_kola=1),
        Statistiky(spravne_tony=20, chybne_tony=5,
                   uspesna_kola=6, neuspesna_kola=2),
        "Období: právě dokončený interval.")

    nazev_int = dialog._label_interval.accessibleName()
    assert nazev_int.startswith("Výsledky intervalu: ")
    assert "7" in nazev_int and "3" in nazev_int
    assert "20" not in nazev_int, "cizí hodnoty se nesmí míchat do intervalu"

    nazev_celk = dialog._label_celkem.accessibleName()
    assert nazev_celk.startswith("Celkové výsledky: ")
    assert "20" in nazev_celk

    nazev_obdobi = dialog._label_obdobi.accessibleName()
    assert nazev_obdobi.startswith("Období intervalu: ")
    assert "právě dokončený interval" in nazev_obdobi

    # Text viditelný v prvku a text čtený čtečkou se nesmí rozejít.
    assert dialog.text_intervalu in nazev_int
    assert dialog.text_celkem in nazev_celk


# ==================================================================
# Klávesnice a kontext zkratek
# ==================================================================

def test_kontext_povolen_ve_hre(okno, qapp):
    okno.activateWindow()
    okno._t_nova.setFocus()
    zpracuj_udalosti(qapp, 0.05)
    assert okno._kontext_klavesy_povolen() is True


def test_kontext_zakazan_v_ciselnem_vstupu(okno, qapp):
    spin = QSpinBox(okno)
    spin.setRange(1, 10)
    spin.show()
    spin.setFocus()
    zpracuj_udalosti(qapp, 0.05)
    assert QApplication.focusWidget() is spin
    assert okno._kontext_klavesy_povolen() is False
    spin.close()


def test_kontext_zakazan_v_modalem(okno, qapp):
    dialog = QDialog(okno)
    dialog.setModal(True)
    dialog.open()
    zpracuj_udalosti(qapp, 0.1)
    assert QApplication.activeModalWidget() is dialog
    assert okno._kontext_klavesy_povolen() is False
    dialog.close()
    zpracuj_udalosti(qapp, 0.1)
    assert okno._kontext_klavesy_povolen() is True


def test_klavesy_1_7_v_modalu_nezadaji_ton(okno, qapp):
    hraj(okno, qapp)
    spravne_pred = okno.logika.spravce.celkem.spravne_tony
    dialog = QDialog(okno)
    dialog.setModal(True)
    dialog.open()
    zpracuj_udalosti(qapp, 0.1)
    okno._klavesa_ton(spravny_stupen(okno))   # nesmí provést vstup
    assert okno.logika.spravce.celkem.spravne_tony == spravne_pred
    dialog.close()
    zpracuj_udalosti(qapp, 0.1)
    # Po zavření dialogu klávesa zase funguje.
    okno._klavesa_ton(spravny_stupen(okno))
    assert okno.logika.spravce.celkem.spravne_tony == spravne_pred + 1


def test_klavesa_ve_spinboxu_nezada_ton(okno, qapp):
    hraj(okno, qapp)
    spravne_pred = okno.logika.spravce.celkem.spravne_tony
    spin = QSpinBox(okno)
    spin.show()
    spin.setFocus()
    zpracuj_udalosti(qapp, 0.05)
    okno._klavesa_ton(0)
    assert okno.logika.spravce.celkem.spravne_tony == spravne_pred
    spin.close()


# ==================================================================
# Herní tok v GUI
# ==================================================================

def test_nova_hra_prehraje_sekvenci_a_povoli_vstup(okno, qapp):
    hraj(okno, qapp)
    assert len(okno.logika.sekvence) == 4
    assert okno.logika.pokusy_zbyva == 3
    assert all(t.isEnabled() for t in okno._tlacitka_tonu)
    assert okno.logika.spravce.celkem.dokoncena_kola == 0
    assert "sekvence" in okno.panel.text.lower() or "hru" in okno.panel.text.lower()


def test_tlacitka_zakazana_behem_prehravani(okno, qapp):
    okno._nova_hra()
    assert okno._worker is not None
    assert not any(t.isEnabled() for t in okno._tlacitka_tonu), \
        "během přehrávání musí být tóny zakázané"
    assert not okno._t_nova.isEnabled()
    assert cekaj_na_worker(okno, qapp)
    assert all(t.isEnabled() for t in okno._tlacitka_tonu)


def test_spravny_vstup(okno, qapp):
    hraj(okno, qapp)
    okno._vstup_ton(spravny_stupen(okno))
    assert okno.logika.spravce.celkem.spravne_tony == 1
    # Zpětná vazba tónem = dočasné zakázání ovládání.
    assert okno._worker is not None
    assert not any(t.isEnabled() for t in okno._tlacitka_tonu)
    assert cekaj_na_worker(okno, qapp)
    assert all(t.isEnabled() for t in okno._tlacitka_tonu)
    assert "Správně" in okno.panel.text


def test_spatny_vstup_snizi_pokusy_a_oznamuje(okno, qapp):
    hraj(okno, qapp)
    spatny = (okno.logika.sekvence[0] + 1) % 7
    okno._vstup_ton(spatny)
    assert cekaj_na_worker(okno, qapp)
    assert okno.logika.pokusy_zbyva == 2
    assert "Zbývá 2 pokusy" in okno.panel.text
    assert "Chyba" in okno.panel.text
    assert okno.logika.spravce.celkem.chybne_tony == 1
    assert okno.logika.pozice == 0, "návrat na začátek sekvence"


def test_opakovani_sekvence_nemeni_skore(okno, qapp):
    hraj(okno, qapp)
    okno._vstup_ton(spravny_stupen(okno))
    assert cekaj_na_worker(okno, qapp)
    pred = (okno.logika.spravce.celkem.spravne_tony,
            okno.logika.spravce.celkem.chybne_tony,
            okno.logika.pokusy_zbyva, okno.logika.pozice,
            okno.logika.stav,
            okno.logika.spravce.celkem.dokoncena_kola)
    okno._prehraj_sekvenci_znovu()
    assert okno._worker is not None
    assert cekaj_na_worker(okno, qapp)
    po = (okno.logika.spravce.celkem.spravne_tony,
          okno.logika.spravce.celkem.chybne_tony,
          okno.logika.pokusy_zbyva, okno.logika.pozice,
          okno.logika.stav, okno.logika.spravce.celkem.dokoncena_kola)
    assert pred == po, "opakování sekvence nesmí měnit skóre ani pokusy"


def test_zopovat_kolo_v_gui(okno, qapp):
    hraj(okno, qapp)
    okno._vstup_ton((okno.logika.sekvence[0] + 1) % 7)   # chyba
    assert cekaj_na_worker(okno, qapp)
    okno._t_zopovat_kolo.click()
    assert okno._worker is not None
    assert cekaj_na_worker(okno, qapp)
    assert okno.logika.pokusy_zbyva == 3, "restart musí vrátit plné pokusy"
    assert okno.logika.pozice == 0


@pytest.mark.parametrize("okno", [1], indirect=True)
def test_uspesne_kolo_a_dialog_intervalu(okno, qapp, monkeypatch):
    """Dialog intervalu až PO výsledkové melodii a právě jednou."""
    zavazane = []
    monkeypatch.setattr(
        okno, "_otevri_stats_intervalu",
        lambda v: zavazane.append((v, okno._worker is None)))

    hraj(okno, qapp)
    for _ in range(3):
        okno._vstup_ton(spravny_stupen(okno))
        assert cekaj_na_worker(okno, qapp)   # zpětná vazba tónem
    okno._vstup_ton(spravny_stupen(okno))    # 4. tón dokončí kolo
    # Kolo dokončeno → vítězná melodie právě hraje, dialog zatím NE.
    assert okno.logika.stav is StavKola.DOKONCENO_USPECH
    assert okno._worker is not None, "měla by hrát vítězná melodie"
    assert zavazane == [], "dialog nesmí otevřít před dohráním melodie"
    assert cekaj_na_worker(okno, qapp)
    assert len(zavazane) == 1, "dialog se musí otevřít právě jednou"
    vysledek, worker_hotov = zavazane[0]
    assert worker_hotov, "worker musí být hotov, když se otevírá dialog"
    assert vysledek.interval.uspesna_kola == 1
    # Druhé kolo spustí další interval (cil=1 → každé kolo = interval).
    hraj(okno, qapp)
    for _ in range(4):
        okno._vstup_ton(spravny_stupen(okno))
        assert cekaj_na_worker(okno, qapp)
    assert len(zavazane) == 2, "každý interval právě jednou"


@pytest.mark.parametrize("okno", [1], indirect=True)
def test_chyba_s_zbyvajicimi_pokusy_neotevre_dialog(okno, qapp, monkeypatch):
    """Chyba se zbývajícími pokusy nesmí spustit intervalový dialog."""
    zavazane = []
    monkeypatch.setattr(
        okno, "_otevri_stats_intervalu", lambda v: zavazane.append(v))
    hraj(okno, qapp)
    okno._vstup_ton((okno.logika.sekvence[0] + 1) % 7)
    assert cekaj_na_worker(okno, qapp)
    assert zavazane == []
    assert okno.logika.spravce.celkem.dokoncena_kola == 0
    assert "Zbývá 2 pokusy" in okno.panel.text


@pytest.mark.parametrize("okno", [1], indirect=True)
def test_dialog_po_neuspesnem_kole_a_po_melodii(okno, qapp, monkeypatch):
    zavazane = []
    monkeypatch.setattr(
        okno, "_otevri_stats_intervalu",
        lambda v: zavazane.append((v, okno._worker is None)))
    hraj(okno, qapp)
    spatny = (okno.logika.sekvence[0] + 1) % 7
    for _ in range(2):                       # dvě chyby se zbývajícími pokusy
        okno._vstup_ton(spatny)
        assert cekaj_na_worker(okno, qapp)
    okno._vstup_ton(spatny)                  # poslední pokus → konec kola
    assert okno.logika.stav is StavKola.DOKONCENO_NEUSPECH
    assert zavazane == [], "smutná melodie ještě hraje"
    assert cekaj_na_worker(okno, qapp)
    assert len(zavazane) == 1
    vysledek, worker_hotov = zavazane[0]
    assert worker_hotov
    assert vysledek.interval.neuspesna_kola == 1
    assert okno.logika.spravce.celkem.neuspesna_kola == 1


def test_fokus_po_prehravani_a_po_kole(okno, qapp):
    """Po sekvenci fokus na první tón, po dokončení kola na Novou hru."""
    hraj(okno, qapp)
    assert qapp.focusWidget() is okno._tlacitka_tonu[0], \
        "po sekvenci patří fokus na první tón"
    for _ in range(4):
        okno._vstup_ton(spravny_stupen(okno))
        assert cekaj_na_worker(okno, qapp)
    assert qapp.focusWidget() is okno._t_nova, \
        "po dokončení kola patří fokus na Novou hru"


def test_fokus_po_zavreni_statistik(okno, qapp):
    """Po zavření dialogu statistik se fokus vrátí na tlačítko Statistiky."""
    okno._t_stats.setFocus()
    zpracuj_udalosti(qapp, 0.05)
    QTimer.singleShot(150,
                      lambda: QApplication.activeModalWidget().accept())
    okno._otevri_stats()
    zpracuj_udalosti(qapp, 0.1)
    assert qapp.focusWidget() is okno._t_stats


def test_fokus_po_zavreni_nastaveni(okno, qapp):
    """Po zavření nastavení se fokus vrátí na tlačítko Nastavení hry."""
    okno._t_nastaveni.setFocus()
    zpracuj_udalosti(qapp, 0.05)
    QTimer.singleShot(150,
                      lambda: QApplication.activeModalWidget().reject())
    okno._otevri_nastaveni()
    zpracuj_udalosti(qapp, 0.1)
    assert qapp.focusWidget() is okno._t_nastaveni


def test_zmena_nastaveni_v_gui(okno, qapp):
    # Bez rozehraného kola → použije se rovnou.
    okno._pouzij_nastaveni({
        "tonina": "Fis", "oktava": 5, "delka_sekvence": 6,
        "pocet_pokusu": 7, "interval_statistik": 4,
        "id_smutne_melodie": "dlouhy_smutny",
        "id_vitezne_melodie": "slavnostni",
    })
    assert okno.logika.nastaveni.tonina == "Fis"
    assert okno.logika.nastaveni.oktava == 5
    nazvy = [t.accessibleName() for t in okno._tlacitka_tonu]
    assert nazvy[0] == "Tón Fis, oktáva 5"
    assert "oktáva 6" in nazvy[4]   # Cis ve Fis dur z oktávy 5 zní jako Cis6?

    # Za rozehraného kola → nastavení se odloží na další kolo.
    hraj(okno, qapp)
    seq_pred = list(okno.logika.sekvence)
    okno._pouzij_nastaveni({
        "tonina": "C", "oktava": 4, "delka_sekvence": 2,
        "pocet_pokusu": 1, "interval_statistik": 5,
        "id_smutne_melodie": "kratka_sestupna",
        "id_vitezne_melodie": "kratka_fanfara",
    })
    assert okno.logika.sekvence == seq_pred, "kolo se nesmí změnit"
    # Nastavení je uložené v okně (pro další kola), logiku rozehraného
    # kola neovlivnilo.
    assert okno.nastaveni.tonina == "C"
    assert okno.logika.nastaveni.tonina == "Fis"
    assert "od dalšího kola" in okno.panel.text


def test_nastaveni_melodii_se_propisuje(okno):
    okno._pouzij_nastaveni({
        "tonina": "C", "oktava": 4, "delka_sekvence": 4,
        "pocet_pokusu": 3, "interval_statistik": 5,
        "id_smutne_melodie": "pomala_sestupna",
        "id_vitezne_melodie": "slavnostni",
    })
    kroky_vybrane = okno._kroky_melodie(melodies.DRUH_VITEZNA)
    okno.nastaveni.id_vitezne_melodie = "kratka_fanfara"
    kroky_jine = okno._kroky_melodie(melodies.DRUH_VITEZNA)
    assert kroky_vybrane != kroky_jine, "jiná volba = jiná melodie"


# ==================================================================
# Zavírání okna a životní cyklus workeru
# ==================================================================

def test_zavirani_behem_prehravani(okno, qapp):
    """close() nesmí zavřít okno, dokud worker běží; po jeho konci zavře."""
    hraj(okno, qapp)
    dlouha = [melodies.KrokPrehravani(60, 0.05, 0.0)] * 60
    assert okno._spust_ulohu("sekvence", dlouha, "dlouhý test")
    assert not okno._worker.isFinished()

    okno.close()
    assert okno.isVisible(), "okno musí zůstat viditelné při ukončování"
    assert okno._pozadavek_zavrit is True
    assert not any(t.isEnabled() for t in okno._tlacitka_tonu), \
        "ovládání musí být vypnuté"

    konec = time.monotonic() + 5
    while okno.isVisible() and time.monotonic() < konec:
        qapp.processEvents()
        time.sleep(0.01)
    assert not okno.isVisible(), "okno se musí zavřít po ukončení workeru"
    assert okno._muzu_zavrit is True
    # Vlákno je skutečně hotové, ne jen přerušené.
    assert okno._worker is None or (okno._worker.isFinished()
                                    and okno._worker.wait(1000))


def test_zavirani_bez_workeru(okno, qapp):
    assert okno.close() is not False
    zpracuj_udalosti(qapp, 0.05)
    assert not okno.isVisible()
    assert okno._muzu_zavrit is True


def test_limit_prekrocen_zruseni_a_pokracovani(okno, qapp, monkeypatch):
    """Limit vyprší → nabídka; „Zrušit ukončení“ → hra pozastavena;
    po doběhnutí workeru → „Pokračovat ve hře“ obnoví ovládání."""
    # Worker, který přerušení ignoruje (simulace zaseknutého přehrávání).
    monkeypatch.setattr(Prehravac, "prerus", lambda self: None)
    monkeypatch.setattr(gm, "LIMIT_UKONCENI_S", 0.25)

    hraj(okno, qapp)
    stav_pred = (list(okno.logika.sekvence), okno.logika.pokusy_zbyva,
                 okno.logika.pozice, okno.logika.stav,
                 okno.logika.spravce.celkem.dokoncena_kola,
                 okno.logika.spravce.celkem.spravne_tony,
                 okno.logika.spravce.celkem.chybne_tony)

    dlouha = [melodies.KrokPrehravani(60, 0.05, 0.0)] * 30   # ~1,5 s
    assert okno._spust_ulohu("sekvence", dlouha, "zaseknutý test")

    def zrus_zavreni():
        box = QApplication.activeModalWidget()
        if box is None:
            QTimer.singleShot(100, zrus_zavreni)
            return
        for tlacitko in box.buttons():
            if tlacitko.text() == "Zrušit ukončení":
                tlacitko.click()
                return

    QTimer.singleShot(150, zrus_zavreni)
    okno.close()

    # Čekat, až se dialog ukáže a worker doběhne.
    konec = time.monotonic() + 6
    while not okno._pozastavena and time.monotonic() < konec:
        qapp.processEvents()
        time.sleep(0.01)
    zpracuj_udalosti(qapp, 0.2)

    assert okno.isVisible(), "po zrušení ukončení okno zůstává otevřené"
    assert okno._pozadavek_zavrit is False
    assert okno._pozastavena is True
    assert okno._worker is None, "worker mezitím bezpečně doběhl"
    # Herní ovládání zůstává vypnuté, dokud hráč nepokračuje.
    assert not any(t.isEnabled() for t in okno._tlacitka_tonu)
    assert okno._t_pokracovat.isVisible()
    assert okno._t_pokracovat.isEnabled()

    # Stav hry se nesměl změnit.
    stav_po = (list(okno.logika.sekvence), okno.logika.pokusy_zbyva,
               okno.logika.pozice, okno.logika.stav,
               okno.logika.spravce.celkem.dokoncena_kola,
               okno.logika.spravce.celkem.spravne_tony,
               okno.logika.spravce.celkem.chybne_tony)
    assert stav_pred == stav_po

    # Pokračování obnoví ovládání a nic nepočítá.
    okno._t_pokracovat.click()
    zpracuj_udalosti(qapp, 0.1)
    assert okno._pozastavena is False
    assert all(t.isEnabled() for t in okno._tlacitka_tonu)
    assert (list(okno.logika.sekvence), okno.logika.pokusy_zbyva,
            okno.logika.pozice, okno.logika.stav) == \
           (stav_pred[0], stav_pred[1], stav_pred[2], stav_pred[3])


def test_po_zavreni_nezustane_bezi_worker(okno, qapp):
    hraj(okno, qapp)
    dlouha = [melodies.KrokPrehravani(60, 0.05, 0.0)] * 40
    okno._spust_ulohu("sekvence", dlouha, "test")
    okno.close()
    konec = time.monotonic() + 6
    while okno.isVisible() and time.monotonic() < konec:
        qapp.processEvents()
        time.sleep(0.01)
    assert not okno.isVisible()
    # Všechna vlákna tohoto okna jsou hotová; worker je buď smazaný,
    # nebo potvrzeně dokončený.
    if okno._worker is not None:
        assert okno._worker.isFinished()
        assert okno._worker.wait(1000) is True


def test_pozastaveni_bez_pokracovani_neblokuje_aplikaci(okno, qapp):
    """Bez stisku „Pokračovat“ hra zůstane pozastavená, aplikace žije."""
    import unittest.mock as mock

    def ignoruj_preruseni(self):
        pass

    with mock.patch.object(Prehravac, "prerus", ignoruj_preruseni), \
            mock.patch.object(gm, "LIMIT_UKONCENI_S", 0.2):
        hraj(okno, qapp)
        dlouha = [melodies.KrokPrehravani(60, 0.05, 0.0)] * 20

        def zrus_zavreni():
            box = QApplication.activeModalWidget()
            if box is None:
                QTimer.singleShot(100, zrus_zavreni)
                return
            for tlacitko in box.buttons():
                if tlacitko.text() == "Zrušit ukončení":
                    tlacitko.click()
                    return

        QTimer.singleShot(120, zrus_zavreni)
        okno._spust_ulohu("sekvence", dlouha, "test")
        okno.close()
        konec = time.monotonic() + 6
        while not okno._pozastavena and time.monotonic() < konec:
            qapp.processEvents()
            time.sleep(0.01)
    assert okno._pozastavena is True
    # Aplikace je stále otevřená a ovládatelná (jediné aktivní: pokračovat).
    assert okno.isVisible()
    assert okno._t_ukoncit.isEnabled(), "ukončení musí zůstat dostupné"
    assert not any(t.isEnabled() for t in okno._tlacitka_tonu)
    okno._t_pokracovat.click()
    zpracuj_udalosti(qapp, 0.1)
    assert okno._pozastavena is False
