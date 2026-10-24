"""Hlavní okno Hudebního pamatováku (PyQt6, česky, přístupné).

Rozhraní je plně ovladatelné klávesnicí:
- Tab / Shift+Tab — pořadí prvků,
- 1–7 — zadání tónů (jen ve herním kontextu, viz ``_kontext_klavesy_povolen``),
- F2 nová hra, F5 přehrát sekvenci znovu, F6 zopakovat hlášení,
  F7 pokračovat ve hře.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import melodies
import theory
from game_logic import HerniLogika, NastaveniHry, StavKola
from gui.settings_dialog import NastaveniDialog
from gui.stats_dialog import StatsDialog
from notify import NastaveniHlasu, Oznamovac
from player_worker import Prehravac, Uloha
from sound import ZvukovyMotor
from melodies import KrokPrehravani
from stats import VysledekIntervalu
import uloziste

# Délka čekání na bezpečné ukončení workeru při zavírání aplikace (s).
LIMIT_UKONCENI_S = 3.0
# Perioda kontroly ukončení (ms) — neblokující, přes signály a timer.
INTERVAL_KONTROLY_MS = 100

# Délky zvuku.
DELKA_TONU_S = 0.45           # zpětná vazba při stisku tlačítka tónu
DELKA_TONU_SEKVENCE_S = 0.55  # tón v přehrávané sekvenci
PAUZA_V_SEKVENCE_S = 0.18


class StavovyPanel(QFrame):
    """Zaměřitelný panel s posledním hlášením a tlačítkem „Zopakovat“.

    Při fokusu odečítač přečte ``accessibleName``, který vždy obsahuje
    aktuální text hlášení — informace tedy nezmizí ani při selhání
    hlasového výstupu.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAccessibleName("Poslední hlášení")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)

        self._label = QLabel("", self)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label.setAccessibleName("Text posledního hlášení")
        lay.addWidget(self._label, stretch=1)

        self.tlacitko_zopakovat = QPushButton("Zopakovat poslední hlášení (F6)", self)
        self.tlacitko_zopakovat.setAccessibleName("Zopakovat poslední hlášení")
        self.tlacitko_zopakovat.setAccessibleDescription(
            "Zopakuje naposledy vyhlášený text hlasitě.")
        lay.addWidget(self.tlacitko_zopakovat)

    def aktualizuj_hlaseni(self, text: str) -> None:
        self._label.setText(text)
        # Odečítač při fokusu panelu přečte samotný obsah hlášení.
        self.setAccessibleName(f"Poslední hlášení: {text}")

    @property
    def text(self) -> str:
        return self._label.text()


class HlavniOkno(QMainWindow):
    """Hlavní okno hry."""

    def __init__(
        self,
        logika: HerniLogika,
        motor: ZvukovyMotor,
        oznamovac: Oznamovac,
        nastaveni: NastaveniHry | None = None,
        nastaveni_hlasu: NastaveniHlasu | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.logika = logika
        self.motor = motor
        self.oznamovac = oznamovac
        self.nastaveni = nastaveni or logika.nastaveni
        self.nastaveni_hlasu = nastaveni_hlasu or NastaveniHlasu()
        # Režim hlasu z nastavení (vypnuto / jen s čtečkou / i bez čtečky).
        self.oznamovac.nastav_rezim(self.nastaveni_hlasu.rezim)

        # Stav workeru a zavírání.
        self._worker: Prehravac | None = None
        self._typ_bezi: str | None = None      # typ právě běžící úlohy
        # Volitelná reakce průvodce/na dokončení zkušební ukázky.
        self._ukazka_po_dokonceni = None
        self._vysledek_ulohy: tuple[str, bool] | None = None
        self._fokus_po_prehrani: str | None = None
        self._fokus_pred: QWidget | None = None
        self._ceka_dialog: VysledekIntervalu | None = None
        self._pozadavek_zavrit = False
        self._cekam_na_ukonceni = False
        self._pozastavena = False
        self._muzu_zavrit = False
        self._ukoncuje_se = False
        self._nabidka_zobrazena = False
        self._dokoncit_zavreni = False
        self._zaviraci_timer: QTimer | None = None
        self._zaviraci_cas = 0.0

        self._postav_gui()
        self.oznamovac.nastav_panel(self.panel)
        self._aktualizuj_tlacitka_tonu()
        self._aktualizuj_info()
        self._aktualizovat_dostupnost()
        self._nastav_zkratky()

        self.panel.tlacitko_zopakovat.clicked.connect(self._zopakuj_hlaseni)

    # ==================================================================
    # Sestavení GUI
    # ==================================================================

    def _postav_gui(self) -> None:
        self.setWindowTitle("Hudební pamatovák")
        self.setAccessibleDescription(
            "Hra s hudebními tóny: poslechněte si sekvenci a zopakujte ji.")
        central = QWidget(self)
        hlavni = QVBoxLayout(central)

        # Stavový panel (přístupná náhradní cesta pro oznámení).
        self.panel = StavovyPanel(central)
        hlavni.addWidget(self.panel)

        # Informace o průběhu.
        self._label_info = QLabel(central)
        self._label_info.setWordWrap(True)
        self._label_info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label_info.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._label_info.setAccessibleName("Průběh hry")
        hlavni.addWidget(self._label_info)

        # --- Skupina tónů ------------------------------------------------
        skupina_tony = QGroupBox("Tóny k zadání", central)
        skupina_tony.setAccessibleName(
            "Sedm tónů zvolené stupnice k zadání")
        mrez = QGridLayout(skupina_tony)
        self._tlacitka_tonu: list[QPushButton] = []
        for i in range(7):
            tlacitko = QPushButton(skupina_tony)
            tlacitko.clicked.connect(
                lambda _=False, idx=i: self._vstup_ton(idx))
            self._tlacitka_tonu.append(tlacitko)
            mrez.addWidget(tlacitko, 0, i)
        hlavni.addWidget(skupina_tony)

        # --- Skupina ovládání -------------------------------------------
        skupina_ovladani = QGroupBox("Ovládání hry", central)
        skupina_ovladani.setAccessibleName("Ovládání hry")
        lay_ovl = QVBoxLayout(skupina_ovladani)

        self._t_nova = QPushButton("Nová hra (F2)", skupina_ovladani)
        self._t_nova.setAccessibleName("Nová hra")
        self._t_nova.setAccessibleDescription(
            "Začne novou hru: nová sekvence, plný počet pokusů.")
        self._t_nova.clicked.connect(self._nova_hra)
        lay_ovl.addWidget(self._t_nova)

        self._t_znovu = QPushButton("Přehrát sekvenci znovu (F5)", skupina_ovladani)
        self._t_znovu.setAccessibleName("Přehrát sekvenci znovu")
        self._t_znovu.setAccessibleDescription(
            "Znovu přehraje stejnou sekvenci. Na skóre ani pokusy nemá vliv.")
        self._t_znovu.clicked.connect(self._prehraj_sekvenci_znovu)
        lay_ovl.addWidget(self._t_znovu)

        self._t_zopovat_kolo = QPushButton("Zopakovat aktuální kolo", skupina_ovladani)
        self._t_zopovat_kolo.setAccessibleName("Zopakovat aktuální kolo")
        self._t_zopovat_kolo.setAccessibleDescription(
            "Restartuje stejné kolo: stejná sekvence a plný počet pokusů. "
            "Statistiky se nemění.")
        self._t_zopovat_kolo.clicked.connect(self._zopovat_kolo)
        lay_ovl.addWidget(self._t_zopovat_kolo)

        self._t_nastaveni = QPushButton("Nastavení hry", skupina_ovladani)
        self._t_nastaveni.setAccessibleName("Nastavení hry")
        self._t_nastaveni.setAccessibleDescription(
            "Otevře nastavení tóniny, oktávy, pokusů, délky sekvence, "
            "intervalu statistik a melodií.")
        self._t_nastaveni.clicked.connect(self._otevri_nastaveni)
        lay_ovl.addWidget(self._t_nastaveni)

        self._t_stats = QPushButton("Statistiky", skupina_ovladani)
        self._t_stats.setAccessibleName("Statistiky")
        self._t_stats.setAccessibleDescription(
            "Otevře přehled statistik za aktuální interval a celkově.")
        self._t_stats.clicked.connect(self._otevri_stats)
        lay_ovl.addWidget(self._t_stats)

        self._t_pokracovat = QPushButton("Pokračovat ve hře (F7)", skupina_ovladani)
        self._t_pokracovat.setAccessibleName("Pokračovat ve hře")
        self._t_pokracovat.setAccessibleDescription(
            "Obnoví ovládání po ukončeném přehrávání. Sekvence, pokusy "
            "ani statistiky se tím nemění.")
        self._t_pokracovat.clicked.connect(self._pokracovat_ve_hre)
        self._t_pokracovat.setVisible(False)
        lay_ovl.addWidget(self._t_pokracovat)

        self._t_ukoncit = QPushButton("Ukončit aplikaci", skupina_ovladani)
        self._t_ukoncit.setAccessibleName("Ukončit aplikaci")
        self._t_ukoncit.setAccessibleDescription(
            "Bezpečně ukončí aplikaci, i když právě hraje melodie.")
        self._t_ukoncit.clicked.connect(self.close)
        lay_ovl.addWidget(self._t_ukoncit)

        hlavni.addWidget(skupina_ovladani)
        self.setCentralWidget(central)

        # Pořadí Tab: panel → info → tóny → ovládání.
        self.setTabOrder(self.panel, self._label_info)
        self.setTabOrder(self._label_info, self._tlacitka_tonu[0])
        for i in range(6):
            self.setTabOrder(self._tlacitka_tonu[i], self._tlacitka_tonu[i + 1])
        self.setTabOrder(self._tlacitka_tonu[6], self.panel.tlacitko_zopakovat)
        self.setTabOrder(self.panel.tlacitko_zopakovat, self._t_nova)
        self.setTabOrder(self._t_nova, self._t_znovu)
        self.setTabOrder(self._t_znovu, self._t_zopovat_kolo)
        self.setTabOrder(self._t_zopovat_kolo, self._t_nastaveni)
        self.setTabOrder(self._t_nastaveni, self._t_stats)
        self.setTabOrder(self._t_stats, self._t_pokracovat)
        self.setTabOrder(self._t_pokracovat, self._t_ukoncit)

        self.resize(760, 520)

    # ==================================================================
    # Klávesové zkratky (kontextové)
    # ==================================================================

    def _nastav_zkratky(self) -> None:
        self._zkratky: list[QShortcut] = []
        for cislo in range(1, 8):
            zkratka = QShortcut(QKeySequence(str(cislo)), self)
            zkratka.setContext(Qt.ShortcutContext.ApplicationShortcut)
            zkratka.activated.connect(
                lambda idx=cislo - 1: self._klavesa_ton(idx))
            self._zkratky.append(zkratka)

        def pridat(popis, klavesa, funkce):
            zkratka = QShortcut(QKeySequence(klavesa), self)
            zkratka.setContext(Qt.ShortcutContext.ApplicationShortcut)
            zkratka.activated.connect(funkce)
            self._zkratky.append(zkratka)
            return zkratka

        pridat("nová hra", "F2", self._nova_hra)
        pridat("přehrát znovu", "F5", self._prehraj_sekvenci_znovu)
        pridat("zopakovat hlášení", "F6", self._zopakuj_hlaseni)
        pridat("pokračovat ve hře", "F7", self._pokracovat_ve_hre)
        pridat("vývojářský režim", "Ctrl+Alt+D", self._prepinac_vyvojarskeho_rezimu)

    def _prepinac_vyvojarskeho_rezimu(self) -> None:
        if QApplication.activeModalWidget() is not None:
            return
        if self.nastaveni.vyvojarsky_rezim:
            self.nastaveni.vyvojarsky_rezim = False
            self.logika.zmenit_nastaveni(vyvojarsky_rezim=False)
            self._aktualizuj_info()
            self._oznam("Vývojářský režim byl uzamčen.")
        else:
            heslo, ok = QInputDialog.getText(
                self, "Vývojářský režim", "Zadejte heslo pro vývojářský režim:",
                QLineEdit.EchoMode.Password
            )
            if ok:
                if heslo == "hudba":
                    self.nastaveni.vyvojarsky_rezim = True
                    self.logika.zmenit_nastaveni(vyvojarsky_rezim=True)
                    self._aktualizuj_info()
                    self._oznam("Vývojářský režim úspěšně odemčen.")
                else:
                    self._oznam("Nesprávné heslo. Vývojářský režim zůstává uzamčen.")

    def _kontext_klavesy_povolen(self) -> bool:
        """Klávesy 1–7 jen ve hře: není modální dialog a fokus není v poli."""
        if QApplication.activeModalWidget() is not None:
            return False
        fw = QApplication.focusWidget()
        if fw is None:
            return True
        if isinstance(fw, (QLineEdit, QAbstractSpinBox)):
            return False
        if isinstance(fw, QComboBox) and fw.isEditable():
            return False
        return True

    def _klavesa_ton(self, stupen: int) -> None:
        if not self._kontext_klavesy_povolen():
            return
        tlacitko = self._tlacitka_tonu[stupen]
        if tlacitko.isEnabled():
            tlacitko.click()

    # ==================================================================
    # Oznámení a informace
    # ==================================================================

    def _oznam(self, text: str, hlasite: bool = True) -> None:
        self.oznamovac.oznam(text, hlasite=hlasite)

    def _zopakuj_hlaseni(self) -> None:
        if not self.oznamovac.posledni_text:
            self._oznam("Zatím žádné hlášení.", hlasite=True)
            return
        self.oznamovac.zopakuj()

    def _aktualizuj_info(self) -> None:
        n = self.nastaveni
        radky = [
            f"Tónina: {theory_popis_toniny(n.tonina)}, "
            f"oktáva {n.oktava}, délka sekvence {n.delka_sekvence}, "
            f"pokusy {n.pocet_pokusu}.",
            self.logika.popis_stavu(),
        ]
        if n.vyvojarsky_rezim and self.logika.sekvence:
            prehled = self.logika.vyvojarsky_prehled_sekvence()
            if prehled:
                radky.append(f"[Vývojářský přehled: {' → '.join(prehled)}]")
        if self.motor.tichy_rezim:
            radky.append(self.motor.popis_rezimu())
        self._label_info.setText("\n".join(radky))

    # ==================================================================
    # Tlačítka tónů
    # ==================================================================

    def _aktualizuj_tlacitka_tonu(self) -> None:
        """Názvy a výšky tlačítek podle aktuální tóniny a oktávy."""
        for stupen, (nazev, midi) in enumerate(self.logika.tlacitka()):
            tlacitko = self._tlacitka_tonu[stupen]
            tlacitko.setText(nazev)
            tlacitko.setAccessibleName(nazev)
            tlacitko.setAccessibleDescription(
                f"{stupen + 1}. stupeň stupnice, zvuková výška MIDI {midi}. "
                f"Klávesa {stupen + 1}.")

    def _aktualizovat_dostupnost(self) -> None:
        """Jediné místo, které řídí dostupnost ovládání."""
        worker_bezi = self._worker is not None and not self._worker.isFinished()
        blokovano = worker_bezi or self._ukoncuje_se or self._pozastavena
        hraje_se = (
            bool(self.logika.sekvence)
            and self.logika.stav is StavKola.HRAC_VSTUPUJE
        )
        for tlacitko in self._tlacitka_tonu:
            tlacitko.setEnabled(hraje_se and not blokovano)
        self._t_nova.setEnabled(not blokovano)
        self._t_znovu.setEnabled(not blokovano and bool(self.logika.sekvence))
        self._t_zopovat_kolo.setEnabled(
            not blokovano
            and bool(self.logika.sekvence)
            and self.logika.stav is not StavKola.CEKA_NA_PREHRANI
        )
        self._t_nastaveni.setEnabled(not blokovano)
        self._t_stats.setEnabled(not blokovano)
        self._t_ukoncit.setEnabled(not self._ukoncuje_se)
        self._t_pokracovat.setVisible(self._pozastavena)
        self._t_pokracovat.setEnabled(self._pozastavena and not worker_bezi)

    # ==================================================================
    # Spouštění přehrávání (vždy jen jeden worker současně)
    # ==================================================================

    def _spust_ulohu(
        self,
        typ: str,
        kroky: list[KrokPrehravani],
        popis: str,
        fokus_po: str | None = "zachovat",
    ) -> bool:
        """Spustí přehrávání v workeru. False = odmítnuto (worker běží)."""
        if self._worker is not None and not self._worker.isFinished():
            self._oznam("Čekám na ukončení probíhajícího přehrávání.")
            return False
        if self._pozastavena:
            self._oznam("Hra je pozastavena. Nejdřív pokračujte ve hře.")
            return False

        self._fokus_pred = QApplication.focusWidget()
        self._fokus_po_prehrani = fokus_po
        self._ukazka_po_dokonceni = None
        worker = Prehravac(self.motor, Uloha(typ, tuple(kroky), popis))
        worker.dokonceno.connect(self._uloha_dokoncena)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        self._typ_bezi = typ
        self._aktualizovat_dostupnost()
        worker.start()
        return True

    def _uloha_dokoncena(self, typ: str, preruseno: bool) -> None:
        """Signál z workeru — uloží výsledek, zpracuje až ``finished``."""
        self._vysledek_ulohy = (typ, preruseno)

    def _worker_finished(self) -> None:
        """Konec vlákna: potvrdit ``wait()``, teprve pak pokračovat."""
        worker = self._worker
        if worker is None:
            return
        if not worker.wait(5000):
            # Nemělo by nastat; vlákno nikdy neničíme.
            self._oznam("Ukončení přehrávání trvá déle, než se čeká.")
            return
        worker.deleteLater()
        self._worker = None
        self._typ_bezi = None

        # --- Zavírání aplikace ----------------------------------------
        if self._pozadavek_zavrit:
            if self._nabidka_zobrazena:
                # Zavřít nabídku ukončení a dokončit zavírání.
                self._dokoncit_zavreni = True
                aktivni = QApplication.activeModalWidget()
                if aktivni is not None:
                    aktivni.reject()
                return
            self._muzu_zavrit = True
            self.close()
            return

        if self._cekam_na_ukonceni:
            # Uživatel zrušil ukončení → zůstáváme otevření, hra
            # pozastavená, dokud sám neklikne „Pokračovat ve hře“.
            self._cekam_na_ukonceni = False
            self._pozastavena = True
            self._ukoncuje_se = False
            self._aktualizovat_dostupnost()
            self._oznam(
                "Přehrávání bylo ukončeno. Hra je pozastavena. "
                "Stiskněte Pokračovat ve hře.")
            return

        # --- Běžný chod hry ---------------------------------------------
        self._dokonceni_ulohy()

    def _dokonceni_ulohy(self) -> None:
        """Reakce na dokončené přehrávání (worker už je potvrzeně hotov)."""
        if self._vysledek_ulohy is None:
            self._aktualizovat_dostupnost()
            return
        typ, preruseno = self._vysledek_ulohy
        self._vysledek_ulohy = None
        self._aktualizovat_dostupnost()

        if typ == "ukazka":
            # Zkušební ukázka (editor melodií i průvodce rytmem):
            # nejdřív reakce volajícího (stav v dialogu), pak fokus.
            self._dokonceni_ukazky(preruseno)
            return

        if preruseno:
            return

        if typ == "sekvence":
            # Dokončené přehrání sekvence: povolit vstup (jen poprvé).
            self.logika.sekvence_prehrana()
            self._aktualizovat_dostupnost()
            self._oznam(f"Sekvence dohrála. {self.logika.popis_stavu()}")
        # U výsledkových melodií (vitezna/smutna) hlášení NEPŘEPISUJEME:
        # důležitá informace o výsledku, chybě a zbývajících pokusech musí
        # na panelu zůstat čitelná i po dohrání melodie.

        # Dialog statistik AŽ po dohrání výsledkové melodie a jen jednou.
        if self._ceka_dialog is not None:
            if not self._ukoncuje_se and not self._pozadavek_zavrit:
                vysledek = self._ceka_dialog
                self._ceka_dialog = None      # právě jednou
                self._otevri_stats_intervalu(vysledek)
            self._nastav_fokus("nova_hra")
            return

        self._nastav_fokus(self._fokus_po_prehrani)

    def _dokonceni_ukazky(self, preruseno: bool) -> None:
        """Dokončení zkušební ukázky (editor melodií i průvodce rytmem).

        Nejdřív zavolá odloženou reakci volajícího (stav v dialogu) —
        chráněně, protože dialog mohl být mezitím zavřený a zničený.
        Při přerušení se fokus nepřesouvá (stejně jako dřív).
        """
        callback = self._ukazka_po_dokonceni
        self._ukazka_po_dokonceni = None
        if callback is not None:
            try:
                callback()
            except Exception:   # noqa: BLE001 — zničený dialog nesmí shodit worker
                pass
        if preruseno:
            return

        # Fokus se NESMÍ přesunout do hlavního okna — otevřený dialog
        # (editor melodií, průvodce) musí zůstat otevřený a zaměřený.
        modal = QApplication.activeModalWidget()
        if modal is not None:
            self._oznam("Zkušební ukázka dohrála.")
            self._vrat_fokus_do_dialogu(modal)
            return
        self._nastav_fokus(self._fokus_po_prehrani)

    def _nastav_fokus(self, kam: str | None) -> None:
        """Předvídatelný návrat fokusu po přehrávání."""
        self.activateWindow()
        if kam == "prvni_ton":
            if self._tlacitka_tonu[0].isEnabled():
                self._tlacitka_tonu[0].setFocus()
                return
            self._t_nova.setFocus()
            return
        if kam == "nova_hra":
            self._t_nova.setFocus()
            return
        # „zachovat“ — vrať se na prvek, který přehrávání spustil.
        cil = self._fokus_pred
        if cil is not None and cil.isVisible() and cil.isEnabled():
            cil.setFocus()
        elif self._t_nova.isEnabled():
            self._t_nova.setFocus()

    def _vrat_fokus_do_dialogu(self, dialog: QWidget) -> None:
        """Zaměří prvek uvnitř právě otevřeného modálního dialogu.

        Používá se po dokončení zkušební ukázky: hlavní okno se nesmí
        ujmout fokusu, dokud je editor melodií otevřený.
        """
        dialog.activateWindow()
        cil = self._fokus_pred
        if (cil is not None and cil.isVisible() and cil.isEnabled()
                and dialog.isAncestorOf(cil)):
            cil.setFocus()
            return
        # Záloha: první zaměřitelný prvek v pořadí Tab v dialogu.
        prvek = dialog.nextInFocusChain()
        zacatek = prvek
        while True:
            if (prvek.isVisible() and prvek.isEnabled()
                    and prvek.focusPolicy() != Qt.FocusPolicy.NoFocus):
                prvek.setFocus()
                return
            prvek = prvek.nextInFocusChain()
            if prvek is zacatek:
                break
        dialog.setFocus()

    # ==================================================================
    # Akce hry
    # ==================================================================

    def _kroky_sekvence(self) -> list[KrokPrehravani]:
        if self.logika.nastaveni.rezim == "akordy":
            return [
                KrokPrehravani(midi=midi_seznam[0], zvuk_s=DELKA_TONU_SEKVENCE_S,
                               pauza_s=PAUZA_V_SEKVENCE_S, midi_seznam=midi_seznam)
                for midi_seznam in self.logika.midi_sekvence()
            ]
        return [
            KrokPrehravani(midi=midi, zvuk_s=DELKA_TONU_SEKVENCE_S,
                           pauza_s=PAUZA_V_SEKVENCE_S)
            for midi in self.logika.midi_sekvence()
        ]

    def _kroky_melodie(self, druh: str) -> list[KrokPrehravani]:
        n = self.nastaveni
        id_melodie = (n.id_smutne_melodie if druh == melodies.DRUH_SMUTNA
                      else n.id_vitezne_melodie)
        volba = melodies.ziskej_melodii(n.tonina, druh, id_melodie)
        if volba.varovani:
            self._oznam(f"Poznámka k melodii: {volba.varovani}")
        return melodies.casovy_plan(volba.melodie)

    def prehraj_ukazku(self, melodie: melodies.Melodie, tonina: str) -> bool:
        """Zkušební přehrání melodie z editoru (na hru ani skóre nemá vliv).

        Volá ji editor vlastních melodií (přes dialog Nastavení). Po
        dokončení se fokus vrátí do editoru, ne do hlavního okna
        (viz větev „ukazka“ v ``_dokonceni_ulohy``).
        """
        if self._worker is not None and not self._worker.isFinished():
            self._oznam("Čekám na ukončení probíhajícího přehrávání.")
            return False
        if self._pozastavena:
            self._oznam("Hra je pozastavena. Nejdřív pokračujte ve hře.")
            return False
        try:
            prelozena = melodies.transponuj_melodii(melodie, tonina)
            kroky = melodies.casovy_plan(prelozena)
        except (ValueError, RuntimeError) as e:
            self._oznam(f"Melodii nelze přehrát: {e}")
            return False
        self._oznam(
            f"Přehrávám ukázku melodie {melodie.nazev} "
            f"v tónině {theory.POPISKY_TONIN.get(tonina, tonina)}.")
        return self._spust_ulohu("ukazka", kroky,
                                 f"ukázka melodie {melodie.nazev}",
                                 fokus_po="zachovat")

    def prehraj_kroky(
        self,
        kroky: list[KrokPrehravani],
        popis: str,
        po_dokonceni=None,
    ) -> bool:
        """Zkušební přehrání hotových kroků (rytmus, odpočítání, porovnání).

        Používá průvodce rytmem. Stejné podmínky jako
        ``prehraj_ukazku``: jeden worker současně, hra nesmí být
        pozastavená, typ „ukazka“ po dokončení vrátí fokus do
        otevřeného dialogu. ``po_dokonceni`` (volitelné) se zavolá
        po doběhnutí i po přerušení — hlavní okno ho chrání proti
        zničenému dialogu.
        """
        if not kroky:
            self._oznam("Není co přehrát — nejdřív vyberte nebo upravte vzor.")
            return False
        spusteno = self._spust_ulohu("ukazka", list(kroky), popis,
                                     fokus_po="zachovat")
        if spusteno and po_dokonceni is not None:
            self._ukazka_po_dokonceni = po_dokonceni
        return spusteno

    def zastav_ukazku(self) -> bool:
        """Kooperativně přeruší právě běžící zkušební ukázku.

        Na hru (sekvence, výsledkové melodie) sahat NIKDY nemůže —
        tyto úlohy přerušuje jen zavírání aplikace. Vrací True, pokud
        bylo co zastavovat.
        """
        worker = self._worker
        if worker is None or worker.isFinished():
            return False
        if self._typ_bezi != "ukazka":
            return False
        worker.prerus()
        return True

    def _akce_povolena(self) -> bool:
        """Akce z klávesnic zkratek jen když není otevřený modální dialog."""
        if QApplication.activeModalWidget() is not None:
            return False
        if self._pozastavena:
            self._oznam("Hra je pozastavena. Nejdřív pokračujte ve hře.")
            return False
        return True

    def _nova_hra(self) -> None:
        if not self._akce_povolena():
            return
        if self._worker is not None and not self._worker.isFinished():
            self._oznam("Čekám na ukončení probíhajícího přehrávání.")
            return
        # Nastavení se projevuje od začátku nového kola.
        self.logika.zmenit_nastaveni(**self.nastaveni.__dict__)
        self.logika.nova_hra()
        self.logika.zahaj_kolo()
        self._aktualizuj_tlacitka_tonu()
        self._aktualizuj_info()
        self._aktualizovat_dostupnost()
        self._oznam(
            f"Nová hra. Tónina {theory_popis_toniny(self.nastaveni.tonina)}, "
            f"sekvence má {self.nastaveni.delka_sekvence} tónů, "
            f"{self.nastaveni.pocet_pokusu} pokusů. Poslechněte si sekvenci.")
        self._spust_ulohu("sekvence", self._kroky_sekvence(),
                          "sekvence tónů", fokus_po="prvni_ton")

    def _prehraj_sekvenci_znovu(self) -> None:
        """Opakování — NEMĚNÍ skóre ani pokusy (jen zvukový výstup)."""
        if not self._akce_povolena():
            return
        if self._worker is not None and not self._worker.isFinished():
            self._oznam("Čekám na ukončení probíhajícího přehrávání.")
            return
        if not self.logika.sekvence:
            self._oznam("Není rozehrané kolo. Nejdřív spusťte novou hru.")
            return
        self._oznam("Přehrávám sekvenci znovu.")
        self._spust_ulohu("sekvence", self._kroky_sekvence(),
                          "sekvence tónů", fokus_po="zachovat")

    def _zopovat_kolo(self) -> None:
        if not self._akce_povolena():
            return
        if self._worker is not None and not self._worker.isFinished():
            self._oznam("Čekám na ukončení probíhajícího přehrávání.")
            return
        if not self.logika.zopovat_kolo():
            self._oznam("Kolo teď nelze zopakovat. Nejdřív spusťte novou hru.")
            return
        self._aktualizuj_info()
        self._aktualizovat_dostupnost()
        self._oznam("Kolo se restartuje: stejná sekvence a plný počet pokusů.")
        self._spust_ulohu("sekvence", self._kroky_sekvence(),
                          "sekvence tónů", fokus_po="prvni_ton")

    def _vstup_ton(self, stupen: int) -> None:
        """Jediná cesta, jak se do logiky dostane vstup hráče."""
        if not self._tlacitka_tonu[stupen].isEnabled():
            return
        vysledek = self.logika.zpracuj_vstup(stupen)
        if not vysledek.prijat:
            self._oznam(vysledek.hlaska)
            return

        self._aktualizuj_info()
        self._aktualizovat_dostupnost()

        if vysledek.kolo_dokonceno and vysledek.uspech:
            if vysledek.interval is not None:
                self._ceka_dialog = vysledek.interval
            if vysledek.ztezena_hra:
                self.nastaveni = self.logika.nastaveni
                uloziste.uloz_nastaveni(self.nastaveni)
                self._aktualizuj_info()
                self._aktualizovat_dostupnost()
            self._oznam(
                f"{vysledek.hlaska} "
                f"Sekvence zopakována správně, vyhráváte.")
            self._spust_ulohu("vitezna", self._kroky_melodie(melodies.DRUH_VITEZNA),
                              "vítězná melodie", fokus_po="nova_hra")
        elif vysledek.kolo_dokonceno and not vysledek.uspech:
            if vysledek.interval is not None:
                self._ceka_dialog = vysledek.interval
            self._oznam(
                f"{vysledek.hlaska} "
                f"Statistiky: správně {self.logika.spravce.celkem.spravne_tony}, "
                f"chybně {self.logika.spravce.celkem.chybne_tony}.")
            self._spust_ulohu("smutna", self._kroky_melodie(melodies.DRUH_SMUTNA),
                              "smutná melodie", fokus_po="nova_hra")
        elif vysledek.spravne:
            # Potvrzení správného tónu nebo akordu — přehraje se samotný tón/akord.
            self._oznam(vysledek.hlaska)
            if self.logika.nastaveni.rezim == "akordy":
                midi_seznam = tuple(theory.akord_stupne(self.logika.nastaveni.tonina, self.logika.sekvence[vysledek.pozice - 1], self.logika.nastaveni.oktava))
                krok = KrokPrehravani(midi=midi_seznam[0], zvuk_s=DELKA_TONU_S, pauza_s=0.0, midi_seznam=midi_seznam)
            else:
                midi = self.logika.midi_sekvence()[vysledek.pozice - 1]
                krok = KrokPrehravani(midi=midi, zvuk_s=DELKA_TONU_S, pauza_s=0.0)
            self._spust_ulohu(
                "ton",
                [krok],
                "potvrzení tónu", fokus_po="zachovat")
        else:
            # Chyba se zbývajícími pokusy — smutná melodie + restart sekvence.
            self._oznam(vysledek.hlaska)
            self._spust_ulohu("smutna", self._kroky_melodie(melodies.DRUH_SMUTNA),
                              "smutná melodie", fokus_po="zachovat")

    # ==================================================================
    # Nastavení a statistiky
    # ==================================================================

    def _otevri_nastaveni(self) -> None:
        if QApplication.activeModalWidget() is not None:
            return
        if self._worker is not None and not self._worker.isFinished():
            self._oznam("Čekám na ukončení probíhajícího přehrávání.")
            return
        dialog = NastaveniDialog(
            self.nastaveni, self,
            nastaveni_hlasu=self.nastaveni_hlasu,
            oznamovac=self.oznamovac,
            prehravac=self.prehraj_ukazku,
            prehravac_kroku=self.prehraj_kroky,
            zastav_ukazku=self.zastav_ukazku,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                hodnoty = dialog.hodnoty()
                hodnoty_hlasu = dialog.hodnoty_hlasu()
            except ValueError as e:
                self._oznam(f"Neplatné nastavení: {e}")
                self._t_nastaveni.setFocus()
                return
            self._pouzij_nastaveni(hodnoty)
            self._pouzij_nastaveni_hlasu(hodnoty_hlasu)
        # Po zavření editoru melodií (i při Zrušit) musí oba výběry
        # ukazovat jen na existující melodie — smazaná volba se vrátí
        # na výchozí ID.
        self._srovnaj_vyber_melodii()
        self.activateWindow()
        # Fokus až po události aktivace okna (asynchronní).
        QTimer.singleShot(0, self._t_nastaveni.setFocus)

    def _pouzij_nastaveni_hlasu(self, hodnoty: NastaveniHlasu) -> None:
        """Nastavení hlasu: uložit na disk + použít v oznamovacím modulu."""
        hodnoty.over()
        uloziste.uloz_nastaveni_hlasu(hodnoty)
        self.nastaveni_hlasu = hodnoty
        self.oznamovac.nastav_rezim(hodnoty.rezim)
        self._oznam(f"Nastavení hlasu uloženo. {self.oznamovac.popis_dostupnosti}")

    def _srovnaj_vyber_melodii(self) -> None:
        """Vrátí smazané volby melodií na výchozí ID (disk + logika + GUI).

        Volá se po zavření nastavení i správce melodií — i když uživatel
        zrušil uložení, nesmí zůstat uložené ani interní reference na
        smazanou melodii. Nesouvisející nastavení se nemění.
        """
        zmeny: dict[str, str] = {}
        for druh, atribut in (
            (melodies.DRUH_SMUTNA, "id_smutne_melodie"),
            (melodies.DRUH_VITEZNA, "id_vitezne_melodie"),
        ):
            id_melodie = getattr(self.nastaveni, atribut)
            if not melodies.je_dostupna_melodie(druh, id_melodie):
                zmeny[atribut] = melodies.VYCHOZI_ID[druh]
        if not zmeny:
            return
        nove = NastaveniHry(**{**self.nastaveni.__dict__, **zmeny})
        nove.over()
        self.nastaveni = nove
        uloziste.uloz_nastaveni(nove)
        # Jen dotčené klíče — interval statistik se nesmí měnit.
        self.logika.zmenit_nastaveni(**zmeny)
        self._aktualizuj_info()
        self._oznam(
            "Vybraná melodie byla smazána. Vrací se výchozí melodie.")

    def _pouzij_nastaveni(self, hodnoty: dict) -> None:
        """Nastavení: uložit na disk + použít pro další kola."""
        nove = NastaveniHry(**hodnoty)
        nove.over()
        self.nastaveni = nove
        uloziste.uloz_nastaveni(nove)

        kolo_bezi = (
            bool(self.logika.sekvence)
            and self.logika.stav in (StavKola.CEKA_NA_PREHRANI,
                                     StavKola.HRAC_VSTUPUJE)
        )
        if kolo_bezi:
            self._oznam(
                "Nastavení uloženo. Probíhající kolo se nezmění, "
                "nové nastavení se použije od dalšího kola.")
        else:
            self.logika.zmenit_nastaveni(**hodnoty)
            self._aktualizuj_tlacitka_tonu()
            self._oznam("Nastavení uloženo a použito.")
        self._aktualizuj_info()
        self._aktualizovat_dostupnost()

    def _otevri_stats(self) -> None:
        if QApplication.activeModalWidget() is not None:
            return
        dialog = StatsDialog(
            self.logika.spravce.interval,
            self.logika.spravce.celkem,
            "Období: od začátku tohoto statistického intervalu. "
            "Celkové statistiky platí od spuštění hry.",
            self,
        )
        dialog.exec()
        self.activateWindow()
        # Fokus až po události aktivace okna (asynchronní).
        QTimer.singleShot(0, self._t_stats.setFocus)

    def _otevri_stats_intervalu(self, vysledek: VysledekIntervalu) -> None:
        dialog = StatsDialog(
            vysledek.interval,
            vysledek.celkem,
            f"Období: právě dokončený interval "
            f"({vysledek.pocet_kol} dokončených kol). "
            f"Celkové statistiky platí od spuštění hry.",
            self,
        )
        dialog.setWindowTitle("Výsledky statistického intervalu")
        self._oznam(
            "Statistický interval je dokončený. Otevírám přehled výsledků.")
        dialog.exec()

    # ==================================================================
    # Pokračování po pozastavení
    # ==================================================================

    def _pokracovat_ve_hre(self) -> None:
        if not self._pozastavena:
            return
        if self._worker is not None and not self._worker.isFinished():
            self._oznam("Přehrávání ještě probíhá, čekejte.")
            return
        self._pozastavena = False
        self._aktualizovat_dostupnost()
        self._oznam(
            "Hra pokračuje. Sekvence, pokusy i statistiky zůstaly beze změny.")
        # Odložený dialog statistik (zrušením ukončení se nesmí ztratit).
        if self._ceka_dialog is not None and QApplication.activeModalWidget() is None:
            vysledek = self._ceka_dialog
            self._ceka_dialog = None
            self._otevri_stats_intervalu(vysledek)
            self.activateWindow()
            self._t_nova.setFocus()
            return
        if self.logika.stav is StavKola.HRAC_VSTUPUJE and self._tlacitka_tonu[0].isEnabled():
            self._tlacitka_tonu[0].setFocus()
        else:
            self._t_nova.setFocus()

    # ==================================================================
    # Zavírání okna — bezpečné odložení do ukončení workeru
    # ==================================================================

    def closeEvent(self, event: QCloseEvent) -> None:   # noqa: D102
        if self._muzu_zavrit:
            self._zastav_zaviraci_timer()
            event.accept()
            return

        worker_bezi = self._worker is not None and not self._worker.isFinished()

        if worker_bezi:
            event.ignore()
            if not self._pozadavek_zavrit:
                # První požadavek na zavření — bezpečně odložit.
                self._pozadavek_zavrit = True
                self._ukoncuje_se = True
                self._aktualizovat_dostupnost()
                self._oznam("Ukončuji přehrávání, aplikace se zavře.")
                self._worker.prerus()
                self._spust_odpocet_zavreni()
            return

        # Worker (pokud existoval) už doběhl — potvrdit jeho konec.
        if self._worker is not None:
            if not self._worker.wait(3000):
                event.ignore()
                self._pozadavek_zavrit = True
                self._ukoncuje_se = True
                self._aktualizovat_dostupnost()
                self._spust_odpocet_zavreni()
                return
            self._worker.deleteLater()
            self._worker = None
            self._typ_bezi = None

        self._zastav_zaviraci_timer()
        # Nic neběží — je bezpečné zavřít.
        self._muzu_zavrit = True
        event.accept()

    def _spust_odpocet_zavreni(self) -> None:
        """Ne-blokující čekání na ukončení workeru (QTimer)."""
        self._zaviraci_cas = time.monotonic() + LIMIT_UKONCENI_S
        if self._zaviraci_timer is None:
            self._zaviraci_timer = QTimer(self)
            self._zaviraci_timer.setInterval(INTERVAL_KONTROLY_MS)
            self._zaviraci_timer.timeout.connect(self._krok_zavreni)
        self._zaviraci_timer.start()

    def _zastav_zaviraci_timer(self) -> None:
        if self._zaviraci_timer is not None:
            self._zaviraci_timer.stop()

    def _krok_zavreni(self) -> None:
        worker = self._worker
        if worker is None or worker.isFinished():
            # Worker doběhl — potvrdit konec a dokončit zavírání.
            if worker is None or worker.wait(3000):
                self._zastav_zaviraci_timer()
                self._muzu_zavrit = True
                self.close()
                return
        if time.monotonic() > self._zaviraci_cas:
            self._zastav_zaviraci_timer()
            self._nabidni_zruseni_zavreni()

    def _nabidni_zruseni_zavreni(self) -> None:
        """Limit překročen: nabídnout čekat, nebo zrušit zavírání."""
        if self._pozadavek_zavrit and self._worker is not None \
                and self._worker.isFinished() and self._worker.wait(3000):
            self._muzu_zavrit = True
            self.close()
            return

        box = QMessageBox(self)
        box.setWindowTitle("Ukončení aplikace")
        box.setText("Ukončování přehrávání trvá déle, než se čeká.")
        box.setInformativeText(
            "Aplikace se zatím nezavře a herní ovládání zůstane "
            "vypnuté, dokud přehrávání bezpečně neskončí.")
        b_zkouset = box.addButton("Zkustit znovu čekat",
                                  QMessageBox.ButtonRole.AcceptRole)
        b_zrusit = box.addButton("Zrušit ukončení",
                                 QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b_zkouset)
        box.setAccessibleName("Nabídka ukončení aplikace")
        self._nabidka_zobrazena = True
        box.exec()
        self._nabidka_zobrazena = False

        if self._dokoncit_zavreni or (self._pozadavek_zavrit and
                                      (self._worker is None or
                                       (self._worker.isFinished() and
                                        self._worker.wait(3000)))):
            self._dokoncit_zavreni = False
            self._muzu_zavrit = True
            self.close()
            return

        if box.clickedButton() is b_zrusit:
            # Zůstáváme v aplikaci; hra zůstává pozastavená,
            # dokud worker doběhne a uživatel neklikne „Pokračovat ve hře“.
            self._pozadavek_zavrit = False
            self._cekam_na_ukonceni = True
            self._ukoncuje_se = False
            self._aktualizovat_dostupnost()
            self._oznam(
                "Ukončení zrušeno. Aplikace zůstává otevřená, "
                "herní ovládání je vypnuté, dokud nedoběhne přehrávání.")
        else:
            # Zkoušet znovu čekat.
            self._spust_odpocet_zavreni()

    # ------------------------------------------------------------------
    def close_mozne(self) -> bool:
        """Pro testy: True, pokud je okno skutečně zavřené."""
        return self._muzu_zavrit


def theory_popis_toniny(tonina: str) -> str:
    return theory.POPISKY_TONIN.get(tonina, tonina)
