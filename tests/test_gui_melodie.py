"""Offscreen GUI testy — hlasový výstup, správce a editor vlastních melodií.

Ověřuje hlavně:
- přístupnost dialogů (názvy, popisy, buddy popisky),
- tvorbu a trvalé uložení vlastní melodie do souboru,
- že po dokončení zkušebního přehrávání (worker typu „ukazka“) zůstane
  editor otevřený a fokus uvnitř něj,
- že smazání právě vybrané melodie aktualizuje oba výběry, uložené
  hodnoty i interní reference (bez změny nesouvisejícího nastavení).
"""

from __future__ import annotations

import json
import random

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
)

from tests.conftest import cekaj_na_worker, zpracuj_udalosti

import melodies
import gui.melodie_dialog as gm
from game_logic import HerniLogika, NastaveniHry
from gui.main_window import HlavniOkno
from gui.melodie_dialog import SpravceMelodiDialog, UpravMelodiiDialog
from gui.settings_dialog import NastaveniDialog
from notify import NastaveniHlasu, Oznamovac
from sound import ZvukovyMotor
from stats import SpravceStatistik
import uloziste


@pytest.fixture(autouse=True)
def prazdny_registr():
    melodies.VLASTNI_MELODIE.clear()
    yield
    melodies.VLASTNI_MELODIE.clear()


@pytest.fixture(params=[100])
def okno(qapp, request):
    """Hotové hlavní okno — shodné s testy test_gui_offscreen."""
    interval = request.param
    nastaveni = NastaveniHry(interval_statistik=interval)
    logika = HerniLogika(
        nastaveni=nastaveni,
        spravce=SpravceStatistik(interval_cil=interval),
        rng=random.Random(20241018),
    )
    okno = HlavniOkno(logika, ZvukovyMotor(), Oznamovac(), nastaveni)
    # Testy nesmí vyžadovat hlasové zařízení — řeč odpojíme.
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


class FakeOznamovac:
    """Atrapa oznamovacího modulu pro dialog (bez reálné řeči)."""

    def __init__(self):
        self.zavolani: list[str] = []

    @property
    def popis_dostupnosti(self) -> str:
        return "Potvrzena aktivní čtečka obrazovky: NVDA."

    def zkusebni_hlaseni(self, text: str = "") -> bool:
        self.zavolani.append(text or "zkuska")
        return True

    def oznam(self, text: str, hlasite: bool = True) -> bool:
        self.zavolani.append(text)
        return True


def vlastni_melodie(id_melodie, nazev="Testovací",
                    druh=melodies.DRUH_SMUTNA):
    m = melodies.Melodie(
        id=id_melodie, nazev=nazev, druh=druh,
        tony=(melodies.Ton("C4", 1.0, 0.0),),
    )
    melodies.uloz_vlastni_melodie(m)
    return m


# ==================================================================
# Dialog nastavení — sekce hlasového výstupu a správce melodií
# ==================================================================

def test_dialog_nastaveni_ma_sekci_hlasu(qapp):
    dialog = NastaveniDialog(NastaveniHry())

    assert dialog.rezim_hlasu.count() == 3
    assert dialog.rezim_hlasu.currentData() == "vcetne_systemu"
    assert dialog.rezim_hlasu.accessibleName() == "Režim hlasového výstupu"
    popis = dialog.rezim_hlasu.accessibleDescription()
    assert "čtečkou obrazovky" in popis and "systémový hlas" in popis

    buddies = {id(l.buddy()): l.text() for l in dialog.findChildren(QLabel)
               if l.buddy() is not None}
    assert buddies.get(id(dialog.rezim_hlasu)) == "Režim:"

    assert dialog.stav_hlasu.accessibleName() == "Stav hlasového výstupu"
    assert dialog.stav_hlasu.text(), "stav musí být hned vidět"
    assert dialog.tlacitko_zjistit.accessibleName() == "Zjistit stav hlasu"
    assert dialog.tlacitko_zkusit.accessibleName() == "Zkušební hláška"

    dialog.rezim_hlasu.setCurrentIndex(
        dialog.rezim_hlasu.findData("jen_odecitas"))
    assert dialog.hodnoty_hlasu().rezim == "jen_odecitas"
    dialog.rezim_hlasu.setCurrentIndex(dialog.rezim_hlasu.findData("vypnuto"))
    assert dialog.hodnoty_hlasu().rezim == "vypnuto"


def test_dialog_nastaveni_s_oznamovacem_nabizi_stav_a_zkousku(qapp):
    fake = FakeOznamovac()
    dialog = NastaveniDialog(NastaveniHry(), oznamovac=fake)
    assert dialog.tlacitko_zjistit.isEnabled()

    dialog.tlacitko_zjistit.click()
    assert "NVDA" in dialog.stav_hlasu.text()

    dialog.tlacitko_zkusit.click()
    assert fake.zavolani == ["zkuska"]
    assert "předána" in dialog.stav_hlasu.text()
    # Zkušební hláška nesmí měnit herní stav — jen ten stavový text.
    assert "NVDA" in dialog.stav_hlasu.text()


def test_dialog_nastaveni_ma_tlacitko_spravce_melodii(qapp):
    dialog = NastaveniDialog(NastaveniHry())
    assert dialog.tlacitko_spravce.accessibleName() == \
        "Spravovat vlastní melodie"
    assert dialog.tlacitko_spravce.accessibleDescription()
    # Kombinace naplněné přednastavenými melodiemi.
    assert dialog.smutna.count() == len(melodies.ZAKLADNI_SMUTNE)
    assert dialog.vitezna.count() == len(melodies.ZAKLADNI_VITEZNE)


def test_dialog_nastaveni_zobrazuje_vlastni_melodie(qapp):
    vlastni_melodie("vlastni_v", "Moje vítězná",
                    druh=melodies.DRUH_VITEZNA)
    dialog = NastaveniDialog(NastaveniHry())
    popisky = [dialog.vitezna.itemText(i)
               for i in range(dialog.vitezna.count())]
    assert any(p.endswith("(vlastní)") for p in popisky), popisky
    dialog.vitezna.setCurrentIndex(dialog.vitezna.findData("vlastni_v"))
    assert dialog.hodnoty()["id_vitezne_melodie"] == "vlastni_v"


# ==================================================================
# Správce a editor — přístupnost a CRUD
# ==================================================================

def test_spravce_melodi_je_pristupny(qapp):
    d = SpravceMelodiDialog()
    assert d.seznam.accessibleName() == "Seznam vlastních melodií"
    assert d.seznam.accessibleDescription()
    for tlacitko, nazev in (
        (d.tlacitko_nova, "Nová melodie"),
        (d.tlacitko_upravit, "Upravit vybranou melodii"),
        (d.tlacitko_smazat, "Smazat vybranou melodii"),
    ):
        assert tlacitko.accessibleName() == nazev
        assert tlacitko.accessibleDescription()
    assert d._pocet.text().startswith("Počet vlastních melodií: 0")
    # Bez výběru (prázdný seznam) nejdou upravovat ani mazat.
    assert not d.tlacitko_upravit.isEnabled()
    assert not d.tlacitko_smazat.isEnabled()


def test_spravce_melodi_zobrazuje_vytvorenou_polozku(qapp):
    vlastni_melodie("vlastni_sez", "V seznamu")
    d = SpravceMelodiDialog()
    assert d.seznam.count() == 1
    assert "V seznamu" in d.seznam.item(0).text()
    assert d.seznam.item(0).data(Qt.ItemDataRole.UserRole) == "vlastni_sez"
    assert d.tlacitko_upravit.isEnabled()
    assert d._pocet.text() == "Počet vlastních melodií: 1."


def test_editor_melodie_ma_buddy_a_popisky(qapp):
    d = UpravMelodiiDialog(None)
    buddies = {id(l.buddy()): l.text() for l in d.findChildren(QLabel)
               if l.buddy() is not None}
    ocekavano = (
        (d.nazev, "Název:"),
        (d.druh, "Druh:"),
        (d.tempo, "Tempo (údery za minutu):"),
        (d.pauza, "Mezertonová pauza (sekundy):"),
        (d.ton_nazev, "Tón:"),
        (d.ton_delka, "Délka v taktech:"),
        (d.ton_pauza, "Pauza po tónu v taktech:"),
        (d.tonina_ukazky, "Tónina ukázky:"),
    )
    for prvek, text in ocekavano:
        assert prvek.accessibleName(), "pole bez přístupného názvu"
        assert buddies.get(id(prvek)) == text, f"bez buddy: {text}"
    assert d.tony_seznam.accessibleName() == "Seznam tónů melodie"
    assert d.tlacitko_pridat.accessibleName() == "Přidat tón"
    assert d._stav.accessibleName() == "Stav úpravy melodie"

    # Enter v polích nesmí náhodně uložit celou melodii.
    box = d.findChild(QDialogButtonBox)
    ulozit = box.button(QDialogButtonBox.StandardButton.Save)
    assert ulozit.isDefault() is False


def test_vytvoreni_melodie_se_ulozi_do_souboru(qapp):
    d = UpravMelodiiDialog(None)
    d.nazev.setText("Moje první")
    d.druh.setCurrentIndex(d.druh.findData(melodies.DRUH_VITEZNA))
    d.tempo.setValue(132)
    d.ton_nazev.setText("C4")
    d.tlacitko_pridat.click()
    d.ton_nazev.setText("G4")
    d.tlacitko_pridat.click()
    assert d.tony_seznam.count() == 2

    d._ulozit()
    assert d.result() == int(QDialog.DialogCode.Accepted)

    # V registru (paměť).
    id_m = d.id_melodie
    ulozena = melodies.VLASTNI_MELODIE.get(id_m)
    assert ulozena is not None
    assert ulozena.nazev == "Moje první"
    assert ulozena.druh == melodies.DRUH_VITEZNA
    assert ulozena.tempo_bpm == 132.0
    assert [t.nazev for t in ulozena.tony] == ["C4", "G4"]

    # Reálný soubor.
    cesta = uloziste.cesta_k_melodiim()
    assert cesta.exists(), "melodie se musí zapsat na disk"
    data = json.loads(cesta.read_text(encoding="utf-8"))
    assert any(z["id"] == id_m and z["nazev"] == "Moje první" for z in data)

    # A hned je k dispozici ve výběru.
    assert id_m in dict(melodies.nabidka_melodii(melodies.DRUH_VITEZNA))


def test_editor_odmita_melodii_bez_tonu(qapp):
    d = UpravMelodiiDialog(None)
    d.nazev.setText("Prázdná")
    d._ulozit()
    assert d.result() != int(QDialog.DialogCode.Accepted)
    assert "nelze uložit" in d._stav.text()
    assert "tóny" in d._stav.text()
    assert melodies.VLASTNI_MELODIE == {}
    # Soubor se nesmí změnit na základě neplatných dat.
    cesta = uloziste.cesta_k_melodiim()
    predchozi = cesta.read_text(encoding="utf-8") if cesta.exists() else None
    d._ulozit()
    dalsi = cesta.read_text(encoding="utf-8") if cesta.exists() else None
    assert predchozi == dalsi


def test_editor_odmita_neplatny_nazev_tonu(qapp):
    d = UpravMelodiiDialog(None)
    d.ton_nazev.setText("X9")
    d.tlacitko_pridat.click()
    assert d.tony_seznam.count() == 0
    assert "Neplatný" in d._stav.text()
    d.ton_nazev.setText("Fis4")
    d.tlacitko_pridat.click()
    assert d.tony_seznam.count() == 1, "platný tón musí projít"


def test_editor_upravuje_existujici_melodii(qapp):
    m = vlastni_melodie("vlastni_u", "Původní")
    d = UpravMelodiiDialog(m)
    assert d.nazev.text() == "Původní"
    assert d.id_melodie == "vlastni_u"
    assert d.tony_seznam.count() == 1

    d.tony_seznam.setCurrentRow(0)      # vybrat tón pro úpravu
    d.nazev.setText("Přejmenovaná")
    d.ton_nazev.setText("D4")
    d._nahrad_ton()
    d._ulozit()
    assert d.result() == int(QDialog.DialogCode.Accepted)
    ulozena = melodies.VLASTNI_MELODIE["vlastni_u"]
    assert ulozena.nazev == "Přejmenovaná"
    assert ulozena.tony[0].nazev == "D4"


def test_smazani_melodie_pres_spravce(qapp, monkeypatch):
    monkeypatch.setattr(gm, "QMessageBox", _FakeMessageBox())
    vlastni_melodie("vlastni_s", "Ke smazání")
    uloziste.uloz_vlastni_melodie()

    d = SpravceMelodiDialog()
    d.seznam.setCurrentRow(0)
    d._smaz_vybranou()
    assert "vlastni_s" not in melodies.VLASTNI_MELODIE
    assert d.seznam.count() == 0
    data = json.loads(uloziste.cesta_k_melodiim().read_text("utf-8"))
    assert all(z["id"] != "vlastni_s" for z in data)


# ==================================================================
# Zkušební přehrávání — fokus musí zůstat v editoru
# ==================================================================

def test_dokonceni_ukazky_zustava_v_editoru(okno, qapp):
    m = melodies.Melodie(
        id="vlastni_ukazka", nazev="Ukázková", druh=melodies.DRUH_SMUTNA,
        tony=(melodies.Ton("C4", 0.125, 0.0),), tempo_bpm=240.0)
    melodies.uloz_vlastni_melodie(m)

    editor = UpravMelodiiDialog(m, okno, tonina="C",
                                prehravac=okno.prehraj_ukazku,
                                oznamovac=okno.oznamovac)
    vysledky: dict = {}

    def kontrola():
        vysledky["editor_viditelny"] = editor.isVisible()
        vysledky["fokus"] = qapp.focusWidget()
        vysledky["worker"] = okno._worker
        editor.reject()

    def cekam_na_worker():
        if okno._worker is not None:
            QTimer.singleShot(50, cekam_na_worker)
            return
        QTimer.singleShot(50, kontrola)

    def spust():
        vysledky["spusteno"] = okno.prehraj_ukazku(m, "C")
        QTimer.singleShot(50, cekam_na_worker)

    QTimer.singleShot(50, spust)
    editor.exec()

    assert vysledky.get("spusteno") is True, "ukázka se měla spustit"
    assert vysledky.get("worker") is None, "worker musel doběhnout"
    assert vysledky.get("editor_viditelny") is True, \
        "editor zůstane po ukázce otevřený"
    fokus = vysledky.get("fokus")
    assert fokus is not None, "po ukázce musí být něco zaměřené"
    assert fokus is editor or editor.isAncestorOf(fokus), \
        f"fokus musí zůstat v editoru, je na {fokus}"


def test_spusteni_ukazky_bez_editoru_nemeni_fokus_hry(okno, qapp):
    """Mimo dialog se chová jako dřív — fokus se neztratí."""
    m = melodies.Melodie(
        id="vlastni_bez_editoru", nazev="Bez editoru",
        druh=melodies.DRUH_SMUTNA,
        tony=(melodies.Ton("C4", 0.125, 0.0),), tempo_bpm=240.0)
    melodies.uloz_vlastni_melodie(m)
    okno._t_nova.setFocus()
    zpracuj_udalosti(qapp, 0.05)

    assert okno.prehraj_ukazku(m, "C") is True
    assert cekaj_na_worker(okno, qapp)
    zpracuj_udalosti(qapp, 0.1)
    fokus = qapp.focusWidget()
    assert fokus is not None


# ==================================================================
# Smazání právě vybrané melodie — oba výběry, uložení, interní reference
# ==================================================================

def test_smazani_vybrane_melodie_aktualizuje_vse(okno, qapp, monkeypatch):
    monkeypatch.setattr(gm, "QMessageBox", _FakeMessageBox())
    vlastni_melodie("vlastni_k_smazani", "Ke smazání")
    uloziste.uloz_vlastni_melodie()

    # Vybraná smutná melodie + nestandardní související nastavení.
    okno.nastaveni = NastaveniHry(
        **{**okno.nastaveni.__dict__,
           "id_smutne_melodie": "vlastni_k_smazani",
           "delka_sekvence": 5})
    uloziste.uloz_nastaveni(okno.nastaveni)
    okno.logika.zmenit_nastaveni(**okno.nastaveni.__dict__)

    vysledky: dict = {}

    def krok1():
        dialog = QApplication.activeModalWidget()
        vysledky["dialog"] = dialog
        if dialog is None:
            return
        vysledky["smutna_pred"] = dialog.smutna.currentData()
        vysledky["vitezna_pred"] = dialog.vitezna.currentData()
        dialog.tlacitko_spravce.click()

    def krok2():
        spravce = QApplication.activeModalWidget()
        vysledky["spravce"] = spravce
        if spravce is None:
            return
        for i in range(spravce.seznam.count()):
            if spravce.seznam.item(i).data(Qt.ItemDataRole.UserRole) == \
                    "vlastni_k_smazani":
                spravce.seznam.setCurrentRow(i)
        vysledky["vybrano"] = spravce._vybrana_id()
        spravce._smaz_vybranou()

    def krok3():
        spravce = QApplication.activeModalWidget()
        vysledky["smazano"] = "vlastni_k_smazani" not in \
            melodies.VLASTNI_MELODIE
        vysledky["seznam_po"] = spravce.seznam.count() \
            if spravce is not None else None
        if spravce is not None:
            spravce.reject()

    def krok4():
        dialog = QApplication.activeModalWidget()
        vysledky["dialog_po"] = dialog
        if dialog is None:
            return
        vysledky["smutna_po"] = dialog.smutna.currentData()
        vysledky["vitezna_po"] = dialog.vitezna.currentData()
        dialog.reject()

    QTimer.singleShot(50, krok1)
    QTimer.singleShot(300, krok2)
    QTimer.singleShot(600, krok3)
    QTimer.singleShot(900, krok4)
    okno._otevri_nastaveni()

    # Dialog správce se opravdu otevřel a melodie se v něm našla.
    assert isinstance(vysledky.get("dialog"), NastaveniDialog)
    assert isinstance(vysledky.get("spravce"), SpravceMelodiDialog)
    assert vysledky.get("smutna_pred") == "vlastni_k_smazani"
    assert vysledky.get("vybrano") == "vlastni_k_smazani"
    assert vysledky.get("smazano") is True
    assert vysledky.get("seznam_po") == 0

    # Oba výběry v dialogu po zavření správce.
    assert vysledky.get("smutna_po") == \
        melodies.VYCHOZI_ID[melodies.DRUH_SMUTNA]
    assert vysledky.get("vitezna_po") == vysledky.get("vitezna_pred"), \
        "vítězná melodie se nesmí změnit"

    # Interní reference (okno + logika) i uložená hodnota.
    vychozi_smutna = melodies.VYCHOZI_ID[melodies.DRUH_SMUTNA]
    assert okno.nastaveni.id_smutne_melodie == vychozi_smutna
    assert okno.logika.nastaveni.id_smutne_melodie == vychozi_smutna
    nacteno = uloziste.nacti_nastaveni()
    assert nacteno.id_smutne_melodie == vychozi_smutna

    # Nesouvisející nastavení zůstalo beze změny.
    assert okno.nastaveni.delka_sekvence == 5
    assert nacteno.delka_sekvence == 5
    assert nacteno.interval_statistik == 100
    assert okno.logika.nastaveni.delka_sekvence == 5
    assert okno.logika.nastaveni.interval_statistik == 100

    # Soubor už melodie neobsahuje a hra na ni nespadne.
    text = uloziste.cesta_k_melodiim().read_text(encoding="utf-8")
    assert "vlastni_k_smazani" not in text
    volba = melodies.ziskej_melodii(okno.nastaveni.tonina,
                                    melodies.DRUH_SMUTNA,
                                    okno.nastaveni.id_smutne_melodie)
    assert volba.zdroj != "vlastni"
    assert volba.varovani is None, f"očekáván výchozí stav: {volba.varovani}"


# ==================================================================
# Nastavení hlasu v hlavním okně
# ==================================================================

def test_hlasovy_rezim_z_nastaveni_se_propise(okno, qapp):
    okno._pouzij_nastaveni_hlasu(NastaveniHlasu(rezim="vypnuto"))
    assert okno.oznamovac.rezim == "vypnuto"
    assert "vypnutý" in okno.oznamovac.popis_dostupnosti

    # Textová oznámení ve stavovém panelu zůstávají i bez hlasu.
    okno._oznam("Panel zůstává plnohodnotný")
    assert okno.panel.text == "Panel zůstává plnohodnotný"

    # Režim se uložil trvale.
    assert uloziste.nacti_nastaveni_hlasu().rezim == "vypnuto"

    okno._pouzij_nastaveni_hlasu(NastaveniHlasu(rezim="jen_odecitas"))
    assert okno.oznamovac.rezim == "jen_odecitas"
    # Bez potvrzené čtečky (ve fixtuře je odpojený výstup) nehlasitě nemluví.
    assert okno.oznamovac.hlas_dostupny is False
    okno._oznam("Text jde do panelu")
    assert okno.panel.text == "Text jde do panelu"


def test_dialog_nastaveni_vraci_hlas_i_melodie(qapp):
    dialog = NastaveniDialog(NastaveniHry())
    dialog.rezim_hlasu.setCurrentIndex(dialog.rezim_hlasu.findData("vypnuto"))
    dialog.delka.setValue(7)
    hodnoty = dialog.hodnoty()
    hlas = dialog.hodnoty_hlasu()
    assert hodnoty["delka_sekvence"] == 7
    assert hlas.rezim == "vypnuto"
    hlas.over()          # validace projde


class _FakeMessageBox:
    """Atrapa QMessageBox — potvrzení mazání bez modálního okna."""

    StandardButton = QMessageBox.StandardButton

    @staticmethod
    def question(*_args, **_kwargs):
        return _FakeMessageBox.StandardButton.Yes
