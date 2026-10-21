"""Přístupný dialog statistik — interval + celkové souhrnně."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)


def _text_statistik(stat) -> str:
    return (
        f"Správně zahrané tóny: {stat.spravne_tony}. "
        f"Chybně zahrané tóny: {stat.chybne_tony}. "
        f"Úspěšná kola: {stat.uspesna_kola}. "
        f"Neúspěšná kola: {stat.neuspesna_kola}. "
        f"Dokončená kola celkem: {stat.dokoncena_kola}."
    )


class StatsDialog(QDialog):
    """Zobrazí výsledky za aktuální interval i celkové od spuštění."""

    def __init__(self, interval, celkem, obdobi: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Statistiky hry")
        self.setModal(True)
        self.setAccessibleDescription(
            "Přehled výsledků za aktuální statistický interval "
            "a celkové výsledky od spuštění hry.")

        hlavni = QVBoxLayout(self)

        # --- Interval -----------------------------------------------------
        skupina_int = QGroupBox("Statistiky za aktuální interval", self)
        skupina_int.setAccessibleName(
            "Statistiky za aktuální statistický interval")
        lay_int = QVBoxLayout(skupina_int)
        text_obdobi = QLabel(obdobi, skupina_int)
        text_obdobi.setWordWrap(True)
        text_obdobi.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        text_obdobi.setAccessibleName("Období intervalu")
        lay_int.addWidget(text_obdobi)
        self._label_interval = QLabel(_text_statistik(interval), skupina_int)
        self._label_interval.setWordWrap(True)
        self._label_interval.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label_interval.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._label_interval.setAccessibleName("Výsledky intervalu")
        lay_int.addWidget(self._label_interval)
        hlavni.addWidget(skupina_int)

        # --- Celkové ------------------------------------------------------
        skupina_celk = QGroupBox("Celkové statistiky", self)
        skupina_celk.setAccessibleName("Celkové statistiky od spuštění hry")
        lay_celk = QVBoxLayout(skupina_celk)
        self._label_celkem = QLabel(_text_statistik(celkem), skupina_celk)
        self._label_celkem.setWordWrap(True)
        self._label_celkem.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label_celkem.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._label_celkem.setAccessibleName("Celkové výsledky")
        lay_celk.addWidget(self._label_celkem)
        hlavni.addWidget(skupina_celk)

        # --- Tlačítka ------------------------------------------------------
        tlacitka = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=self)
        tlacitka.button(QDialogButtonBox.StandardButton.Ok).setText("Zavřít")
        tlacitka.setAccessibleName("Ovládací tlačítka statistik")
        tlacitka.accepted.connect(self.accept)
        hlavni.addWidget(tlacitka)

        self.setTabOrder(self._label_interval, self._label_celkem)
        self.setTabOrder(self._label_celkem,
                         tlacitka.button(QDialogButtonBox.StandardButton.Ok))

        # Výchozí fokus na výsledky intervalu — odečítač hned přečte výsledky.
        self._label_interval.setFocus()

    # Pomocné pro testy -------------------------------------------------

    @property
    def text_intervalu(self) -> str:
        return self._label_interval.text()

    @property
    def text_celkem(self) -> str:
        return self._label_celkem.text()
