"""Průvodce rytmem a fanfárami — přístupný dialog (PyQt6, česky).

Dialog vysvětlí tempo (BPM), délky tónů v dobách a pauzy, přepočte
zadané doby na sekundy, nabídne krátké rytmické příklady a tři
originální vzory fanfár k vyzkoušení i úpravě.

Zásady:
- vzory se upravují VŽDY přes kopii (``VZOROVE_FANFARY`` zůstávají
  nedotčené), otevření v editoru vždy přidělí nové ID,
- veškeré přehrávání jde přes worker hlavního okna
  (``prehraj_kroky``) — nikdy ne v hlavním vlákně GUI,
- při zavření dialogu se běžící ukázka kooperativně přeruší
  (``zastav_ukazku``), fokus se po ukázce vrací do tohoto dialogu,
- všechny ovládací prvky mají české přístupné názvy a popisy,
  hodnoty se zadávají přímo z klávesnice (žádné posuvníky).

Vzory se přehrávají v tónině C, ve které jsou uložené (stejně jako
vlastní melodie před transpozicí).
"""

from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

import melodies
import pruvodce

# ID položky „melodie přinesená z editoru“ ve výběru vzorů.
_ID_EDITORU = "_editor"

# Popisek s upozorněním na původ vzorů.
TEXT_PUVOD_VZORU = (
    "Vzory jsou originální, volně vymyšlené ukázky postupu fanfáry — "
    "nejde o oficiální znělky žádných hokejových ani jiných klubů. "
    "Upravují se vždy přes kopii, původní vzor zůstane beze změny."
)

TEXT_VYSVETLENI = (
    "Tempo (BPM = beats per minute, údery za minutu) určuje, jak rychle "
    "se hraje. 120 úderů za minutu znamená dva údery za sekundu. "
    "Z tempa se počítá délka jedné doby: 60 děleno tempem. Při 120 BPM "
    "je doba dlouhá 0,500 s, při 90 BPM 0,667 s.\n"
    "Délka tónu se zapisuje v DOBÁCH: 1 = celá doba (čtvrťová nota), "
    "0,5 = polovina doby (osminka), 0,25 = čtvrtina doby, 2 = dvě doby. "
    "Délka v sekundách = délka v dobách × (60 ÷ tempo).\n"
    "Pauza po tónu se zapisuje také v dobách. Navíc se vždy přičte "
    "mezertonová pauza v sekundách — ta je pevná a na tempu nezávisí. "
    "Příklad: při 120 BPM, pauze 0,5 doby a mezertonové pauze 0,12 s "
    "celková pauza činí 0,25 + 0,12 = 0,37 s."
)


def _text_polozky(ton: melodies.Ton) -> str:
    return f"{ton.nazev} — délka {ton.delka:g}, pauza {ton.pauza:g}"


class PruvodceRytmuDialog(QDialog):
    """Vysvětlení tempa a délek, rytmické příklady, vzory fanfár, poslech."""

    def __init__(self, parent=None, *,
                 prehravac=None,
                 prehravac_kroku=None,
                 zastav_ukazku=None,
                 oznamovac=None,
                 melodie: melodies.Melodie | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Průvodce rytmem a fanfárami")
        self.setModal(True)
        self.setAccessibleDescription(
            "Vysvětlení tempa, délek tónů a pauz, rytmické příklady, "
            "vzory fanfár k úpravě a zkušební přehrání rytmu i melodie.")
        self._prehravac = prehravac              # (melodie, tonina) -> bool
        self._prehravac_kroku = prehravac_kroku  # (kroky, popis) -> bool
        self._zastav_ukazku = zastav_ukazku      # () -> bool
        self._oznamovac = oznamovac
        self._melodie_editoru = melodie          # draft z editoru (volitelný)
        self._zdroj: melodies.Melodie | None = None
        self._snimek: melodies.Melodie | None = None

        hlavni = QVBoxLayout(self)

        nadpis = QLabel("Průvodce rytmem a fanfárami", self)
        nadpis.setAccessibleName("Průvodce rytmem a fanfárami, nadpis")
        font = nadpis.font()
        font.setBold(True)
        nadpis.setFont(font)
        hlavni.addWidget(nadpis)

        # --- Vysvětlení ---------------------------------------------------
        skupina_vysvetleni = QGroupBox("Jak funguje tempo a délky", self)
        skupina_vysvetleni.setAccessibleName("Jak funguje tempo a délky")
        lay_v = QVBoxLayout(skupina_vysvetleni)

        popis = QLabel(TEXT_VYSVETLENI, self)
        popis.setWordWrap(True)
        popis.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        popis.setAccessibleName("Vysvětlení tempa, dob a pauz")
        lay_v.addWidget(popis)

        form_p = QFormLayout()
        form_p.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        lay_v.addLayout(form_p)

        self.tempo = QSpinBox(self)
        self.tempo.setRange(20, 240)
        self.tempo.setSingleStep(5)
        self.tempo.setAccessibleName("Tempo")
        self.tempo.setAccessibleDescription(
            "Údery za minutu (BPM). Vyšší číslo znamená rychlejší chod, "
            "jedna doba je pak kratší. Lze zadat přímo z klávesnice.")
        pop_tempo = QLabel("Tempo (údery za minutu):", self)
        pop_tempo.setBuddy(self.tempo)
        form_p.addRow(pop_tempo, self.tempo)

        self.delka = QDoubleSpinBox(self)
        self.delka.setRange(0.125, 8.0)
        self.delka.setSingleStep(0.125)
        self.delka.setDecimals(3)
        self.delka.setAccessibleName("Délka tónu v dobách")
        self.delka.setAccessibleDescription(
            "Délka tónu v dobách, například 1 pro čtvrťovou notu "
            "nebo 0,5 pro osminku. Slouží k přepočtu na sekundy.")
        pop_delka = QLabel("Délka tónu v dobách:", self)
        pop_delka.setBuddy(self.delka)
        form_p.addRow(pop_delka, self.delka)

        self.pauza = QDoubleSpinBox(self)
        self.pauza.setRange(0.0, 8.0)
        self.pauza.setSingleStep(0.125)
        self.pauza.setDecimals(3)
        self.pauza.setAccessibleName("Pauza po tónu v dobách")
        self.pauza.setAccessibleDescription(
            "Pauza po tónu v dobách. K výsledku se navíc přičte "
            "mezertonová pauza v sekundách.")
        pop_pauza = QLabel("Pauza po tónu v dobách:", self)
        pop_pauza.setBuddy(self.pauza)
        form_p.addRow(pop_pauza, self.pauza)

        self.mezertonova = QDoubleSpinBox(self)
        self.mezertonova.setRange(0.0, 2.0)
        self.mezertonova.setSingleStep(0.05)
        self.mezertonova.setDecimals(2)
        self.mezertonova.setAccessibleName("Mezertonová pauza")
        self.mezertonova.setAccessibleDescription(
            "Klid mezi tóny v sekundách, na tempu nezávisí. Používá se "
            "i při přehrávání vybraného vzoru.")
        pop_mez = QLabel("Mezertonová pauza (sekundy):", self)
        pop_mez.setBuddy(self.mezertonova)
        form_p.addRow(pop_mez, self.mezertonova)

        self._prepoctet = QLabel(self)
        self._prepoctet.setWordWrap(True)
        self._prepoctet.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._prepoctet.setAccessibleName("Přepočet délek na sekundy")
        lay_v.addWidget(self._prepoctet)
        hlavni.addWidget(skupina_vysvetleni)

        # --- Rytmické příklady -------------------------------------------
        skupina_prikladu = QGroupBox("Rytmické příklady", self)
        skupina_prikladu.setAccessibleName("Rytmické příklady")
        lay_r = QVBoxLayout(skupina_prikladu)

        self.priklady = QListWidget(self)
        self.priklady.setAccessibleName("Seznam rytmických příkladů")
        self.priklady.setAccessibleDescription(
            "Krátké ukázkové rytmy. Šipkami vyberete příklad — "
            "jeho popis a přepočet se zobrazí pod seznamem.")
        for p in pruvodce.PRIKLADY:
            self.priklady.addItem(QListWidgetItem(p.nazev))
        lay_r.addWidget(self.priklady)

        self._popis_prikladu = QLabel(self)
        self._popis_prikladu.setWordWrap(True)
        self._popis_prikladu.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._popis_prikladu.setAccessibleName("Popis vybraného příkladu")
        lay_r.addWidget(self._popis_prikladu)
        hlavni.addWidget(skupina_prikladu)

        # --- Vzor fanfáry a jeho tóny -------------------------------------
        skupina_vzor = QGroupBox("Vzor fanfáry k úpravě", self)
        skupina_vzor.setAccessibleName("Vzor fanfáry k úpravě")
        lay_f = QVBoxLayout(skupina_vzor)

        form_v = QFormLayout()
        form_v.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        lay_f.addLayout(form_v)

        self.vzor = QComboBox(self)
        self.vzor.setAccessibleName("Vybraný vzor")
        self.vzor.setAccessibleDescription(
            "Vzor fanfáry, který se zobrazí pod seznamem a půjde "
            "upravit i přehrát. Při změně vzoru se obnoví i výchozí "
            "stav pro porovnání rytmu.")
        pop_vzor = QLabel("Vzor:", self)
        pop_vzor.setBuddy(self.vzor)
        form_v.addRow(pop_vzor, self.vzor)

        self.tony = QListWidget(self)
        self.tony.setAccessibleName("Tóny vybraného vzoru")
        self.tony.setAccessibleDescription(
            "Tóny vzoru v pořadí přehrávání, s délkou a pauzou v dobách. "
            "Šipkami vyberete tón k úpravě.")
        lay_f.addWidget(self.tony)

        form_t = QFormLayout()
        form_t.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        lay_f.addLayout(form_t)

        self.ton_delka = QDoubleSpinBox(self)
        self.ton_delka.setRange(0.125, 8.0)
        self.ton_delka.setSingleStep(0.125)
        self.ton_delka.setDecimals(3)
        self.ton_delka.setAccessibleName("Délka vybraného tónu")
        self.ton_delka.setAccessibleDescription(
            "Délka vybraného tónu v dobách, například 0,5 nebo 1.")
        pop_td = QLabel("Délka vybraného tónu v dobách:", self)
        pop_td.setBuddy(self.ton_delka)
        form_t.addRow(pop_td, self.ton_delka)

        self.ton_pauza = QDoubleSpinBox(self)
        self.ton_pauza.setRange(0.0, 8.0)
        self.ton_pauza.setSingleStep(0.125)
        self.ton_pauza.setDecimals(3)
        self.ton_pauza.setAccessibleName("Pauza po vybraném tónu")
        self.ton_pauza.setAccessibleDescription(
            "Pauza po vybraném tónu v dobách, navíc k mezertonové pauze.")
        pop_tp = QLabel("Pauza po vybraném tónu v dobách:", self)
        pop_tp.setBuddy(self.ton_pauza)
        form_t.addRow(pop_tp, self.ton_pauza)

        self.tlacitko_zmenit_ton = QPushButton("Změnit vybraný tón", self)
        self.tlacitko_zmenit_ton.setAccessibleName("Změnit vybraný tón")
        self.tlacitko_zmenit_ton.setAccessibleDescription(
            "Přepíše vybraný tón v seznamu délkou a pauzou z polí. "
            "Původní vzor se tím nemění — upravuje se pracovní kopie.")
        self.tlacitko_zmenit_ton.clicked.connect(self._zmenit_ton)
        lay_f.addWidget(self.tlacitko_zmenit_ton)

        self.tlacitko_v_editoru = QPushButton(
            "Otevřít vzor v editoru…", self)
        self.tlacitko_v_editoru.setAccessibleName(
            "Otevřít vzor v editoru")
        self.tlacitko_v_editoru.setAccessibleDescription(
            "Otevře aktuální stav vzoru v editoru vlastních melodií jako "
            "NOVOU kopii s novým ID. Uložením vznikne vlastní melodie "
            "a původní vzor zůstane beze změny.")
        self.tlacitko_v_editoru.clicked.connect(self._otevri_editor)
        lay_f.addWidget(self.tlacitko_v_editoru)

        info_vzory = QLabel(TEXT_PUVOD_VZORU, self)
        info_vzory.setWordWrap(True)
        info_vzory.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        info_vzory.setAccessibleName("Původ vzorů fanfár")
        lay_f.addWidget(info_vzory)
        hlavni.addWidget(skupina_vzor)

        # --- Poslech -------------------------------------------------------
        skupina_poslech = QGroupBox("Poslech a porovnání", self)
        skupina_poslech.setAccessibleName("Poslech a porovnání")
        lay_s = QVBoxLayout(skupina_poslech)

        self.tlacitko_rytmus = QPushButton("Přehrát jen rytmus", self)
        self.tlacitko_rytmus.setAccessibleName("Přehrát jen rytmus")
        self.tlacitko_rytmus.setAccessibleDescription(
            "Přehraje vybraný vzor jako krátké klepy — uslyšíte jen "
            "načasování, bez výšky tónů.")
        self.tlacitko_rytmus.clicked.connect(self._prehraj_rytmus)
        lay_s.addWidget(self.tlacitko_rytmus)

        self.tlacitko_odpocet = QPushButton(
            "Přehrát rytmus s odpočítáním", self)
        self.tlacitko_odpocet.setAccessibleName(
            "Přehrát rytmus s odpočítáním")
        self.tlacitko_odpocet.setAccessibleDescription(
            "Nejdřív zazní čtyři zvukové údery odpočítání (jeden úder = "
            "jedna doba zvoleného tempa), potom rytmus vzoru. Údery jdou "
            "v pořadí „raz, dva, tři, čtyři“ — jde jen o vysvětlení "
            "pořadí, text aplikace nahlas nevyslovuje.")
        self.tlacitko_odpocet.clicked.connect(self._prehraj_odpocet)
        lay_s.addWidget(self.tlacitko_odpocet)

        popis_odpocetu = QLabel(
            "Odpočítání = čtyři zvukové údery v pořadí „raz, dva, tři, "
            "čtyři“, jeden úder = jedna doba tempa. Aplikace tento text "
            "nahlas nevyslovuje — zazní jen údery.", self)
        popis_odpocetu.setWordWrap(True)
        popis_odpocetu.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        popis_odpocetu.setAccessibleName("Vysvětlení odpočítání")
        lay_s.addWidget(popis_odpocetu)

        self.tlacitko_melodie = QPushButton("Přehrát melodii", self)
        self.tlacitko_melodie.setAccessibleName("Přehrát melodii")
        self.tlacitko_melodie.setAccessibleDescription(
            "Přehraje vybraný vzor s tóny — celou melodii, jak je "
            "právě nastavená.")
        self.tlacitko_melodie.clicked.connect(self._prehraj_melodii)
        lay_s.addWidget(self.tlacitko_melodie)

        self.tlacitko_zastavit = QPushButton("Zastavit přehrávání", self)
        self.tlacitko_zastavit.setAccessibleName("Zastavit přehrávání")
        self.tlacitko_zastavit.setAccessibleDescription(
            "Okamžitě přeruší právě přehrávanou ukázku. Na hru to nemá vliv.")
        self.tlacitko_zastavit.clicked.connect(self._zastavit)
        lay_s.addWidget(self.tlacitko_zastavit)

        radky = QHBoxLayout()
        self.tlacitko_zaznamenat = QPushButton(
            "Zaznamenat současný stav", self)
        self.tlacitko_zaznamenat.setAccessibleName(
            "Zaznamenat současný stav")
        self.tlacitko_zaznamenat.setAccessibleDescription(
            "Uloží kopii právě nastaveného rytmu jako stav „před“ pro "
            "porovnání. Při změně vzoru se stav „před“ obnoví na nově "
            "načtený vzor.")
        self.tlacitko_zaznamenat.clicked.connect(self._zaznamenat_snimek)
        radky.addWidget(self.tlacitko_zaznamenat)

        self.tlacitko_porovnat = QPushButton("Porovnat rytmus před a po", self)
        self.tlacitko_porovnat.setAccessibleName(
            "Porovnat rytmus před a po")
        self.tlacitko_porovnat.setAccessibleDescription(
            "V jednom přehrávání nejdřív zazní zaznamenaný stav „před“, "
            "potom pauza a pak současný stav „po“.")
        self.tlacitko_porovnat.clicked.connect(self._prehraj_porovnani)
        radky.addWidget(self.tlacitko_porovnat)
        lay_s.addLayout(radky)

        hlavni.addWidget(skupina_poslech)

        # --- Stav -----------------------------------------------------------
        self._stav = QLabel(self)
        self._stav.setWordWrap(True)
        self._stav.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._stav.setAccessibleName("Stav průvodce")
        hlavni.addWidget(self._stav)

        tlacitka = QDialogButtonBox(QDialogButtonBox.StandardButton.Close,
                                    parent=self)
        b_zavrit = tlacitka.button(QDialogButtonBox.StandardButton.Close)
        b_zavrit.setText("Zavřít")
        b_zavrit.setAutoDefault(False)
        b_zavrit.setDefault(False)
        tlacitka.setAccessibleName("Ovládací tlačítka průvodce")
        tlacitka.rejected.connect(self.reject)
        tlacitka.accepted.connect(self.accept)
        hlavni.addWidget(tlacitka)

        # --- Naplnění a vazby ----------------------------------------------
        if self._melodie_editoru is not None:
            self.vzor.addItem("Rozpracovaná melodie z editoru", _ID_EDITORU)
        for v in melodies.vzorove_fanfary():
            self.vzor.addItem(v.nazev, v.id)
        self.vzor.currentIndexChanged.connect(self._zmena_vzoru)
        self.priklady.currentRowChanged.connect(self._zmena_prikladu)
        self.tempo.valueChanged.connect(lambda _=False: self._prepocti())
        self.delka.valueChanged.connect(lambda _=False: self._prepocti())
        self.pauza.valueChanged.connect(lambda _=False: self._prepocti())
        self.mezertonova.valueChanged.connect(lambda _=False: self._prepocti())
        self.tony.currentRowChanged.connect(self._polozka_zmenena)

        hraje_kroky = prehravac_kroku is not None
        self.tlacitko_rytmus.setEnabled(hraje_kroky)
        self.tlacitko_odpocet.setEnabled(hraje_kroky)
        self.tlacitko_melodie.setEnabled(hraje_kroky)
        self.tlacitko_porovnat.setEnabled(hraje_kroky)
        self.tlacitko_zastavit.setEnabled(zastav_ukazku is not None)

        self.setTabOrder(self.tempo, self.delka)
        self.setTabOrder(self.delka, self.pauza)
        self.setTabOrder(self.pauza, self.mezertonova)
        self.setTabOrder(self.mezertonova, self.priklady)
        self.setTabOrder(self.priklady, self.vzor)
        self.setTabOrder(self.vzor, self.tony)
        self.setTabOrder(self.tony, self.ton_delka)
        self.setTabOrder(self.ton_delka, self.ton_pauza)
        self.setTabOrder(self.ton_pauza, self.tlacitko_zmenit_ton)
        self.setTabOrder(self.tlacitko_zmenit_ton, self.tlacitko_v_editoru)
        self.setTabOrder(self.tlacitko_v_editoru, self.tlacitko_rytmus)
        self.setTabOrder(self.tlacitko_rytmus, self.tlacitko_odpocet)
        self.setTabOrder(self.tlacitko_odpocet, self.tlacitko_melodie)
        self.setTabOrder(self.tlacitko_melodie, self.tlacitko_zastavit)
        self.setTabOrder(self.tlacitko_zastavit, self.tlacitko_zaznamenat)
        self.setTabOrder(self.tlacitko_zaznamenat, self.tlacitko_porovnat)
        self.setTabOrder(self.tlacitko_porovnat, tlacitka)

        self.priklady.setCurrentRow(0)
        self._zmena_vzoru(self.vzor.currentIndex())
        self.tempo.setFocus()

    # ------------------------------------------------------------------
    # Zavírání — bezpečné ukončení přehrávání
    # ------------------------------------------------------------------

    def done(self, r: int) -> None:     # noqa: D102
        # Kooperativní přerušení (bez čekání v hlavním vlákně); dialog
        # se může zavřít i během přehrávání, worker pak doběhne jako
        # „přerušený“ a hlavní okno ho bezpečně potvrdí.
        if self._zastav_ukazku is not None:
            try:
                self._zastav_ukazku()
            except Exception:   # noqa: BLE001 — zavření nesmí spadnout
                pass
        super().done(r)

    # ------------------------------------------------------------------
    # Pomocné
    # ------------------------------------------------------------------

    def _zobraz(self, text: str, hlasite: bool = True) -> None:
        self._stav.setText(text)
        if hlasite and self._oznamovac is not None:
            self._oznamovac.oznam(text)

    def _prepocti(self) -> None:
        """Aktualizuje přepočet zadaných dob na sekundy."""
        tempo = float(self.tempo.value())
        delka = float(self.delka.value())
        pauza = float(self.pauza.value())
        mez = float(self.mezertonova.value())
        doba = pruvodce.doba_s(tempo)
        zvuk_s, pauza_s = pruvodce.prepocti_doby(delka, pauza, tempo, mez)
        self._prepoctet.setText(
            f"1 doba = {doba:.3f} s. Zadaný tón: délka {delka:g} doby "
            f"= {zvuk_s:.3f} s; pauza {pauza:g} doby = {pauza * doba:.3f} s; "
            f"celkem s mezertonovou pauzou {mez:g} s = "
            f"{zvuk_s + pauza_s:.3f} s.")

    def _zmena_prikladu(self, radek: int) -> None:
        if not 0 <= radek < len(pruvodce.PRIKLADY):
            self._popis_prikladu.setText("")
            return
        p = pruvodce.PRIKLADY[radek]
        celkem = melodies.doba_celkem(p.melodie)
        self._popis_prikladu.setText(
            f"{p.nazev}: {p.popis} Celková délka tohoto příkladu "
            f"{celkem:.2f} s.")

    def _polozka_zmenena(self, radek: int) -> None:
        """Načte údaje vybraného tónu do polí."""
        if not 0 <= radek < self.tony.count():
            self.tlacitko_zmenit_ton.setEnabled(False)
            return
        self.tlacitko_zmenit_ton.setEnabled(True)
        ton = self.tony.item(radek).data(Qt.ItemDataRole.UserRole)
        if isinstance(ton, melodies.Ton):
            self.ton_delka.blockSignals(True)
            self.ton_pauza.blockSignals(True)
            self.ton_delka.setValue(ton.delka)
            self.ton_pauza.setValue(ton.pauza)
            self.ton_delka.blockSignals(False)
            self.ton_pauza.blockSignals(False)

    def _sesbiraj(self) -> melodies.Melodie | None:
        """Sestaví pracovní melodii z polí a seznamu (None = prázdné)."""
        tony: list[melodies.Ton] = []
        for i in range(self.tony.count()):
            ton = self.tony.item(i).data(Qt.ItemDataRole.UserRole)
            if isinstance(ton, melodies.Ton):
                tony.append(ton)
        if not tony:
            return None
        zdroj = self._zdroj
        return melodies.Melodie(
            id=zdroj.id if zdroj is not None else "_pruvodce",
            nazev=zdroj.nazev if zdroj is not None else "Vzor",
            tony=tuple(tony),
            tempo_bpm=float(self.tempo.value()),
            mezertonova_pauza_s=float(self.mezertonova.value()),
            druh=melodies.DRUH_VITEZNA,
        )

    # ------------------------------------------------------------------
    # Výběr vzoru a jeho (kopie) úpravy
    # ------------------------------------------------------------------

    def _zmena_vzoru(self, index: int) -> None:
        id_vzoru = self.vzor.itemData(index)
        if id_vzoru == _ID_EDITORU:
            zdroj = self._melodie_editoru
        else:
            zdroj = melodies.vzor(str(id_vzoru)) if id_vzoru is not None else None
        if zdroj is None:
            return
        self._nacti_zdroj(zdroj)

    def _nacti_zdroj(self, zdroj: melodies.Melodie) -> None:
        """Naplní seznam tóny a nastavením Z DROJOVÉHO objektu (jen čtení).

        Pracovní stav se skládá vždy z widgetů; ``self._snimek``
        (stav „před“) je vždy KOPIE — vzory se nikdy nemění přímo.
        Při načtení vzoru se snímek obnoví na právě načtený vzor.
        """
        self._zdroj = zdroj
        self.tony.clear()
        for ton in zdroj.tony:
            polozka = QListWidgetItem(_text_polozky(ton))
            polozka.setData(Qt.ItemDataRole.UserRole, ton)
            self.tony.addItem(polozka)

        self.tempo.blockSignals(True)
        self.mezertonova.blockSignals(True)
        self.tempo.setValue(int(round(zdroj.tempo_bpm)))
        self.mezertonova.setValue(zdroj.mezertonova_pauza_s)
        self.tempo.blockSignals(False)
        self.mezertonova.blockSignals(False)

        self._snimek = replace(zdroj)
        if self.tony.count():
            self.tony.setCurrentRow(0)
        self._prepocti()
        self._zobraz(
            f"Načten vzor „{zdroj.nazev}“. Výchozí stav pro porovnání "
            f"„před“ = tento vzor.", hlasite=False)

    def _zmenit_ton(self) -> None:
        radek = self.tony.currentRow()
        if not 0 <= radek < self.tony.count():
            self._zobraz("Nejdřív vyberte tón v seznamu.")
            return
        stary = self.tony.item(radek).data(Qt.ItemDataRole.UserRole)
        nazev = stary.nazev if isinstance(stary, melodies.Ton) else "C4"
        novy = melodies.Ton(
            nazev=nazev,
            delka=float(self.ton_delka.value()),
            pauza=float(self.ton_pauza.value()),
        )
        polozka = self.tony.item(radek)
        polozka.setText(_text_polozky(novy))
        polozka.setData(Qt.ItemDataRole.UserRole, novy)
        self.tony.setCurrentRow(radek)
        self._zobraz(
            f"Tón na místě {radek + 1} upraven: délka {novy.delka:g} doby, "
            f"pauza {novy.pauza:g} doby.", hlasite=False)

    def _zaznamenat_snimek(self) -> None:
        prace = self._sesbiraj()
        if prace is None:
            self._zobraz("Není co zaznamenat — nejdřív vyberte vzor.")
            return
        self._snimek = replace(prace)
        self._zobraz(
            "Zaznamenán současný stav jako „před“. Po dalších úpravách "
            "ho uslyšíte tlačítkem Porovnat rytmus před a po.")

    # ------------------------------------------------------------------
    # Přehrávání
    # ------------------------------------------------------------------

    def _spust_prehravani(self, kroky: list, popis: str) -> bool:
        if self._prehravac_kroku is None:
            self._zobraz("Zkušební přehrání není k dispozici.")
            return False
        spusteno = self._prehravac_kroku(kroky, popis,
                                          po_dokonceni=self._po_prehravani)
        if spusteno:
            self._zobraz(f"Přehrávám: {popis}.")
        else:
            self._zobraz("Přehrávání se teď nespustilo — v aplikaci už "
                         "něco hraje nebo je hra pozastavena. Zkuste to "
                         "za chvíli.")
        return spusteno

    def _po_prehravani(self) -> None:
        """Reakce hlavního okna na dokončení (volá ji worker přes okno)."""
        if not self.isVisible():
            return
        self._zobraz("Přehrávání skončilo.", hlasite=False)

    def _prehraj_rytmus(self) -> None:
        prace = self._sesbiraj()
        if prace is None:
            self._zobraz("Není co přehrát — vyberte vzor s tóny.")
            return
        self._spust_prehravani(
            pruvodce.kroky_rytmu(prace),
            f"rytmus vzoru {prace.nazev}")

    def _prehraj_odpocet(self) -> None:
        prace = self._sesbiraj()
        if prace is None:
            self._zobraz("Není co přehrát — vyberte vzor s tóny.")
            return
        kroky = pruvodce.kroky_s_odpocet(
            pruvodce.kroky_rytmu(prace), prace.tempo_bpm)
        self._spust_prehravani(
            kroky,
            f"rytmus s odpočítáním ({pruvodce.UDERY_ODPOCETU} údery) "
            f"vzoru {prace.nazev}")

    def _prehraj_melodii(self) -> None:
        prace = self._sesbiraj()
        if prace is None:
            self._zobraz("Není co přehrát — vyberte vzor s tóny.")
            return
        self._spust_prehravani(
            melodies.casovy_plan(prace),
            f"melodie {prace.nazev}")

    def _prehraj_porovnani(self) -> None:
        if self._snimek is None:
            self._zobraz("Není zaznamenaný stav „před“ — nejdřív ho "
                         "zaznamenejte tlačítkem Zaznamenat současný stav.")
            return
        prace = self._sesbiraj()
        if prace is None:
            self._zobraz("Není co porovnat — vyberte vzor s tóny.")
            return
        kroky = pruvodce.spoj_kroky(
            pruvodce.kroky_rytmu(self._snimek),
            pruvodce.kroky_rytmu(prace),
        )
        self._spust_prehravani(kroky, "porovnání rytmu před a po změně")

    def _zastavit(self) -> None:
        if self._zastav_ukazku is None:
            self._zobraz("Zastavení není k dispozici.")
            return
        zastaveno = self._zastav_ukazku()
        if zastaveno:
            self._zobraz("Přehrávání zastaveno.")
        else:
            self._zobraz("Nic se právě nepřehrává.")

    # ------------------------------------------------------------------
    # Otevření kopie v editoru
    # ------------------------------------------------------------------

    def _otevri_editor(self) -> None:
        prace = self._sesbiraj()
        if prace is None:
            self._zobraz("Vyberte nejdřív vzor, který obsahuje tóny.")
            return
        # Vždy NOVÉ ID a nový název — původní vzor zůstane beze změny.
        kopie = replace(
            prace,
            id=melodies.nova_id_melodie(),
            nazev=prace.nazev.removesuffix(" (vzor)") + " (vlastní úprava)",
            druh=melodies.DRUH_VITEZNA,
        )
        from gui.melodie_dialog import UpravMelodiiDialog   # bez cyklu importů

        editor = UpravMelodiiDialog(
            kopie, self,
            tonina="C",
            prehravac=self._prehravac,
            prehravac_kroku=self._prehravac_kroku,
            zastav_ukazku=self._zastav_ukazku,
            oznamovac=self._oznamovac,
        )
        editor.exec()
        # Návrat fokusu do průvodce po zavření editoru.
        self.activateWindow()
        self.tlacitko_v_editoru.setFocus()
