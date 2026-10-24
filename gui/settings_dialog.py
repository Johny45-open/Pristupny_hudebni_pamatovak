"""Přístupné nastavení hry a hlasového výstupu (PyQt6).

Každé pole má český popisek propojený přes ``setBuddy``, přístupný
název a popis. Nastavení se validuje a vrací jako složka hodnot.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

import melodies
import notify
import theory


class NastaveniDialog(QDialog):
    """Dialog nastavení hry — tónina, októva, pokusy, délka, interval, melodie,
    hlasový výstup."""

    def __init__(self, nastaveni, parent=None, *,
                 nastaveni_hlasu=None,
                 oznamovac=None,
                 prehravac=None,
                 prehravac_kroku=None,
                 zastav_ukazku=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavení hry")
        self.setModal(True)
        self.setAccessibleDescription(
            "Nastavení tóniny, oktávy, pokusů, délky sekvence, "
            "intervalu statistik, melodií a hlasového výstupu.")
        self._nastaveni = nastaveni   # kopie pro čtení výchozích hodnot
        self._oznamovac = oznamovac           # pro stav a zkušební hlášku
        self._prehravac = prehravac           # (melodie, tonina) -> bool
        self._prehravac_kroku = prehravac_kroku   # (kroky, popis) -> bool
        self._zastav_ukazku = zastav_ukazku       # () -> bool
        self._nastaveni_hlasu = (nastaveni_hlasu or notify.NastaveniHlasu())

        hlavni = QVBoxLayout(self)

        nadpis = QLabel("Nastavení hry")
        nadpis.setAccessibleName("Nastavení hry, nadpis")
        font = nadpis.font()
        font.setBold(True)
        nadpis.setFont(font)
        hlavni.addWidget(nadpis)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        hlavni.addLayout(form)

        # --- Tónina ------------------------------------------------------
        self.tonina = QComboBox(self)
        for klic in theory.PORADI_TONIN:
            self.tonina.addItem(theory.POPISKY_TONIN[klic], klic)
        self.tonina.setCurrentIndex(theory.PORADI_TONIN.index(nastaveni.tonina))
        self.tonina.setAccessibleName("Tónina")
        self.tonina.setAccessibleDescription(
            "Durová tónina, ve které se budou generovat tóny.")
        pop_tonina = QLabel("Tónina:", self)
        pop_tonina.setBuddy(self.tonina)
        form.addRow(pop_tonina, self.tonina)

        # --- Výchozí oktáva ---------------------------------------------
        self.oktava = QComboBox(self)
        for o in (3, 4, 5):
            self.oktava.addItem(f"{o}. oktáva", o)
        self.oktava.setCurrentIndex((3, 4, 5).index(nastaveni.oktava))
        self.oktava.setAccessibleName("Výchozí oktáva")
        self.oktava.setAccessibleDescription(
            "Oktáva, od které sedm stupňů stupnice začíná.")
        pop_oktava = QLabel("Výchozí oktáva:", self)
        pop_oktava.setBuddy(self.oktava)
        form.addRow(pop_oktava, self.oktava)

        # --- Počet pokusů -----------------------------------------------
        self.pokusy = QSpinBox(self)
        self.pokusy.setRange(1, 10)
        self.pokusy.setValue(nastaveni.pocet_pokusu)
        self.pokusy.setAccessibleName("Počet pokusů")
        self.pokusy.setAccessibleDescription(
            "Kolik pokusů má hráč v jednom kole. Chybný tón spotřebí jeden.")
        pop_pokusy = QLabel("Počet pokusů:", self)
        pop_pokusy.setBuddy(self.pokusy)
        form.addRow(pop_pokusy, self.pokusy)

        # --- Délka sekvence ---------------------------------------------
        self.delka = QSpinBox(self)
        self.delka.setRange(2, 12)
        self.delka.setValue(nastaveni.delka_sekvence)
        self.delka.setAccessibleName("Délka sekvence")
        self.delka.setAccessibleDescription(
            "Počet tónů v jedné sekvenci, od 2 do 12.")
        pop_delka = QLabel("Délka sekvence:", self)
        pop_delka.setBuddy(self.delka)
        form.addRow(pop_delka, self.delka)

        # --- Interval statistik -----------------------------------------
        self.interval = QSpinBox(self)
        self.interval.setRange(1, 100)
        self.interval.setValue(nastaveni.interval_statistik)
        self.interval.setAccessibleName("Interval statistik")
        self.interval.setAccessibleDescription(
            "Po kolika dokončených kolech se zobrazí přehled statistik.")
        pop_interval = QLabel("Interval statistik:", self)
        pop_interval.setBuddy(self.interval)
        form.addRow(pop_interval, self.interval)

        # --- Odměna po úspěšných kolech ---------------------------------
        self.odmena_kola = QSpinBox(self)
        self.odmena_kola.setRange(1, 50)
        self.odmena_kola.setValue(nastaveni.odmena_po_kolech)
        self.odmena_kola.setAccessibleName("Odměna po úspěšných kolech")
        self.odmena_kola.setAccessibleDescription(
            "Po kolika úspěšných kolech v řadě (streak) se přehraje odměna.")
        pop_odmena = QLabel("Odměna po úspěšných kolech:", self)
        pop_odmena.setBuddy(self.odmena_kola)
        form.addRow(pop_odmena, self.odmena_kola)

        # --- Absolutní hudební sluch ------------------------------------
        self.absolutni_sluch = QCheckBox("Zapnout absolutní hudební sluch", self)
        self.absolutni_sluch.setChecked(nastaveni.absolutni_sluch)
        self.absolutni_sluch.setAccessibleName("Absolutní hudební sluch")
        self.absolutni_sluch.setAccessibleDescription(
            "Pokud je zapnuto a zvládnete všechna kola v intervalu bez chyb, hra se stane těžší.")
        form.addRow("", self.absolutni_sluch)

        # --- Herní režim -------------------------------------------------
        self.rezim = QComboBox(self)
        self.rezim.addItem("Tóny / Melodie", "tony")
        self.rezim.addItem("Akordy", "akordy")
        self.rezim.setCurrentIndex(0 if getattr(nastaveni, "rezim", "tony") == "tony" else 1)
        self.rezim.setAccessibleName("Herní režim")
        self.rezim.setAccessibleDescription(
            "Režim hry: buď hádání jednotlivých tónů, nebo hádání akordů.")
        pop_rezim = QLabel("Herní režim:", self)
        pop_rezim.setBuddy(self.rezim)
        form.addRow(pop_rezim, self.rezim)

        # --- Smutná melodie ---------------------------------------------
        self.smutna = QComboBox(self)
        self.smutna.setAccessibleName("Smutná melodie")
        self.smutna.setAccessibleDescription(
            "Melodie, která se přehraje při chybném tónu.")
        pop_smutna = QLabel("Smutná melodie:", self)
        pop_smutna.setBuddy(self.smutna)
        form.addRow(pop_smutna, self.smutna)

        # --- Vítězná melodie --------------------------------------------
        self.vitezna = QComboBox(self)
        self.vitezna.setAccessibleName("Vítězná melodie")
        self.vitezna.setAccessibleDescription(
            "Melodie, která se přehraje po správném zopakování sekvence.")
        pop_vitezna = QLabel("Vítězná melodie:", self)
        pop_vitezna.setBuddy(self.vitezna)
        form.addRow(pop_vitezna, self.vitezna)

        # Naplnění nabídky melodií (přednastavené + vlastní) se volá
        # i po zavření správce vlastních melodií.
        self._napln_kombo_melodie()

        # --- Správce vlastních melodií ----------------------------------
        self.tlacitko_spravce = QPushButton("Spravovat vlastní melodie…", self)
        self.tlacitko_spravce.setAccessibleName("Spravovat vlastní melodie")
        self.tlacitko_spravce.setAccessibleDescription(
            "Otevře dialog pro vytváření, úpravu a mazání vlastních "
            "melodií a pro zkušební přehrání.")
        self.tlacitko_spravce.clicked.connect(self._otevri_spravce_melodii)
        hlavni.addWidget(self.tlacitko_spravce)

        # --- Informace o přizpůsobení melodií ---------------------------
        self._info = QLabel(self)
        self._info.setWordWrap(True)
        self._info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._info.setAccessibleName("Informace o melodiích pro tóninu")
        hlavni.addWidget(self._info)

        # --- Hlasový výstup ---------------------------------------------
        skupina_hlas = QGroupBox("Hlasový výstup", self)
        skupina_hlas.setAccessibleName("Hlasový výstup")
        lay_hlas = QVBoxLayout(skupina_hlas)

        form_hlas = QFormLayout()
        form_hlas.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        lay_hlas.addLayout(form_hlas)

        self.rezim_hlasu = QComboBox(self)
        for rezim in notify.REZIMY_HLASU:
            self.rezim_hlasu.addItem(notify.POPISKY_REZIMU[rezim], rezim)
        self.rezim_hlasu.setCurrentIndex(
            self.rezim_hlasu.findData(self._nastaveni_hlasu.rezim))
        self.rezim_hlasu.setAccessibleName("Režim hlasového výstupu")
        self.rezim_hlasu.setAccessibleDescription(
            "Hlas vypnut: nemluví vůbec, text je jen na stavovém panelu. "
            "Hlas jen s potvrzenou čtečkou obrazovky: mluví pouze tehdy, "
            "když je skutečně aktivní NVDA, JAWS nebo jiná podporovaná "
            "čtečka; jinak zůstává zticha. "
            "Hlas i bez čtečky: přednost má čtečka, bez ní použije "
            "systémový hlas.")
        pop_rezim = QLabel("Režim:", self)
        pop_rezim.setBuddy(self.rezim_hlasu)
        form_hlas.addRow(pop_rezim, self.rezim_hlasu)

        self.stav_hlasu = QLabel(self)
        self.stav_hlasu.setWordWrap(True)
        self.stav_hlasu.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.stav_hlasu.setAccessibleName("Stav hlasového výstupu")
        lay_hlas.addWidget(self.stav_hlasu)

        tlacitka_hlas = QHBoxLayout()
        self.tlacitko_zjistit = QPushButton("Zjistit stav hlasu", self)
        self.tlacitko_zjistit.setAccessibleName("Zjistit stav hlasu")
        self.tlacitko_zjistit.setAccessibleDescription(
            "Zjistí, jestli běží čtečka obrazovky a jestli je dostupný "
            "systémový hlas, a výsledek přečte do tohoto pole.")
        self.tlacitko_zjistit.clicked.connect(self._aktualizuj_stav_hlasu)
        tlacitka_hlas.addWidget(self.tlacitko_zjistit)

        self.tlacitko_zkusit = QPushButton("Zkušební hláška", self)
        self.tlacitko_zkusit.setAccessibleName("Zkušební hláška")
        self.tlacitko_zkusit.setAccessibleDescription(
            "Nechá promluvit právě zvolený výstup, aby bylo poznat, "
            "jestli je hlas slyšet. Stavové hlášení hry tím nepřepíše.")
        self.tlacitko_zkusit.clicked.connect(self._zkusebni_hlaska)
        tlacitka_hlas.addWidget(self.tlacitko_zkusit)
        lay_hlas.addLayout(tlacitka_hlas)

        hlavni.addWidget(skupina_hlas)

        # --- Tlačítka ----------------------------------------------------
        tlacitka = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        tlacitka.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        tlacitka.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        tlacitka.setAccessibleName("Ovládací tlačítka nastavení")
        tlacitka.accepted.connect(self.accept)
        tlacitka.rejected.connect(self.reject)
        hlavni.addWidget(tlacitka)
        self._tlacitka = tlacitka

        self.tonina.currentIndexChanged.connect(self._aktualizuj_info)
        self.smutna.currentIndexChanged.connect(self._aktualizuj_info)
        self.vitezna.currentIndexChanged.connect(self._aktualizuj_info)
        self._aktualizuj_info()
        self._aktualizuj_stav_hlasu()

        self.setTabOrder(self.tonina, self.oktava)
        self.setTabOrder(self.oktava, self.pokusy)
        self.setTabOrder(self.pokusy, self.delka)
        self.setTabOrder(self.delka, self.interval)
        self.setTabOrder(self.interval, self.odmena_kola)
        self.setTabOrder(self.odmena_kola, self.absolutni_sluch)
        self.setTabOrder(self.absolutni_sluch, self.smutna)
        self.setTabOrder(self.smutna, self.vitezna)
        self.setTabOrder(self.vitezna, self.tlacitko_spravce)
        self.setTabOrder(self.tlacitko_spravce, self.rezim_hlasu)
        self.setTabOrder(self.rezim_hlasu, self.tlacitko_zjistit)
        self.setTabOrder(self.tlacitko_zjistit, self.tlacitko_zkusit)
        self.setTabOrder(self.tlacitko_zkusit, tlacitka)

    # ------------------------------------------------------------------
    # Melodie
    # ------------------------------------------------------------------

    def _napln_kombo_melodie(self) -> None:
        """Naplní oba výběry melodií; smazaná volba spadne na výchozí.

        Při prvním naplnění se vychází z uloženého nastavení, po
        zavření správce z aktuálního výběru (smazaný údaj se přeskočí).
        """
        for druh, combo, vychozi_id, ulozene_id in (
            (melodies.DRUH_SMUTNA, self.smutna,
             melodies.VYCHOZI_ID[melodies.DRUH_SMUTNA],
             self._nastaveni.id_smutne_melodie),
            (melodies.DRUH_VITEZNA, self.vitezna,
             melodies.VYCHOZI_ID[melodies.DRUH_VITEZNA],
             self._nastaveni.id_vitezne_melodie),
        ):
            stare_id = combo.currentData() or ulozene_id or vychozi_id
            combo.blockSignals(True)
            combo.clear()
            for mid, nazev in melodies.nabidka_melodii(druh):
                combo.addItem(nazev, mid)
            index = combo.findData(stare_id)
            if index < 0:
                index = combo.findData(vychozi_id)
            combo.setCurrentIndex(max(index, 0))
            combo.blockSignals(False)

    def _otevri_spravce_melodii(self) -> None:
        """Otevře správce vlastních melodií; po zavření obnoví výběry."""
        from gui.melodie_dialog import SpravceMelodiDialog

        dialog = SpravceMelodiDialog(
            self,
            prehravac=self._prehravac,
            prehravac_kroku=self._prehravac_kroku,
            zastav_ukazku=self._zastav_ukazku,
            oznamovac=self._oznamovac,
            tonina=self.tonina.currentData(),
        )
        dialog.exec()
        self._napln_kombo_melodie()
        self._aktualizuj_info()
        self.activateWindow()
        self.tlacitko_spravce.setFocus()

    def _aktualizuj_info(self) -> None:
        """Popíše, odkud se melodie pro vybranou tóninu vezme."""
        tonina = self.tonina.currentData()
        casti = []
        for druh, combo in ((melodies.DRUH_SMUTNA, self.smutna),
                            (melodies.DRUH_VITEZNA, self.vitezna)):
            volba = melodies.ziskej_melodii(tonina, druh, combo.currentData())
            zdroj = {"vlastni": "vlastní melodie",
                     "individualni": "individuální definice",
                     "transpozice": "automatická transpozice",
                     "zalozni": "záložní náhrada"}.get(volba.zdroj, volba.zdroj)
            casti.append(f"{volba.melodie.nazev}: {zdroj}")
            if volba.varovani:
                casti.append(f"  Pozn.: {volba.varovani}")
        text = ("Melodie pro tóninu " + theory.POPISKY_TONIN[tonina]
                + " — " + "; ".join(casti) + ".")
        self._info.setText(text)

    # ------------------------------------------------------------------
    # Hlasový výstup
    # ------------------------------------------------------------------

    def _aktualizuj_stav_hlasu(self) -> None:
        """Zjistí stav hlasu (čtečka vs. systémový hlas) a zobrazí ho."""
        if self._oznamovac is None:
            self.stav_hlasu.setText(
                "Stav hlasu není k dispozici — dialog není napojený "
                "na oznamovací modul.")
            self.tlacitko_zjistit.setEnabled(False)
            self.tlacitko_zkusit.setEnabled(False)
            return
        self.stav_hlasu.setText(self._oznamovac.popis_dostupnosti)

    def _zkusebni_hlaska(self) -> None:
        """Promluví zkušební hláškou (stavový panel se nepřepíše)."""
        if self._oznamovac is None:
            return
        promluvilo = self._oznamovac.zkusebni_hlaseni()
        stav = self._oznamovac.popis_dostupnosti
        if promluvilo:
            vysledek = "Zkušební hláška byla předána hlasovému výstupu."
        else:
            vysledek = ("Zkušební hlášku teď nelze přehrát — "
                        "podívejte se na stav hlasu.")
        self.stav_hlasu.setText(f"{vysledek} {stav}")
        self.stav_hlasu.setFocus()

    # ------------------------------------------------------------------

    def hodnoty(self) -> dict:
        """Validované hodnoty nastavení hry z dialogu."""
        hodnoty = {
            "tonina": self.tonina.currentData(),
            "oktava": int(self.oktava.currentData()),
            "pocet_pokusu": int(self.pokusy.value()),
            "delka_sekvence": int(self.delka.value()),
            "interval_statistik": int(self.interval.value()),
            "odmena_po_kolech": int(self.odmena_kola.value()),
            "absolutni_sluch": bool(self.absolutni_sluch.isChecked()),
            "id_smutne_melodie": self.smutna.currentData(),
            "id_vitezne_melodie": self.vitezna.currentData(),
            "rezim": self.rezim.currentData(),
        }
        # Kontrola rozsahů (i když spinboxy je hlídají).
        if not 2 <= hodnoty["delka_sekvence"] <= 12:
            raise ValueError("Délka sekvence musí být 2–12.")
        if not 1 <= hodnoty["pocet_pokusu"] <= 10:
            raise ValueError("Počet pokusů musí být 1–10.")
        if hodnoty["interval_statistik"] < 1:
            raise ValueError("Interval statistik musí být kladné celé číslo.")
        if hodnoty["odmena_po_kolech"] < 1:
            raise ValueError("Odměna po úspěšných kolech musí být kladné celé číslo.")
        return hodnoty

    def hodnoty_hlasu(self) -> notify.NastaveniHlasu:
        """Validované nastavení hlasového výstupu z dialogu."""
        nastaveni = notify.NastaveniHlasu(
            rezim=str(self.rezim_hlasu.currentData()))
        nastaveni.over()
        return nastaveni
