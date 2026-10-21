"""Správce vlastních melodií — tvorba, úprava, mazání, zkušební ukázka.

Uživatel zde vytvoří a upraví melodii BEZ zásahu do zdrojového kódu:
- základní údaje (název, druh, tempo, mezertonová pauza, příznak
  tónů mimo stupnici),
- seznam tónů (název, délka, pauza) s pořadím,
- zkušební přehrání ve zvolené tónině (přehrává hlavní okno přes
  worker — dialog jen požádá),
- uložení se ihned zapíše do JSON souboru přes ``uloziste``.

Všechny ovládací prvky mají české názvy, popisy a popisky se
``setBuddy`` — ovladatelné klávesnicí s odečítačem obrazovky.
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
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
)

import melodies
import theory
import uloziste

DRUHY_POPISKY = {
    melodies.DRUH_SMUTNA: "Smutná",
    melodies.DRUH_VITEZNA: "Vítězná",
}

# Výchozí mezertonová pauza nové melodie (sekundy).
VYCHOZI_MEZERTONOVA_PAUZA = 0.12


def _popis_druhu(druh: str) -> str:
    return DRUHY_POPISKY.get(druh, druh)


class UpravMelodiiDialog(QDialog):
    """Editor jedné vlastní melodie (nové i existující)."""

    def __init__(self, melodie: melodies.Melodie | None = None, parent=None, *,
                 tonina: str = "C",
                 prehravac=None,
                 oznamovac=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Úprava vlastní melodie")
        self.setModal(True)
        self.setAccessibleDescription(
            "Údaje vlastní melodie: název, druh, tempo, tóny a zkušební "
            "přehrání.")
        self._prehravac = prehravac        # (melodie, tonina) -> bool
        self._oznamovac = oznamovac
        self._id = (melodie.id if melodie is not None
                    else melodies.nova_id_melodie())

        hlavni = QVBoxLayout(self)

        # --- Základní údaje ---------------------------------------------
        zakladni = QGroupBox("Základní údaje", self)
        zakladni.setAccessibleName("Základní údaje melodie")
        lay_z = QVBoxLayout(zakladni)
        form_z = QFormLayout()
        form_z.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        lay_z.addLayout(form_z)

        self.nazev = QLineEdit(self)
        self.nazev.setAccessibleName("Název melodie")
        self.nazev.setAccessibleDescription(
            "Český název, který se zobrazí ve výběru melodií.")
        pop_nazev = QLabel("Název:", self)
        pop_nazev.setBuddy(self.nazev)
        form_z.addRow(pop_nazev, self.nazev)

        self.druh = QComboBox(self)
        for druh in melodies.DRUHY:
            self.druh.addItem(_popis_druhu(druh), druh)
        self.druh.setAccessibleName("Druh melodie")
        self.druh.setAccessibleDescription(
            "Smutná hraje při chybě, vítězná po správném zopakování.")
        pop_druh = QLabel("Druh:", self)
        pop_druh.setBuddy(self.druh)
        form_z.addRow(pop_druh, self.druh)

        self.tempo = QSpinBox(self)
        self.tempo.setRange(20, 240)
        self.tempo.setSingleStep(5)
        self.tempo.setAccessibleName("Tempo")
        self.tempo.setAccessibleDescription(
            "Údery za minutu. Vyšší číslo znamená rychlejší melodii.")
        pop_tempo = QLabel("Tempo (údery za minutu):", self)
        pop_tempo.setBuddy(self.tempo)
        form_z.addRow(pop_tempo, self.tempo)

        self.pauza = QDoubleSpinBox(self)
        self.pauza.setRange(0.0, 2.0)
        self.pauza.setSingleStep(0.05)
        self.pauza.setDecimals(2)
        self.pauza.setAccessibleName("Mezertonová pauza")
        self.pauza.setAccessibleDescription(
            "Klid mezi tóny v sekundách, od 0 do 2.")
        pop_pauza = QLabel("Mezertonová pauza (sekundy):", self)
        pop_pauza.setBuddy(self.pauza)
        form_z.addRow(pop_pauza, self.pauza)

        self.mimo_stupnici = QCheckBox(
            "Povolit tóny mimo stupnici tóniny", self)
        self.mimo_stupnici.setAccessibleDescription(
            "Bez zaškrtnutí se melodie odmítne, pokud některý tón "
            "nepatří do durové tóniny.")
        form_z.addRow(self.mimo_stupnici)
        hlavni.addWidget(zakladni)

        # --- Tóny --------------------------------------------------------
        skupina_tonu = QGroupBox("Tóny melodie", self)
        skupina_tonu.setAccessibleName("Tóny melodie")
        lay_t = QVBoxLayout(skupina_tonu)

        self.tony_seznam = QListWidget(self)
        self.tony_seznam.setAccessibleName("Seznam tónů melodie")
        self.tony_seznam.setAccessibleDescription(
            "Tóny v pořadí, v jakém se přehrají. Šipkami vyberete tón "
            "pro úpravu nebo odebrání.")
        lay_t.addWidget(self.tony_seznam)

        form_t = QFormLayout()
        form_t.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        lay_t.addLayout(form_t)

        self.ton_nazev = QLineEdit(self)
        self.ton_nazev.setAccessibleName("Tón")
        self.ton_nazev.setAccessibleDescription(
            "Český název tónu včetně oktávy, například C4, Fis4, B3, H5.")
        pop_ton = QLabel("Tón:", self)
        pop_ton.setBuddy(self.ton_nazev)
        form_t.addRow(pop_ton, self.ton_nazev)

        self.ton_delka = QDoubleSpinBox(self)
        self.ton_delka.setRange(0.125, 8.0)
        self.ton_delka.setSingleStep(0.125)
        self.ton_delka.setDecimals(3)
        self.ton_delka.setAccessibleName("Délka tónu")
        self.ton_delka.setAccessibleDescription(
            "Délka tónu v taktech. 1 je čtvrťová nota, 0,5 polovina.")
        pop_delka = QLabel("Délka v taktech:", self)
        pop_delka.setBuddy(self.ton_delka)
        form_t.addRow(pop_delka, self.ton_delka)

        self.ton_pauza = QDoubleSpinBox(self)
        self.ton_pauza.setRange(0.0, 8.0)
        self.ton_pauza.setSingleStep(0.125)
        self.ton_pauza.setDecimals(3)
        self.ton_pauza.setAccessibleName("Pauza po tónu")
        self.ton_pauza.setAccessibleDescription(
            "Klid po tomto tónu v taktech, navíc k mezertonové pauze.")
        pop_ton_pauza = QLabel("Pauza po tónu v taktech:", self)
        pop_ton_pauza.setBuddy(self.ton_pauza)
        form_t.addRow(pop_ton_pauza, self.ton_pauza)

        radky_tonu = QHBoxLayout()
        self.tlacitko_pridat = QPushButton("Přidat tón", self)
        self.tlacitko_pridat.setAccessibleName("Přidat tón")
        self.tlacitko_pridat.setAccessibleDescription(
            "Přidá tón z polí na konec seznamu.")
        self.tlacitko_pridat.clicked.connect(self._pridej_ton)
        radky_tonu.addWidget(self.tlacitko_pridat)

        self.tlacitko_nahradit = QPushButton("Nahradit vybraný tón", self)
        self.tlacitko_nahradit.setAccessibleName("Nahradit vybraný tón")
        self.tlacitko_nahradit.setAccessibleDescription(
            "Přepíše vybraný tón v seznamu hodnotami z polí.")
        self.tlacitko_nahradit.clicked.connect(self._nahrad_ton)
        radky_tonu.addWidget(self.tlacitko_nahradit)

        self.tlacitko_odebrat = QPushButton("Odebrat vybraný tón", self)
        self.tlacitko_odebrat.setAccessibleName("Odebrat vybraný tón")
        self.tlacitko_odebrat.setAccessibleDescription(
            "Smaže vybraný tón ze seznamu.")
        self.tlacitko_odebrat.clicked.connect(self._odeber_ton)
        radky_tonu.addWidget(self.tlacitko_odebrat)
        lay_t.addLayout(radky_tonu)

        radky_poradi = QHBoxLayout()
        self.tlacitko_vys = QPushButton("Přesunout výš", self)
        self.tlacitko_vys.setAccessibleName("Přesunout tón výš")
        self.tlacitko_vys.setAccessibleDescription(
            "Posune vybraný tón o jedno místo blíž začátku melodie.")
        self.tlacitko_vys.clicked.connect(lambda: self._presun(+1))
        radky_poradi.addWidget(self.tlacitko_vys)

        self.tlacitko_niz = QPushButton("Přesunout níž", self)
        self.tlacitko_niz.setAccessibleName("Přesunout tón níž")
        self.tlacitko_niz.setAccessibleDescription(
            "Posune vybraný tón o jedno místo blíž konci melodie.")
        self.tlacitko_niz.clicked.connect(lambda: self._presun(-1))
        radky_poradi.addWidget(self.tlacitko_niz)
        lay_t.addLayout(radky_poradi)

        hlavni.addWidget(skupina_tonu)

        # --- Tónina ukázky a stav ---------------------------------------
        form_dopl = QFormLayout()
        self.tonina_ukazky = QComboBox(self)
        for klic in theory.PORADI_TONIN:
            self.tonina_ukazky.addItem(theory.POPISKY_TONIN[klic], klic)
        self.tonina_ukazky.setCurrentIndex(
            self.tonina_ukazky.findData(tonina)
            if self.tonina_ukazky.findData(tonina) >= 0 else 0)
        self.tonina_ukazky.setAccessibleName("Tónina ukázky")
        self.tonina_ukazky.setAccessibleDescription(
            "Tónina, ve které se přehraje zkušební ukázka. "
            "Na uloženou melodii nemá vliv — ta se ukládá v tónině C "
            "a při hře se sama přeloží.")
        pop_ukazka = QLabel("Tónina ukázky:", self)
        pop_ukazka.setBuddy(self.tonina_ukazky)
        form_dopl.addRow(pop_ukazka, self.tonina_ukazky)
        hlavni.addLayout(form_dopl)

        self._stav = QLabel(self)
        self._stav.setWordWrap(True)
        self._stav.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._stav.setAccessibleName("Stav úpravy melodie")
        hlavni.addWidget(self._stav)

        # --- Tlačítka -----------------------------------------------------
        self.tlacitko_ukazka = QPushButton("Přehrát ukázku", self)
        self.tlacitko_ukazka.setAccessibleName("Přehrát ukázku melodie")
        self.tlacitko_ukazka.setAccessibleDescription(
            "Přehraje melodii z polí (zatím neuloženou) ve zvolené "
            "tónině. Na hru to nemá vliv.")
        self.tlacitko_ukazka.clicked.connect(self._prehrat_ukazku)
        self.tlacitko_ukazka.setEnabled(prehravac is not None)
        hlavni.addWidget(self.tlacitko_ukazka)

        tlacitka = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        b_ulozit = tlacitka.button(QDialogButtonBox.StandardButton.Save)
        b_ulozit.setText("Uložit")
        b_ulozit.setAccessibleDescription(
            "Zkontroluje melodii a uloží ji do souboru.")
        b_zrusit = tlacitka.button(QDialogButtonBox.StandardButton.Cancel)
        b_zrusit.setText("Zrušit")
        # Enter v textových polích nesmí náhodně uložit celou melodii.
        b_ulozit.setAutoDefault(False)
        b_ulozit.setDefault(False)
        b_zrusit.setAutoDefault(False)
        b_zrusit.setDefault(False)
        tlacitka.setAccessibleName("Ovládací tlačítka úpravy melodie")
        tlacitka.accepted.connect(self._ulozit)
        tlacitka.rejected.connect(self.reject)
        hlavni.addWidget(tlacitka)

        self.tony_seznam.currentRowChanged.connect(self._polozka_zmenena)

        # --- Naplnění z existující melodie -------------------------------
        if melodie is not None:
            self.nazev.setText(melodie.nazev)
            index = self.druh.findData(melodie.druh)
            self.druh.setCurrentIndex(index if index >= 0 else 0)
            self.tempo.setValue(int(round(melodie.tempo_bpm)))
            self.pauza.setValue(melodie.mezertonova_pauza_s)
            self.mimo_stupnici.setChecked(melodie.povolit_mimo_stupnici)
            for ton in melodie.tony:
                self.tony_seznam.addItem(self._text_polozky(ton))
        else:
            self.tempo.setValue(100)
            self.pauza.setValue(VYCHOZI_MEZERTONOVA_PAUZA)

        self.setTabOrder(self.nazev, self.druh)
        self.setTabOrder(self.druh, self.tempo)
        self.setTabOrder(self.tempo, self.pauza)
        self.setTabOrder(self.pauza, self.mimo_stupnici)
        self.setTabOrder(self.mimo_stupnici, self.tony_seznam)
        self.setTabOrder(self.tony_seznam, self.ton_nazev)
        self.setTabOrder(self.ton_nazev, self.ton_delka)
        self.setTabOrder(self.ton_delka, self.ton_pauza)
        self.setTabOrder(self.ton_pauza, self.tlacitko_pridat)
        # Počáteční stav tlačítek tónů (bez výběru jsou vypnutá).
        self._polozka_zmenena(self.tony_seznam.currentRow())

    @property
    def id_melodie(self) -> str:
        """ID, které editor upravuje nebo vytvoří."""
        return self._id

    # ------------------------------------------------------------------
    # Pomocné
    # ------------------------------------------------------------------

    @staticmethod
    def _text_polozky(ton: melodies.Ton) -> str:
        return f"{ton.nazev} — délka {ton.delka:g}, pauza {ton.pauza:g}"

    def _zobraz(self, text: str, hlasite: bool = True) -> None:
        self._stav.setText(text)
        if hlasite and self._oznamovac is not None:
            self._oznamovac.oznam(text)

    def _polozka_zmenena(self, radek: int) -> None:
        """Vybraný tón se načte do polí (připraveno k úpravě)."""
        ma_vyber = 0 <= radek < self.tony_seznam.count()
        self.tlacitko_nahradit.setEnabled(ma_vyber)
        self.tlacitko_odebrat.setEnabled(ma_vyber)
        self.tlacitko_vys.setEnabled(ma_vyber and radek > 0)
        self.tlacitko_niz.setEnabled(
            ma_vyber and radek < self.tony_seznam.count() - 1)
        if not ma_vyber:
            return
        ton = self._ton_z_polozky(radek)
        if ton is not None:
            self.ton_nazev.setText(ton.nazev)
            self.ton_delka.setValue(ton.delka)
            self.ton_pauza.setValue(ton.pauza)

    @staticmethod
    def _ton_z_polozky(text: str) -> melodies.Ton | None:
        try:
            nazev, zbytek = text.split(" — ", 1)
            delka_s, pauza_s = zbytek.split(", ", 1)
            return melodies.Ton(
                nazev=nazev,
                delka=float(delka_s.removeprefix("délka ")),
                pauza=float(pauza_s.removeprefix("pauza ")),
            )
        except (ValueError, AttributeError):
            return None

    def _ton_z_poli(self) -> melodies.Ton:
        """Sestaví a zkontroluje tón z polí; ValueError s českým textem."""
        nazev = self.ton_nazev.text().strip()
        if not nazev:
            raise ValueError("Napište název tónu, například C4.")
        try:
            theory.midi_z_nazvu(nazev)
        except ValueError as e:
            # theory už hlásí srozumitelně česky („Neplatný název tónu…“).
            raise ValueError(str(e)) from None
        return melodies.Ton(
            nazev=nazev,
            delka=float(self.ton_delka.value()),
            pauza=float(self.ton_pauza.value()),
        )

    # ------------------------------------------------------------------
    # Práce s tóny
    # ------------------------------------------------------------------

    def _pridej_ton(self) -> None:
        try:
            ton = self._ton_z_poli()
        except ValueError as e:
            self._zobraz(f"Tón nebyl přidán: {e}")
            self.ton_nazev.setFocus()
            return
        self.tony_seznam.addItem(self._text_polozky(ton))
        self.tony_seznam.setCurrentRow(self.tony_seznam.count() - 1)
        self._zobraz(f"Přidán tón {ton.nazev}. "
                     f"Celkem tónů: {self.tony_seznam.count()}.",
                     hlasite=False)
        self.ton_nazev.clear()
        self.ton_nazev.setFocus()

    def _nahrad_ton(self) -> None:
        radek = self.tony_seznam.currentRow()
        if not 0 <= radek < self.tony_seznam.count():
            self._zobraz("Nejdřív vyberte tón v seznamu.")
            return
        try:
            ton = self._ton_z_poli()
        except ValueError as e:
            self._zobraz(f"Tón nebyl nahrazen: {e}")
            self.ton_nazev.setFocus()
            return
        self.tony_seznam.item(radek).setText(self._text_polozky(ton))
        self.tony_seznam.setCurrentRow(radek)
        self._zobraz(f"Tón na místě {radek + 1} nahrazen za {ton.nazev}.",
                     hlasite=False)
        self.ton_nazev.setFocus()

    def _odeber_ton(self) -> None:
        radek = self.tony_seznam.currentRow()
        if not 0 <= radek < self.tony_seznam.count():
            self._zobraz("Nejdřív vyberte tón v seznamu.")
            return
        odstraneny = self.tony_seznam.takeItem(radek)
        nova_volba = min(radek, self.tony_seznam.count() - 1)
        self.tony_seznam.setCurrentRow(nova_volba)
        self._zobraz(f"Odebrán tón {odstraneny.text().split(' — ')[0]}. "
                     f"Zbývá tónů: {self.tony_seznam.count()}.",
                     hlasite=False)
        self.tlacitko_pridat.setFocus()

    def _presun(self, smer: int) -> None:
        radek = self.tony_seznam.currentRow()
        cil = radek - smer   # výš = menší index
        if not 0 <= radek < self.tony_seznam.count() or not 0 <= cil < self.tony_seznam.count():
            return
        polozka = self.tony_seznam.takeItem(radek)
        self.tony_seznam.insertItem(cil, polozka)
        self.tony_seznam.setCurrentRow(cil)
        self._zobraz(f"Tón je teď na místě {cil + 1} z "
                     f"{self.tony_seznam.count()}.", hlasite=False)

    # ------------------------------------------------------------------
    # Sestavení, ukázka, uložení
    # ------------------------------------------------------------------

    def _sesbiraj(self, pouze_ukazka: bool) -> tuple[melodies.Melodie | None, list[str]]:
        """Sestaví melodii z polí. Vrací (melodie, chyby)."""
        chyby: list[str] = []

        nazev = self.nazev.text().strip()
        if not nazev and not pouze_ukazka:
            chyby.append("melodie musí mít název")

        tony: list[melodies.Ton] = []
        for i in range(self.tony_seznam.count()):
            ton = self._ton_z_polozky(self.tony_seznam.item(i).text())
            if ton is None:
                chyby.append(f"tón na místě {i + 1} se nepodařil přečíst")
                continue
            tony.append(ton)
        if not tony:
            chyby.append("melodie neobsahuje žádné tóny — přidejte alespoň jeden")

        melodie = melodies.Melodie(
            id=self._id,
            nazev=nazev or "Bez názvu",
            tony=tuple(tony),
            tempo_bpm=float(self.tempo.value()),
            mezertonova_pauza_s=float(self.pauza.value()),
            povolit_mimo_stupnici=bool(self.mimo_stupnici.isChecked()),
            druh=str(self.druh.currentData()),
        )
        if chyby:
            return None, chyby
        chyby_m, varovani = melodies.over_pred_ulozenim(melodie)
        if chyby_m:
            return None, chyby_m
        if pouze_ukazka:
            return melodie, [f"Upozornění: {v}" for v in varovani]
        return melodie, [f"Upozornění: {v}" for v in varovani]

    def _prehrat_ukazku(self) -> None:
        if self._prehravac is None:
            self._zobraz("Zkušební přehrání není k dispozici.")
            return
        melodie, chyby = self._sesbiraj(pouze_ukazka=True)
        chyby_skutecne = [c for c in chyby if not c.startswith("Upozornění: ")]
        if melodie is None:
            self._zobraz("Ukázku nelze přehrát: " + "; ".join(chyby_skutecne))
            return
        tonina = str(self.tonina_ukazky.currentData())
        spusteno = self._prehravac(melodie, tonina)
        if spusteno:
            doplneni = " ".join(
                c.removeprefix("Upozornění: ") for c in chyby if c.startswith("Upozornění: "))
            self._stav.setText(
                f"Přehrávám ukázku melodie v tónině "
                f"{theory.POPISKY_TONIN[tonina]}."
                + (f" Pozn.: {doplneni}" if doplneni else ""))
        else:
            self._stav.setText("Ukázku se teď nepodařilo spustit — "
                               "podívejte se na hlášení v okně hry.")

    def _ulozit(self) -> None:
        melodie, chyby = self._sesbiraj(pouze_ukazka=False)
        if melodie is None:
            self._zobraz("Melodii nelze uložit: " + "; ".join(chyby))
            return
        varovani = [c.removeprefix("Upozornění: ") for c in chyby]

        stara = melodies.VLASTNI_MELODIE.get(self._id)
        try:
            melodies.uloz_vlastni_melodie(melodie)
        except ValueError as e:
            self._zobraz(f"Melodii nelze uložit: {e}")
            return
        try:
            uloziste.uloz_vlastni_melodie()
        except (OSError, ValueError) as e:
            # Disk zůstává konzistentní s pamětí — vrátíme starý stav.
            if stara is None:
                melodies.VLASTNI_MELODIE.pop(self._id, None)
            else:
                melodies.VLASTNI_MELODIE[self._id] = stara
            self._zobraz(f"Melodii se nepodařilo zapsat do souboru: {e}. "
                         "Zkuste to prosím znovu.")
            return

        zprava = f"Melodie „{melodie.nazev}“ byla uložena."
        if varovani:
            zprava += " Pozn.: " + "; ".join(varovani)
        if self._oznamovac is not None:
            self._oznamovac.oznam(zprava)
        self.accept()


class SpravceMelodiDialog(QDialog):
    """Seznam vlastních melodií + vytvoření, úprava a smazání."""

    def __init__(self, parent=None, *, prehravac=None, oznamovac=None,
                 tonina: str = "C") -> None:
        super().__init__(parent)
        self.setWindowTitle("Vlastní melodie")
        self.setModal(True)
        self.setAccessibleDescription(
            "Seznam vlastních melodií s tlačítky pro vytvoření, úpravu "
            "a smazání.")
        self._prehravac = prehravac
        self._oznamovac = oznamovac
        self._tonina = tonina

        hlavni = QVBoxLayout(self)

        nadpis = QLabel("Vlastní melodie")
        nadpis.setAccessibleName("Vlastní melodie, nadpis")
        font = nadpis.font()
        font.setBold(True)
        nadpis.setFont(font)
        hlavni.addWidget(nadpis)

        popis = QLabel(
            "Melodie se ukládají trvale do souboru a objeví se ve "
            "výběru smutné a vítězné melodie v nastavení.", self)
        popis.setWordWrap(True)
        popis.setAccessibleName("Jak vlastní melodie fungují")
        hlavni.addWidget(popis)

        prostredni = QHBoxLayout()
        self.seznam = QListWidget(self)
        self.seznam.setAccessibleName("Seznam vlastních melodií")
        self.seznam.setAccessibleDescription(
            "Vlastní melodie. Šipkami vyberete melodii, Enter ji otevře "
            "k úpravě.")
        self.seznam.itemDoubleClicked.connect(
            lambda _item: self._uprav_vybranou())
        prostredni.addWidget(self.seznam, stretch=1)

        tlacitka = QVBoxLayout()
        self.tlacitko_nova = QPushButton("Nová melodie", self)
        self.tlacitko_nova.setAccessibleName("Nová melodie")
        self.tlacitko_nova.setAccessibleDescription(
            "Otevře prázdný editor nové vlastní melodie.")
        self.tlacitko_nova.clicked.connect(self._nova)
        tlacitka.addWidget(self.tlacitko_nova)

        self.tlacitko_upravit = QPushButton("Upravit vybranou", self)
        self.tlacitko_upravit.setAccessibleName("Upravit vybranou melodii")
        self.tlacitko_upravit.setAccessibleDescription(
            "Otevře vybranou melodii v editoru.")
        self.tlacitko_upravit.clicked.connect(self._uprav_vybranou)
        tlacitka.addWidget(self.tlacitko_upravit)

        self.tlacitko_smazat = QPushButton("Smazat vybranou", self)
        self.tlacitko_smazat.setAccessibleName("Smazat vybranou melodii")
        self.tlacitko_smazat.setAccessibleDescription(
            "Smaže vybranou melodii. Pokud byla právě tato melodie "
            "nastavená ve hře, vrátí se výchozí.")
        self.tlacitko_smazat.clicked.connect(self._smaz_vybranou)
        tlacitka.addWidget(self.tlacitko_smazat)

        tlacitka.addStretch(1)
        prostredni.addLayout(tlacitka)
        hlavni.addLayout(prostredni)

        self._pocet = QLabel(self)
        self._pocet.setAccessibleName("Počet vlastních melodií")
        hlavni.addWidget(self._pocet)

        self._stav = QLabel(self)
        self._stav.setWordWrap(True)
        self._stav.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._stav.setAccessibleName("Stav správce melodií")
        hlavni.addWidget(self._stav)

        tlacitka_dol = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, parent=self)
        b_zavrit = tlacitka_dol.button(QDialogButtonBox.StandardButton.Close)
        b_zavrit.setText("Zavřít")
        tlacitka_dol.setAccessibleName("Ovládací tlačítka správce melodií")
        tlacitka_dol.rejected.connect(self.reject)
        tlacitka_dol.accepted.connect(self.accept)
        hlavni.addWidget(tlacitka_dol)

        self.seznam.currentRowChanged.connect(self._vyber_zmenen)
        self._obnov_seznam()

        self.setTabOrder(self.seznam, self.tlacitko_nova)
        self.setTabOrder(self.tlacitko_nova, self.tlacitko_upravit)
        self.setTabOrder(self.tlacitko_upravit, self.tlacitko_smazat)
        self.setTabOrder(self.tlacitko_smazat, tlacitka_dol)

    # ------------------------------------------------------------------

    def _vybrana_id(self) -> str | None:
        radek = self.seznam.currentRow()
        if not 0 <= radek < self.seznam.count():
            return None
        polozka = self.seznam.item(radek)
        id_melodie = polozka.data(Qt.ItemDataRole.UserRole)
        return str(id_melodie)

    def _vyber_zmenen(self, radek: int) -> None:
        ma_vyber = 0 <= radek < self.seznam.count()
        self.tlacitko_upravit.setEnabled(ma_vyber)
        self.tlacitko_smazat.setEnabled(ma_vyber)

    def _obnov_seznam(self, zachovat_id: str | None = None) -> None:
        """Znovu načte seznam (po vytvoření, úpravě nebo smazání)."""
        if zachovat_id is None:
            zachovat_id = self._vybrana_id()
        self.seznam.clear()
        for melodie in melodies.vlastni_melodie():
            polozka = QListWidgetItem(
                f"{melodie.nazev} ({_popis_druhu(melodie.druh).lower()})")
            polozka.setData(Qt.ItemDataRole.UserRole, melodie.id)
            self.seznam.addItem(polozka)
        self._pocet.setText(
            f"Počet vlastních melodií: {self.seznam.count()}.")
        index = -1
        if zachovat_id is not None:
            for i in range(self.seznam.count()):
                if self.seznam.item(i).data(Qt.ItemDataRole.UserRole) == zachovat_id:
                    index = i
                    break
        self.seznam.setCurrentRow(index if index >= 0 else
                                  (0 if self.seznam.count() else -1))
        # Signál u změny -1 → -1 nevzniká — stav vypnutí zajistíme ručně.
        self._vyber_zmenen(self.seznam.currentRow())

    # ------------------------------------------------------------------

    def _nova(self) -> None:
        self._otevri_editor(None)

    def _uprav_vybranou(self) -> None:
        id_melodie = self._vybrana_id()
        if id_melodie is None:
            self._stav.setText("Nejdřív vyberte melodii v seznamu.")
            return
        melodie = melodies.VLASTNI_MELODIE.get(id_melodie)
        if melodie is None:
            self._stav.setText("Vybraná melodie už neexistuje.")
            self._obnov_seznam()
            return
        self._otevri_editor(melodie)

    def _otevri_editor(self, melodie: melodies.Melodie | None) -> None:
        editor = UpravMelodiiDialog(
            melodie, self,
            tonina=self._tonina,
            prehravac=self._prehravac,
            oznamovac=self._oznamovac,
        )
        if editor.exec() == QDialog.DialogCode.Accepted:
            self._obnov_seznam(zachovat_id=editor.id_melodie)
            ulozena = melodies.VLASTNI_MELODIE.get(editor.id_melodie)
            if ulozena is not None:
                self._stav.setText(f"Uloženo: {ulozena.nazev}.")
        self.activateWindow()

    def _smaz_vybranou(self) -> None:
        id_melodie = self._vybrana_id()
        if id_melodie is None:
            self._stav.setText("Nejdřív vyberte melodii v seznamu.")
            return
        melodie = melodies.VLASTNI_MELODIE.get(id_melodie)
        if melodie is None:
            self._obnov_seznam()
            return

        odpoved = QMessageBox.question(
            self,
            "Smazat melodii",
            f"Opravdu smazat melodii „{melodie.nazev}“? "
            "Smaže se i ze souboru.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if odpoved != QMessageBox.StandardButton.Yes:
            self._stav.setText("Mazání zrušeno.")
            return

        melodies.smaz_vlastni_melodie(id_melodie)
        try:
            uloziste.uloz_vlastni_melodie()
        except (OSError, ValueError) as e:
            # Disk zůstává konzistentní s pamětí.
            melodies.VLASTNI_MELODIE[id_melodie] = melodie
            self._stav.setText(
                f"Melodii se nepodařilo smazat ze souboru: {e}.")
            return

        self._obnov_seznam(zachovat_id=None)
        zprava = f"Melodie „{melodie.nazev}“ smazána."
        self._stav.setText(zprava)
        if self._oznamovac is not None:
            self._oznamovac.oznam(zprava)
