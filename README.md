# Hudební pamatovák

Přístupná desktopová hra pro Windows: aplikace vygeneruje náhodnou sekvenci
tónů ve zvolené durové tónině, přehraje ji a hráč ji opakuje sedmi tlačítky
(stupně stupnice). Vytvořeno v **Pythonu + PyQt6**, celé rozhraní je česky a
je ovladatelné klávesnicí pro uživatele s odečítačem obrazovky (NVDA, JAWS).

## Co aplikace umí

- 15 durových tónin česky: C, G, D, A, E, H, Fis, Cis, F, B, Es, As, Des,
  Ges, Ces (bez mezinárodních dvojznaček; H = B přirozené, B = B snížené).
- Sedm tlačítek tónů = stupnice od základního tónu vzhůru; názvy jsou
  enharmonicky správné (Eis, Fes, His, Ces…) a vždy obsahují oktávu.
- Nastavení: tónina, výchozí oktáva (3/4/5), počet pokusů, délka sekvence
  (2–12), interval statistik, smutná a vítězná melodie. Nastavení se ukládá
  trvale (QSettings) a použije se od dalšího kola.
- Pravidla: chyba = jeden pokus + smutná melodie + návrat na začátek
  sekvence; úspěch = vítězná melodie; opakované přehrání sekvence nemění
  skóre ani pokusy.
- Statistiky: intervalové i celkové; dialog se otevře až po přesně N
  dokončených kolech a až po dohrání výsledkové melodie, vždy jednou.
- Tóny se generují matematicky (numpy + pygame) — žádné externí zvukové
  soubory. Bez zvukového zařízení aplikace přejde do tichého režimu a dál
  funguje (logika i GUI).

## Instalace a spuštění (Windows)

V příkazovém řádku (PowerShell) v adresáři projektu:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Pokud aktivace virtuálního prostředí selže kvůli politice skriptů:

```powershell
powershell -ExecutionPolicy Bypass -File .venv\Scripts\Activate.ps1
```

## Ovládání

| Klávesa | Akce |
|---|---|
| 1–7 | zadání tónu (stupnice stupnice vzhůru; funguje jen ve hře, ne v dialozích ani v polích) |
| F2 | nová hra |
| F5 | přehrát sekvenci znovu (nemění skóre ani pokusy) |
| F6 | zopakovat poslední hlášení hlasitě |
| F7 | pokračovat ve hře po ukončeném přehrávání (hráčem zvolené zrušení zavírání) |
| Tab / Shift+Tab | pohyb po ovládacích prvcích |
| Enter / mezerník | aktivace zaměřeného tlačítka |

Při zavírání okna během přehrávání se zavírání bezpečně odloží, dokud
přehrávání neskončí. Překročí-li čekání limit, nabídne aplikace volbu
„Zkustit znovu čekat“ nebo „Zrušit ukončení“; po zrušení zůstane hra
pozastavená, dokud hráč nestiskne „Pokračovat ve hře“ — sekvence, pokusy ani
statistiky se tím nezmění.

## Testy

Testy běží bez obrazovky, bez myši a bez zvukového zařízení
(`QT_QPA_PLATFORM=offscreen`, deterministická náhodnost):

```powershell
python -m pytest tests -q
```

Jednotlivé sady:

```powershell
python -m pytest tests\test_theory.py -q
python -m pytest tests\test_melodies.py -q
python -m pytest tests\test_game_logic.py -q
python -m pytest tests\test_stats.py -q
python -m pytest tests\test_player_worker.py -q
python -m pytest tests\test_settings.py -q
python -m pytest tests\test_notify.py -q
python -m pytest tests\test_gui_offscreen.py -q
```

Kontrola syntaxe:

```powershell
python -m py_compile theory.py melodies.py game_logic.py stats.py sound.py player_worker.py notify.py uloziste.py main.py gui\main_window.py gui\settings_dialog.py gui\stats_dialog.py
```

## Struktura projektu

| Soubor | Účel |
|---|---|
| `main.py` | vstupní bod: QApplication, načtení nastavení, propojení komponent |
| `theory.py` | 15 tónin, české názvy stupňů, MIDI převody, transpozice |
| `melodies.py` | definice melodií, transpozice, individuální definice, validace, fallback |
| `game_logic.py` | čistá herní logika (bez Qt a zvuku) |
| `stats.py` | intervalové a celkové statistiky |
| `sound.py` | matematické generování tónů, přehrávání přes pygame, tichý režim |
| `player_worker.py` | QThread worker s kooperativním přerušením přehrávání |
| `notify.py` | hlasová oznámení (accessible_output2) + stavový panel jako fallback |
| `uloziste.py` | ukládání a načítání nastavení přes QSettings |
| `gui/` | hlavní okno, dialog nastavení, dialog statistik (PyQt6, česky) |
| `tests/` | pytest sady (offscreen, bez zvuku) |

## Vlastní melodie (jen `melodies.py`)

Melodie se definují jednou v tónině C a automaticky se transponují do všech
15 tónin. Pro konkrétní tóninu lze definovat nezávislou melodii, která má
přednost. Příklad (do slovníku `INDIVIDUALNI_MELODIE`):

```python
INDIVIDUALNI_MELODIE = {
    ("Fis", DRUH_VITEZNA, "kratka_fanfara"): Melodie(
        id="kratka_fanfara",
        nazev="Fanfára pro Fis dur",
        tony=(Ton("Fis4", 0.5), Ton("Cis5", 0.5), Ton("Fis5", 1.0)),
        tempo_bpm=126.0,
    ),
}
```

Tóny mimo stupnici jsou povoleny jen příznakem `povolit_mimo_stupnici=True`;
jinak je melodie odmítnuta a použije se bezpečná náhrada. Herní logiku,
GUI ani zvukový engine kvůli nové melodii měnit nemusíte.

## Přístupnost — co je a co není ověřeno

**Ověřeno automaticky (offscreen testy):** přístupné názvy a popisy všech
ovládacích prvků (žádné generické „Tlačítko 1“), propojení popisků přes
`setBuddy`, čitelnost textu chyby a zbývajících pokusů na stavovém panelu
(včetně přístupného názvu panelu), kontext kláves 1–7 (neaktivní v modálních
dialozích a číselných polích), návrat fokusu po kole a po zavření dialogů,
bezpečné odložení zavírání, skutečné ukončení workeru (`wait()` + `isFinished()`),
fungování bez zvukového zařízení.

**Není fyzicky ověřeno:** průběh s reálně spuštěným NVDA nebo JAWS a reálný
hlasový výstup. Přítomnost `setAccessibleName()` sama o sobě kompatibilitu
s odečítačem negarantuje. Manuální postup testu s NVDA:

1. Spusťte NVDA, pak `python main.py`.
2. NVDA by měl při otevření okna přečíst název aplikace a stavový panel.
3. Tabulátorem projděte: panel → informace o hře → 7 tlačítek tónů (každé
   slyšitelně „Tón …, oktáva …“) → ovládací tlačítka.
4. F2 — uslyšíte oznámení o nové hře a přehraje se sekvence.
5. Zadejte špatný tón (libovolné jiné tlačítko) — NVDA hlásí chybu a počet
   zbývajících pokusů; přehraje se smutná melodie; informace zůstane čitelná
   i na panelu (přepněte do režimu procházení a přečtěte si panel).
6. Vyčerpejte pokusy — kolo skončí neúspěchem; po melodii se (pokud je
   vyčerpán interval) otevře dialog statistik; NVDA přečte výsledky a po
   Zavřít se fokus vrátí na tlačítko Statistiky.
7. Opakujte kolo správně — po sekvenci fokus přejde na první tón, po
   vítězné melodii na Novou hru; uslyšíte vítěznou melodii.
8. F5 uprostřed kola — sekvence se znovu přehraje; skóre i pokusy zůstanou
   (ověřte přečtením panelu a statistik).
9. F6 — NVDA zopakuje poslední hlášení (funkční i bez hlasového výstupu,
   protože text je i na panelu).
10. Spusťte přehrávání a zkuste zavřít okno — okno se nesmí zavřít, dokud
    zvuk doběhne; ovládání bude dočasně vypnuté.

S JAWS postupujte stejně (JAWS čte stejné standardní názvy přístupnosti).

## Známá omezení

- Při startu v režimu `QT_QPA_PLATFORM=offscreen` Qt varuje, že nenajde
  adresář s písmy; na běžném Windows s reálnou obrazovkou toto varování
  nevzniká (Qt používá systémová písma).
- Výchozí oktáva 4; rozsah tlačítek je přibližně C4–A5 podle tóniny (u
  tónin s ostrým základem může horní stupeň přesáhnout do oktávy 6).
- Hlasová oznámení používají `accessible_output2` (SAPI); pokud není
  aktivní žádný odečítač, text zůstává čitelný na přístupném stavovém panelu.
