"""Trvalé ukládání nastavení přes QSettings (INI soubor v profilu).

Nastavení se ukládá i načítá; samotná herní logika o QSettings
neví (zůstává čistý Python).
"""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from game_logic import NastaveniHry

ORGANIZACE = "PristupnyHudebniPamatovak"
APLIKACE = "HudebniPamatovak"

KLICE = (
    "tonina", "oktava", "delka_sekvence", "pocet_pokusu",
    "interval_statistik", "id_smutne_melodie", "id_vitezne_melodie",
)


def vychozi_nastaveni() -> NastaveniHry:
    return NastaveniHry()


def _nastaveni_qsettings(nastaveni_qsettings: QSettings | None) -> QSettings:
    if nastaveni_qsettings is not None:
        return nastaveni_qsettings
    return QSettings(ORGANIZACE, APLIKACE)


def uloz_nastaveni(nastaveni: NastaveniHry,
                   nastaveni_qsettings: QSettings | None = None) -> None:
    """Uloží nastavení na disk (přes QSettings)."""
    s = _nastaveni_qsettings(nastaveni_qsettings)
    s.setValue("tonina", nastaveni.tonina)
    s.setValue("oktava", nastaveni.oktava)
    s.setValue("delka_sekvence", nastaveni.delka_sekvence)
    s.setValue("pocet_pokusu", nastaveni.pocet_pokusu)
    s.setValue("interval_statistik", nastaveni.interval_statistik)
    s.setValue("id_smutne_melodie", nastaveni.id_smutne_melodie)
    s.setValue("id_vitezne_melodie", nastaveni.id_vitezne_melodie)
    s.sync()


def nacti_nastaveni(nastaveni_qsettings: QSettings | None = None) -> NastaveniHry:
    """Načte nastavení z disku; neplatné/chybějící hodnoty → výchozí."""
    s = _nastaveni_qsettings(nastaveni_qsettings)
    vychozi = vychozi_nastaveni()

    def _int(klic: str, vychozi_hodnota: int) -> int:
        try:
            return int(s.value(klic, vychozi_hodnota))
        except (TypeError, ValueError):
            return vychozi_hodnota

    kandidat = NastaveniHry(
        tonina=str(s.value("tonina", vychozi.tonina)),
        oktava=_int("oktava", vychozi.oktava),
        delka_sekvence=_int("delka_sekvence", vychozi.delka_sekvence),
        pocet_pokusu=_int("pocet_pokusu", vychozi.pocet_pokusu),
        interval_statistik=_int("interval_statistik",
                                vychozi.interval_statistik),
        id_smutne_melodie=str(s.value("id_smutne_melodie",
                                      vychozi.id_smutne_melodie)),
        id_vitezne_melodie=str(s.value("id_vitezne_melodie",
                                       vychozi.id_vitezne_melodie)),
    )
    try:
        kandidat.over()
    except ValueError:
        # Nedůvěryhodný soubor — bezpečně zpět k výchozím hodnotám.
        return vychozi
    return kandidat
