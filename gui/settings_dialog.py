"""Přístupné nastavení hry (PyQt6).

Každé pole má český popisek propojený přes ``setBuddy``, přístupný
název a popis. Nastavení se validuje a vrací jako složka hodnot.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

import melodies
import theory


class NastaveniDialog(QDialog):
    """Dialog nastavení hry — tónina, októva, pokusy, délka, interval, melodie."""

    def __init__(self, nastaveni, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavení hry")
        self.setModal(True)
        self.setAccessibleDescription(
            "Nastavení tóniny, oktávy, pokusů, délky sekvence, "
            "intervalu statistik a melodií.")
        self._nastaveni = nastaveni   # kopie pro čtení výchozích hodnot

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
            "Kolik pokusů má hráč v jednom kole. Chybný tón spotřebuje jeden.")
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

        # --- Smutná melodie ---------------------------------------------
        self.smutna = QComboBox(self)
        for mid, nazev in melodies.nabidka_melodii(melodies.DRUH_SMUTNA):
            self.smutna.addItem(nazev, mid)
        self.smutna.setCurrentIndex(
            self.smutna.findData(nastaveni.id_smutne_melodie))
        self.smutna.setAccessibleName("Smutná melodie")
        self.smutna.setAccessibleDescription(
            "Melodie, která se přehraje při chybném tónu.")
        pop_smutna = QLabel("Smutná melodie:", self)
        pop_smutna.setBuddy(self.smutna)
        form.addRow(pop_smutna, self.smutna)

        # --- Vítězná melodie --------------------------------------------
        self.vitezna = QComboBox(self)
        for mid, nazev in melodies.nabidka_melodii(melodies.DRUH_VITEZNA):
            self.vitezna.addItem(nazev, mid)
        self.vitezna.setCurrentIndex(
            self.vitezna.findData(nastaveni.id_vitezne_melodie))
        self.vitezna.setAccessibleName("Vítězná melodie")
        self.vitezna.setAccessibleDescription(
            "Melodie, která se přehraje po správném zopakování sekvence.")
        pop_vitezna = QLabel("Vítězná melodie:", self)
        pop_vitezna.setBuddy(self.vitezna)
        form.addRow(pop_vitezna, self.vitezna)

        # --- Informace o přizpůsobení melodií ---------------------------
        self._info = QLabel(self)
        self._info.setWordWrap(True)
        self._info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._info.setAccessibleName("Informace o melodiích pro tóninu")
        hlavni.addWidget(self._info)

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

        self.tonina.currentIndexChanged.connect(self._aktualizuj_info)
        self.smutna.currentIndexChanged.connect(self._aktualizuj_info)
        self.vitezna.currentIndexChanged.connect(self._aktualizuj_info)
        self._aktualizuj_info()

        self.setTabOrder(self.tonina, self.oktava)
        self.setTabOrder(self.oktava, self.pokusy)
        self.setTabOrder(self.pokusy, self.delka)
        self.setTabOrder(self.delka, self.interval)
        self.setTabOrder(self.interval, self.smutna)
        self.setTabOrder(self.smutna, self.vitezna)

    # ------------------------------------------------------------------

    def _aktualizuj_info(self) -> None:
        """Popíše, odkud se melodie pro vybranou tóninu vezme."""
        tonina = self.tonina.currentData()
        casti = []
        for druh, combo in ((melodies.DRUH_SMUTNA, self.smutna),
                            (melodies.DRUH_VITEZNA, self.vitezna)):
            volba = melodies.ziskej_melodii(tonina, druh, combo.currentData())
            zdroj = {"individualni": "individuální definice",
                     "transpozice": "automatická transpozice",
                     "zalozni": "záložní náhrada"}.get(volba.zdroj, volba.zdroj)
            casti.append(f"{volba.melodie.nazev}: {zdroj}")
            if volba.varovani:
                casti.append(f"  Pozn.: {volba.varovani}")
        text = ("Melodie pro tóninu " + theory.POPISKY_TONIN[tonina]
                + " — " + "; ".join(casti) + ".")
        self._info.setText(text)

    # ------------------------------------------------------------------

    def hodnoty(self) -> dict:
        """Validované hodnoty z dialogu."""
        hodnoty = {
            "tonina": self.tonina.currentData(),
            "oktava": int(self.oktava.currentData()),
            "pocet_pokusu": int(self.pokusy.value()),
            "delka_sekvence": int(self.delka.value()),
            "interval_statistik": int(self.interval.value()),
            "id_smutne_melodie": self.smutna.currentData(),
            "id_vitezne_melodie": self.vitezna.currentData(),
        }
        # Kontrola rozsahů (i když spinboxy je hlídají).
        if not 2 <= hodnoty["delka_sekvence"] <= 12:
            raise ValueError("Délka sekvence musí být 2–12.")
        if not 1 <= hodnoty["pocet_pokusu"] <= 10:
            raise ValueError("Počet pokusů musí být 1–10.")
        if hodnoty["interval_statistik"] < 1:
            raise ValueError("Interval statistik musí být kladné celé číslo.")
        return hodnoty
