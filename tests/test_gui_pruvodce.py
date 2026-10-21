"""Offscreen GUI testy — Průvodce rytmem a fanfárami.

Ověřuje hlavně:
- přístupnost dialogu (přístupné názvy, buddy popisky, žádné posuvníky,
  logické pořadí Tab),
- přepočet dob na sekundy a rytmické příklady,
- ochranu `VZOROVE_FANFARY` při úpravách i při otevření kopie v editoru
  a její uložení s novým ID,
- fokus: návrat po zavření editoru do průvodce (a po průvodci do správce
  i do editoru),
- přehrání bez blokování GUI, obnovu fokusu po ukázce a kooperativní
  zastavení při zavření průvodce,
- porovnání „před/po“ v jediném workeru.
"""

from __future__ import annotations

import dataclasses

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QSlider,
)

from tests.conftest import cekaj_na_worker, zpracuj_udalosti

import melodies
import pruvodce
from gui.melodie_dialog import SpravceMelodiDialog, UpravMelodiiDialog
from gui.pruvodce_dialog import PruvodceRytmuDialog
from game_logic import HerniLogika, NastaveniHry
from gui.main_window import HlavniOkno
from notify import Oznamovac
from sound import ZvukovyMotor
from stats import SpravceStatistik
import random


@pytest.fixture(autouse=True)
def prazdny_registr():
    melodies.VLASTNI_MELODIE.clear()
    yield
    melodies.VLASTNI_MELODIE.clear()


@pytest.fixture(params=[100])
def okno(qapp, request):
    """Hotové hlavní okno — shodné s testy test_gui_melodie."""
    interval = request.param
    nastaveni = NastaveniHry(interval_statistik=interval)
    logika = HerniLogika(
        nastaveni=nastaveni,
        spravce=SpravceStatistik(interval_cil=interval),
        rng=random.Random(20241018),
    )
    okno = HlavniOkno(logika, ZvukovyMotor(), Oznamovac(), nastaveni)
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


def mala_melodie() -> melodies.Melodie:
    """Rychlá dvoutónová melodii pro přehrávání v testech."""
    return melodies.Melodie(
        id="_pruvodce_test", nazev="Malá ukázka",
        druh=melodies.DRUH_VITEZNA,
        tony=(melodies.Ton("C4", 0.125), melodies.Ton("E4", 0.125)),
        tempo_bpm=240.0,
        mezertonova_pauza_s=0.02,
    )


def snimek_vzoru() -> dict:
    return {k: dataclasses.asdict(v)
            for k, v in melodies.VZOROVE_FANFARY.items()}


def retezec_klice(dialog: PruvodceRytmuDialog) -> list:
    """Projde focus chain a vypíše pořadí klíčových ovládacích prvků."""
    klicove = [
        dialog.tempo, dialog.delka, dialog.pauza, dialog.mezertonova,
        dialog.priklady, dialog.vzor, dialog.tony,
        dialog.ton_delka, dialog.ton_pauza, dialog.tlacitko_zmenit_ton,
        dialog.tlacitko_v_editoru, dialog.tlacitko_rytmus,
        dialog.tlacitko_odpocet, dialog.tlacitko_melodie,
        dialog.tlacitko_zastavit, dialog.tlacitko_zaznamenat,
        dialog.tlacitko_porovnat,
    ]
    start = dialog.tempo
    poradi = []
    aktualni = start
    for _ in range(400):
        aktualni = aktualni.nextInFocusChain()
        if aktualni is start:
            break
        if aktualni in klicove:
            poradi.append(klicove.index(aktualni))
    return poradi


# ==================================================================
# Přístupnost
# ==================================================================

def test_pruvodce_je_pristupny(qapp):
    d = PruvodceRytmuDialog()

    # Žádné posuvníky — jen pole se zadáním hodnoty z klávesnice.
    assert not d.findChildren(QSlider), "průvodce nesmí používat QSlider"

    # Přístupné názvy a popisy.
    for prvek, nazev in (
        (d.tempo, "Tempo"),
        (d.delka, "Délka tónu v dobách"),
        (d.pauza, "Pauza po tónu v dobách"),
        (d.mezertonova, "Mezertonová pauza"),
        (d.priklady, "Seznam rytmických příkladů"),
        (d.vzor, "Vybraný vzor"),
        (d.tony, "Tóny vybraného vzoru"),
        (d.ton_delka, "Délka vybraného tónu"),
        (d.ton_pauza, "Pauza po vybraném tónu"),
        (d.tlacitko_zmenit_ton, "Změnit vybraný tón"),
        (d.tlacitko_v_editoru, "Otevřít vzor v editoru"),
        (d.tlacitko_rytmus, "Přehrát jen rytmus"),
        (d.tlacitko_odpocet, "Přehrát rytmus s odpočítáním"),
        (d.tlacitko_melodie, "Přehrát melodii"),
        (d.tlacitko_zastavit, "Zastavit přehrávání"),
        (d.tlacitko_zaznamenat, "Zaznamenat současný stav"),
        (d.tlacitko_porovnat, "Porovnat rytmus před a po"),
        (d._stav, "Stav průvodce"),
        (d._prepoctet, "Přepočet délek na sekundy"),
        (d._popis_prikladu, "Popis vybraného příkladu"),
    ):
        assert prvek.accessibleName() == nazev, f"špatný název: {nazev}"
    for prvek in (d.tempo, d.delka, d.pauza, d.mezertonova,
                  d.ton_delka, d.ton_pauza, d.tlacitko_rytmus,
                  d.tlacitko_odpocet, d.tlacitko_melodie,
                  d.tlacitko_porovnat, d.tlacitko_v_editoru):
        assert prvek.accessibleDescription(), "prvek bez popisu"

    # Buddy popisky u vstupních polí.
    buddies = {id(l.buddy()): l.text() for l in d.findChildren(QLabel)
               if l.buddy() is not None}
    ocekavano = (
        (d.tempo, "Tempo (údery za minutu):"),
        (d.delka, "Délka tónu v dobách:"),
        (d.pauza, "Pauza po tónu v dobách:"),
        (d.mezertonova, "Mezertonová pauza (sekundy):"),
        (d.ton_delka, "Délka vybraného tónu v dobách:"),
        (d.ton_pauza, "Pauza po vybraném tónu v dobách:"),
        (d.vzor, "Vzor:"),
    )
    for prvek, text in ocekavano:
        assert buddies.get(id(prvek)) == text, f"bez buddy: {text}"

    # Vysvětlení a přepočet jsou hned vidět.
    assert any("BPM" in l.text() for l in d.findChildren(QLabel))
    assert "1 doba" in d._prepoctet.text()

    # Bez přehrávacích callbacků jsou tlačítka poslechu vypnutá.
    assert not d.tlacitko_rytmus.isEnabled()
    assert not d.tlacitko_odpocet.isEnabled()
    assert not d.tlacitko_melodie.isEnabled()
    assert not d.tlacitko_porovnat.isEnabled()
    assert not d.tlacitko_zastavit.isEnabled()

    # Odpočítání je vysvětleno jako zvukové údery, ne řeč.
    assert "raz, dva, tři, čtyři" in d.tlacitko_odpocet.accessibleDescription()
    popisky = [l.text() for l in d.findChildren(QLabel)]
    assert any("nahlas nevyslovuje" in t for t in popisky), \
        "viditelné vysvětlení odpočítání chybí"

    d.reject()


def test_pruvodce_s_prehravacem_povoluje_tlacitka(qapp):
    d = PruvodceRytmuDialog(
        prehravac_kroku=lambda *_a, **_k: True,
        zastav_ukazku=lambda: True,
    )
    assert d.tlacitko_rytmus.isEnabled()
    assert d.tlacitko_odpocet.isEnabled()
    assert d.tlacitko_melodie.isEnabled()
    assert d.tlacitko_porovnat.isEnabled()
    assert d.tlacitko_zastavit.isEnabled()
    d.reject()


def test_pruvodce_ma_logicky_tab(qapp):
    d = PruvodceRytmuDialog()
    poradi = retezec_klice(d)
    # Řetězec musí obsahovat všechny klíčové prvky kromě výchozího tempa
    # a v přesném pořadí Tab.
    assert poradi == list(range(1, 17)), f"pořadí Tab nesedí: {poradi}"
    d.reject()


# ==================================================================
# Přepočet a příklady
# ==================================================================

def test_prepocteny_text_reaguje_na_tempo(qapp):
    d = PruvodceRytmuDialog()
    d.tempo.setValue(120)
    assert "1 doba = 0.500 s" in d._prepoctet.text()
    d.tempo.setValue(100)
    assert "1 doba = 0.600 s" in d._prepoctet.text()
    d.delka.setValue(0.75)
    # 0,75 doby × 0,600 s = 0,450 s.
    assert "0.450 s" in d._prepoctet.text()
    d.reject()


def test_priklady_zobrazuji_popis_a_delku(qapp):
    d = PruvodceRytmuDialog()
    assert d.priklady.count() == 3
    d.priklady.setCurrentRow(2)
    popis = d._popis_prikladu.text()
    assert "3 + 3 + 2" in popis
    assert "Celková délka" in popis
    d.priklady.setCurrentRow(0)
    assert "0,60 sekundy" in d._popis_prikladu.text()
    d.reject()


# ==================================================================
# Ochrana vzorů při úpravách v průvodci
# ==================================================================

def test_uprava_v_pruvodci_nemeni_vzory(qapp):
    d = PruvodceRytmuDialog()
    pred = snimek_vzoru()
    prvni_id = d.vzor.itemData(0)
    zdroj = melodies.vzor(prvni_id)

    # Seznam tónů + doba přehrávání sedí s originálem.
    assert d.tony.count() == len(zdroj.tony)
    assert d.tempo.value() == round(zdroj.tempo_bpm)
    assert d._snimek is not zdroj
    assert d._snimek.tony == zdroj.tony

    # Úprava tónu jde jen do pracovní kopie.
    d.tony.setCurrentRow(0)
    d.ton_delka.setValue(3.0)
    d.tlacitko_zmenit_ton.click()
    prace = d._sesbiraj()
    assert prace is not None
    assert prace.tony[0].delka == 3.0
    assert prace.tony[1:] == zdroj.tony[1:]

    # Stav „před“ po úpravě zůstává původní (až do zaznamenání).
    assert d._snimek.tony == zdroj.tony

    # Zaznamenání současného stavu přepne „před“ na pracovní stav.
    d.tlacitko_zaznamenat.click()
    assert d._snimek.tony[0].delka == 3.0
    assert "Zaznamenán" in d._stav.text()

    # Změna vzoru obnoví „před“ na nově načtený vzor (reset).
    d.vzor.setCurrentIndex(1)
    druhy_id = d.vzor.itemData(1)
    druhy = melodies.vzor(druhy_id)
    assert d._snimek.id == druhy.id
    assert d._snimek.tony == druhy.tony
    assert d.tempo.value() == round(druhy.tempo_bpm)
    assert "Načten vzor" in d._stav.text()

    # Registr vzorů je beze změny (vč. dočasně uložených objektů).
    assert snimek_vzoru() == pred
    d.reject()


# ==================================================================
# Otevření vzoru v editoru — vždy nová kopie s novým ID
# ==================================================================

def test_pruvodce_otevri_vzor_v_editoru_a_ulozi_kopii(qapp):
    pred = snimek_vzoru()
    d = PruvodceRytmuDialog()
    vysledky: dict = {}

    def krok3():
        vysledky["fokus"] = qapp.focusWidget()
        vysledky["pruvodce_viditelny"] = d.isVisible()
        d.reject()

    def krok2():
        editor = QApplication.activeModalWidget()
        vysledky["editor"] = editor
        if not isinstance(editor, UpravMelodiiDialog):
            return
        vysledky["id"] = editor.id_melodie
        vysledky["nazev"] = editor.nazev.text()
        vysledky["tony"] = editor.tony_seznam.count()
        QTimer.singleShot(50, krok3)
        editor._ulozit()        # uloží kopii a zavře editor

    def krok1():
        QTimer.singleShot(100, krok2)
        d.tlacitko_v_editoru.click()    # vnořený exec editoru

    QTimer.singleShot(50, krok1)
    d.exec()

    # Editor dostal NOVÉ ID a název s „vlastní úprava“.
    id_kopie = vysledky.get("id")
    assert id_kopie and id_kopie.startswith(melodies.PREFIX_ID_VLASTNI)
    assert "vlastní úprava" in vysledky.get("nazev", "")
    assert vysledky.get("tony") == 6, "kopie musí mít tóny vzoru"

    # Uložení proběhlo — jen kopie, vzor v registru zůstal beze změny.
    assert id_kopie in melodies.VLASTNI_MELODIE
    for v in melodies.vzorove_fanfary():
        assert v.id not in melodies.VLASTNI_MELODIE
    assert snimek_vzoru() == pred

    # Návrat fokusu do průvodce po zavření editoru.
    fokus = vysledky.get("fokus")
    assert vysledky.get("pruvodce_viditelny") is True
    assert fokus is not None, "fokus se musí vrátit do průvodce"
    assert fokus is d or d.isAncestorOf(fokus), \
        f"fokus je na {fokus}, měl by být v průvodci"


# ==================================================================
# Návrat fokusu — průvodce spuštěný ze správce i z editoru
# ==================================================================

def test_pruvodce_ze_spravce_vrati_fokus(qapp):
    spravce = SpravceMelodiDialog()
    vysledky: dict = {}

    def krok3():
        vysledky["fokus"] = qapp.focusWidget()
        vysledky["spravce_viditelny"] = spravce.isVisible()
        spravce.reject()

    def krok2():
        dialog = QApplication.activeModalWidget()
        vysledky["pruvodce"] = dialog
        if isinstance(dialog, PruvodceRytmuDialog):
            QTimer.singleShot(50, krok3)
            dialog.reject()

    def krok1():
        vysledky["spravce"] = QApplication.activeModalWidget()
        QTimer.singleShot(100, krok2)
        spravce.tlacitko_pruvodce.click()

    QTimer.singleShot(50, krok1)
    spravce.exec()

    assert vysledky.get("spravce") is spravce, "správce musí být modální"
    assert isinstance(vysledky.get("pruvodce"), PruvodceRytmuDialog)
    assert vysledky.get("spravce_viditelny") is True, \
        "po zavření průvodce zůstane správce otevřený"
    fokus = vysledky.get("fokus")
    assert fokus is not None
    assert fokus is spravce.tlacitko_pruvodce or spravce.isAncestorOf(fokus), \
        f"fokus se musí vrátit do správce, je na {fokus}"


def test_pruvodce_z_editoru_vrati_fokus(qapp):
    draft = melodies.Melodie(
        id="_draft", nazev="Rozpracovaná", druh=melodies.DRUH_VITEZNA,
        tony=(melodies.Ton("C4", 1.0),), tempo_bpm=120.0)
    editor = UpravMelodiiDialog(draft, tonina="C")
    vysledky: dict = {}

    def krok3():
        vysledky["fokus"] = qapp.focusWidget()
        vysledky["editor_viditelny"] = editor.isVisible()
        editor.reject()

    def krok2():
        dialog = QApplication.activeModalWidget()
        vysledky["pruvodce"] = dialog
        if isinstance(dialog, PruvodceRytmuDialog):
            # Přinesená melodii z editoru je první položkou výběru.
            vysledky["polozek"] = dialog.vzor.count()
            vysledky["prvni_polozka"] = dialog.vzor.itemData(0)
            QTimer.singleShot(50, krok3)
            dialog.reject()

    def krok1():
        vysledky["editor"] = QApplication.activeModalWidget()
        QTimer.singleShot(100, krok2)
        editor.tlacitko_pruvodce.click()

    QTimer.singleShot(50, krok1)
    editor.exec()

    assert vysledky.get("editor") is editor
    assert isinstance(vysledky.get("pruvodce"), PruvodceRytmuDialog)
    assert vysledky.get("polozek") == 4, "3 vzory + melodie z editoru"
    assert vysledky.get("prvni_polozka") == "_editor"
    assert vysledky.get("editor_viditelny") is True, \
        "po zavření průvodce zůstane editor otevřený"
    fokus = vysledky.get("fokus")
    assert fokus is not None
    assert fokus is editor.tlacitko_pruvodce or editor.isAncestorOf(fokus), \
        f"fokus se musí vrátit do editoru, je na {fokus}"


# ==================================================================
# Přehrávání — bez blokování GUI, fokus, zastavení
# ==================================================================

def test_prehrani_rytmu_neblokuje_gui_a_vrati_fokus(okno, qapp):
    d = PruvodceRytmuDialog(
        okno,
        prehravac_kroku=okno.prehraj_kroky,
        zastav_ukazku=okno.zastav_ukazku,
        oznamovac=okno.oznamovac,
        melodie=mala_melodie(),
    )
    vysledky: dict = {}

    def kontrola():
        vysledky["fokus"] = qapp.focusWidget()
        vysledky["stav"] = d._stav.text()
        vysledky["viditelny"] = d.isVisible()
        d.reject()

    def cekam():
        if okno._worker is not None:
            QTimer.singleShot(50, cekam)
            return
        QTimer.singleShot(50, kontrola)

    def spust():
        d.tlacitko_rytmus.click()
        # Hned po kliknutí: worker už běží → obsluha se neblokovala.
        vysledky["bezi"] = (okno._worker is not None
                            and not okno._worker.isFinished())
        vysledky["stav_po_kliku"] = d._stav.text()
        QTimer.singleShot(50, cekam)

    QTimer.singleShot(50, spust)
    d.exec()

    assert vysledky.get("bezi") is True, "worker musí běžet po kliknutí"
    assert "Přehrávám" in vysledky.get("stav_po_kliku", "")
    assert okno._worker is None, "worker musel doběhnout"
    assert okno._typ_bezi is None
    assert okno._ukazka_po_dokonceni is None, \
        "po dokončení nesmí zůstat odložená reakce"
    assert vysledky.get("viditelny") is True, "průvodce zůstane otevřený"
    fokus = vysledky.get("fokus")
    assert fokus is not None
    assert fokus is d or d.isAncestorOf(fokus), \
        f"fokus se musí vrátit do průvodce, je na {fokus}"
    assert "skončilo" in vysledky.get("stav", "")


def test_zavreni_pruvodce_behen_prehravani_zastavi(okno, qapp):
    d = PruvodceRytmuDialog(
        okno,
        prehravac_kroku=okno.prehraj_kroky,
        zastav_ukazku=okno.zastav_ukazku,
        oznamovac=okno.oznamovac,
        melodie=mala_melodie(),
    )
    vysledky: dict = {}

    def zavri():
        vysledky["bezi_pred"] = okno._worker is not None and \
            not okno._worker.isFinished()
        d.reject()      # zavření = done() → kooperativní přerušení

    def spust():
        d.tlacitko_rytmus.click()
        QTimer.singleShot(100, zavri)

    QTimer.singleShot(50, spust)
    d.exec()

    assert vysledky.get("bezi_pred") is True, "před zavřením musí hrát"
    # Kooperativní ukončení bez zablokování hlavního vlákna
    # (dialog se zavřel, worker doběhne „přerušený“ sám).
    assert cekaj_na_worker(okno, qapp), "worker se musí ukončit sám"
    assert okno._worker is None
    zpracuj_udalosti(qapp, 0.2)
    assert okno._typ_bezi is None
    assert okno._ukazka_po_dokonceni is None
    assert okno.isVisible(), "hlavní okno musí zůstat v pořádku"


def test_porovnani_prehraje_obedva_rytmy_v_jednom_workeru(okno, qapp):
    spusteni: list[list] = []

    def zakryt_kroky(kroky, popis, **kwargs):
        spusteni.append(list(kroky))
        return okno.prehraj_kroky(kroky, popis, **kwargs)

    d = PruvodceRytmuDialog(
        okno,
        prehravac_kroku=zakryt_kroky,
        zastav_ukazku=okno.zastav_ukazku,
        oznamovac=okno.oznamovac,
        melodie=mala_melodie(),
    )
    vysledky: dict = {}

    def kontrola():
        vysledky["fokus"] = qapp.focusWidget()
        vysledky["stav"] = d._stav.text()
        d.reject()

    def cekam():
        if okno._worker is not None:
            QTimer.singleShot(50, cekam)
            return
        QTimer.singleShot(50, kontrola)

    def spust():
        d.tlacitko_zaznamenat.click()
        d.tony.setCurrentRow(0)
        d.ton_delka.setValue(2.0)
        d.tlacitko_zmenit_ton.click()
        d.tlacitko_porovnat.click()
        vysledky["bezi"] = (okno._worker is not None
                            and not okno._worker.isFinished())
        vysledky["delka_ulohy"] = (
            len(okno._worker._uloha.kroky) if okno._worker else 0)
        QTimer.singleShot(50, cekam)

    QTimer.singleShot(50, spust)
    d.exec()

    # Jediné spuštění = oba rytmy v jednom workeru (žádný souběh).
    assert len(spusteni) == 1, f"očekáváno jedno spuštění, je {len(spusteni)}"
    assert vysledky.get("bezi") is True
    # Dva kroky „před“ + dva kroky „po“ = 4 impulzy v jedné úloze.
    kroky = spusteni[0]
    assert len(kroky) == 4
    assert all(k.impuls for k in kroky)
    assert vysledky.get("delka_ulohy") == 4
    # Výrazná pauza mezi oběma rytmy.
    assert kroky[1].pauza_s >= pruvodce.PAUZA_MEZI_POROVNANIM_S

    assert okno._worker is None
    assert "skončilo" in vysledky.get("stav", "")
    fokus = vysledky.get("fokus")
    assert fokus is not None
    assert fokus is d or d.isAncestorOf(fokus)


def test_prehravani_nemeni_herni_logiku(okno, qapp):
    d = PruvodceRytmuDialog(
        okno,
        prehravac_kroku=okno.prehraj_kroky,
        zastav_ukazku=okno.zastav_ukazku,
        oznamovac=okno.oznamovac,
        melodie=mala_melodie(),
    )
    stav_pred = (okno.logika.popis_stavu(),
                 okno.logika.stav,
                 list(okno.logika.sekvence),
                 okno.logika.pozice,
                 okno.logika.pokusy_zbyva)

    vysledky: dict = {}

    def po():
        vysledky["stav_po"] = (
            okno.logika.popis_stavu(),
            okno.logika.stav,
            list(okno.logika.sekvence),
            okno.logika.pozice,
            okno.logika.pokusy_zbyva)
        d.reject()

    def cekam():
        if okno._worker is not None:
            QTimer.singleShot(50, cekam)
            return
        QTimer.singleShot(50, po)

    def spust():
        d.tlacitko_odpocet.click()
        QTimer.singleShot(50, cekam)

    QTimer.singleShot(50, spust)
    d.exec()

    assert vysledky.get("stav_po") == stav_pred, \
        "ukázka nesmí zasáhnout do herní logiky"
    assert okno._worker is None
