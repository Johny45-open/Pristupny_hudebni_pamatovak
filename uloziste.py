"""Trvalé ukládání nastavení a vlastních melodií (QSettings + JSON).

Nastavení hry a hlasu se ukládá přes ``QSettings``; vlastní melodie
maji vlastní JSON soubor. Samotná herní logika o QSettings ani o JSON
neví (zůstává čistý Python).

Ověřené chování QSettings (PyQt6 6.11, Windows, tento projekt):
- ``QSettings(ORGANIZACE, APLIKACE)`` používá **nativní formát** = na
  Windows **registr** (``fileName()`` vrací ``\\HKEY_CURRENT_USER\\…``,
  žádný soubor neexistuje);
- volání ``QSettings.setDefaultFormat(IniFormat)`` tuto dvouparametrovou
  konstrukci NEovlivní (ověřeno) — proto ``_nastaveni_qsettings``
  sestaví objekt s explicitním formátem, když je výchozí formát INI
  (díky tomu testy míří do dočasné složky a nezapisují do registru).

Protože reálná aplikace nemá „INI soubor vedle kterého“ by ležel JSON
s melodiemi, ukládají se vlastní melodie do složky dat aplikace
(``%APPDATA%\\PristupnyHudebniPamatovak\\HudebniPamatovak``); je-li
použitý QSettings skutečně soubor INI (explicitní cesta, testy), leží
JSON vedle něj. Viz ``cesta_k_melodiim``.
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QSettings, QStandardPaths

import melodies
from game_logic import NastaveniHry
from notify import NastaveniHlasu

ORGANIZACE = "PristupnyHudebniPamatovak"
APLIKACE = "HudebniPamatovak"

KLICE = (
    "tonina", "oktava", "delka_sekvence", "pocet_pokusu",
    "interval_statistik", "id_smutne_melodie", "id_vitezne_melodie",
)

# Klíč nastavení hlasového výstupu (notify.NastaveniHlasu).
KLIC_HLASU = "hlasovy_vystup"

# Soubor s vlastními melodiemi (JSON, UTF-8).
NAZEV_SOUBORU_MELODII = "vlastni_melodie.json"


def vychozi_nastaveni() -> NastaveniHry:
    return NastaveniHry()


def _nastaveni_qsettings(nastaveni_qsettings: QSettings | None) -> QSettings:
    if nastaveni_qsettings is not None:
        return nastaveni_qsettings
    # Viz dokumentace modulu: dvouparametrová konstrukce defaultFormat
    # ignoruje, proto ho při INI výslovně uvádíme.
    if QSettings.defaultFormat() == QSettings.Format.IniFormat:
        return QSettings(QSettings.Format.IniFormat,
                         QSettings.Scope.UserScope,
                         ORGANIZACE, APLIKACE)
    return QSettings(ORGANIZACE, APLIKACE)


def uloz_nastaveni(nastaveni: NastaveniHry,
                   nastaveni_qsettings: QSettings | None = None) -> None:
    """Uloží nastavení hry na disk (přes QSettings)."""
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


# ---------------------------------------------------------------------------
# Nastavení hlasového výstupu
# ---------------------------------------------------------------------------


def uloz_nastaveni_hlasu(nastaveni_hlasu: NastaveniHlasu,
                         nastaveni_qsettings: QSettings | None = None) -> None:
    """Uloží nastavení hlasového výstupu; neplatný režim odmítne."""
    nastaveni_hlasu.over()
    s = _nastaveni_qsettings(nastaveni_qsettings)
    s.setValue(KLIC_HLASU, nastaveni_hlasu.rezim)
    s.sync()


def nacti_nastaveni_hlasu(
        nastaveni_qsettings: QSettings | None = None) -> NastaveniHlasu:
    """Načte nastavení hlasu; chybějící/neplatná hodnota → výchozí."""
    s = _nastaveni_qsettings(nastaveni_qsettings)
    vychozi = NastaveniHlasu()
    hodnota = s.value(KLIC_HLASU, vychozi.rezim)
    if hodnota is None:
        return vychozi
    kandidat = NastaveniHlasu(rezim=str(hodnota))
    try:
        kandidat.over()
    except ValueError:
        return vychozi
    return kandidat


# ---------------------------------------------------------------------------
# Vlastní melodie — JSON soubor
# ---------------------------------------------------------------------------


def _adresar_dat_aplikace(adresar_dat: str | Path | None = None) -> Path:
    """Složka dat aplikace pro JSON s melodiemi (když QSettings není soubor)."""
    if adresar_dat is not None:
        return Path(adresar_dat)
    zaklad = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation))
    # Bez nastaveného jména aplikace vrací Qt jen %APPDATA% (nebo složku
    # jiného programu) — připojíme vlastní organizaci a aplikaci.
    if zaklad.name.casefold() != APLIKACE.casefold():
        zaklad = zaklad / ORGANIZACE / APLIKACE
    return zaklad


def cesta_k_melodiim(
        nastaveni_qsettings: QSettings | None = None,
        adresar_dat: str | Path | None = None) -> Path:
    """Úplná cesta k JSON souboru s vlastními melodiemi.

    - QSettings je skutečný soubor INI (``fileName()`` končí na
      ``.ini``) → JSON leží vedle něj,
    - jinak (nativní formát = registr) → JSON je v datech aplikace,
      ``adresar_dat`` přepíše tuto složku (pro testy).
    """
    s = _nastaveni_qsettings(nastaveni_qsettings)
    nazev = s.fileName() or ""
    if nazev.lower().endswith(".ini"):
        return Path(nazev).parent / NAZEV_SOUBORU_MELODII
    return _adresar_dat_aplikace(adresar_dat) / NAZEV_SOUBORU_MELODII


def uloz_vlastni_melodie(
        nastaveni_qsettings: QSettings | None = None,
        adresar_dat: str | Path | None = None) -> Path:
    """Zapíše registr vlastních melodií do JSON — atomicky.

    Nejprve zkontroluje KAŽDOU melodii; je-li některá neplatná, vyhodí
    ValueError a soubor se vůbec nezmění (poslední platná definice
    zůstává nedotčená). Zápis jde přes dočasný soubor a ``os.replace`` —
    ani výpadek nezanechá poloviční JSON.
    """
    chyby: list[str] = []
    for id_melodie, melodie in melodies.VLASTNI_MELODIE.items():
        chyby_m, _ = melodies.over_pred_ulozenim(melodie)
        chyby.extend(f"{id_melodie}: {c}" for c in chyby_m)
    if chyby:
        raise ValueError(
            "Vlastní melodie nejsou platné, soubor zůstal nezměněn: "
            + "; ".join(chyby))

    cil = cesta_k_melodiim(nastaveni_qsettings, adresar_dat)
    cil.parent.mkdir(parents=True, exist_ok=True)
    docasny = cil.with_name(cil.name + ".tmp")
    try:
        docasny.write_text(melodies.vlastni_do_jsonu(), encoding="utf-8")
        os.replace(docasny, cil)
    finally:
        try:
            docasny.unlink(missing_ok=True)
        except OSError:
            pass
    return cil


def nacti_vlastni_melodie(
        nastaveni_qsettings: QSettings | None = None,
        adresar_dat: str | Path | None = None) -> tuple[bool, list[str]]:
    """Načte JSON s melodiemi do ``melodies.VLASTNI_MELODIE``.

    Vrací ``(zmeneno, chyby)`` — chyby jsou srozumitelná česká hlášení:

    - soubor neexistuje → ``(False, [])``, registr se nemění,
    - poškozený JSON / neočekávaný tvar → ``(False, chyby)`` — registr
      se NEMĚNÍ (platná data v paměti zůstávají),
    - čitelný soubor → platné záznamy registr nahradí; neplatné záznamy
      se vynechají, ale stejné ID v paměti se přepsat NESMÍ
      (neplatná melodie nikdy nepřetlačí poslední platnou definici).
    """
    cil = cesta_k_melodiim(nastaveni_qsettings, adresar_dat)
    if not cil.exists():
        return False, []
    try:
        text = cil.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return False, [f"Soubor s vlastními melodiemi se nepodařil "
                       f"přečíst: {e}"]

    nactene, chyby, neplatne_id = melodies.vlastni_z_jsonu(text)
    if nactene is None:
        # Soubor je poškozený — do registrů nesaháme.
        return False, chyby

    nove: dict[str, melodies.Melodie] = dict(nactene)
    for id_melodie in neplatne_id:
        # Neplatný záznam: necháme platnou verzi z paměti (pokud existuje).
        stara = melodies.VLASTNI_MELODIE.get(id_melodie)
        if stara is not None and not melodies.over_pred_ulozenim(stara)[0]:
            nove[id_melodie] = stara

    melodies.VLASTNI_MELODIE.clear()
    melodies.VLASTNI_MELODIE.update(nove)
    return True, chyby
