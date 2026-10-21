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
  (2–12), interval statistik, smutná a vítězná melodie a hlasový výstup.
  Nastavení se ukládá trvale (QSettings) a použije se od dalšího kola.
- Vlastní melodie: uživatel je vytvoří, upraví, smaže i zkušebně přehraje
  přímo v aplikaci (tlačítko „Spravovat vlastní melodie…“ v nastavení),
  bez úpravy zdrojového kódu. Ukládají se trvale do JSON souboru;
  poškozená data aplikaci nerozbijí a přednastavené melodie zůstávají.
- Průvodce rytmem a fanfárami: dialog s vysvětlením tempa (BPM), délek
  tónů v dobách a pauz, s přepočtem zadaných dob na sekundy, se třemi
  krátkými rytmickými příklady a se třemi originálními (volně
  vymyšlenými) vzory fanfár k poslechu, úpravě a otevření v editoru
  jako vlastní kopie. Tlačítko „Průvodce rytmem a fanfárami“ je
  v editoru i ve správci melodií. Viz sekce „Průvodce rytmem a fanfárami“.
- Hlasový výstup ve třech režimech: vypnutý; jen s potvrzenou aktivní
  čtečkou obrazovky (bez potvrzení aplikace nehlasitě nemluví); i bez
  čtečky (přednost má čtečka, jinak systémový hlas). Viz sekce
  „Hlasový výstup“.
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
python -m pytest tests\test_vlastni_melodie.py -q
python -m pytest tests\test_uloziste_melodie.py -q
python -m pytest tests\test_gui_offscreen.py -q
python -m pytest tests\test_gui_melodie.py -q
python -m pytest tests\test_pruvodce.py -q
python -m pytest tests\test_gui_pruvodce.py -q
```

Kontrola syntaxe:

```powershell
python -m py_compile theory.py melodies.py game_logic.py stats.py sound.py player_worker.py notify.py uloziste.py pruvodce.py main.py gui\main_window.py gui\settings_dialog.py gui\melodie_dialog.py gui\pruvodce_dialog.py gui\stats_dialog.py
```

## Struktura projektu

| Soubor | Účel |
|---|---|
| `main.py` | vstupní bod: QApplication, načtení nastavení, propojení komponent |
| `theory.py` | 15 tónin, české názvy stupňů, MIDI převody, transpozice |
| `melodies.py` | definice melodií, transpozice, individuální definice, validace, fallback |
| `game_logic.py` | čistá herní logika (bez Qt a zvuku) |
| `stats.py` | intervalové a celkové statistiky |
| `sound.py` | matematické generování tónů, přehrávání přes pygame, tichý režim; krátké rytmické klepy (`generuj_impuls`) s vlastní cache |
| `player_worker.py` | QThread worker s kooperativním přerušením přehrávání (kroky s `impuls=True` = rytmický klep) |
| `notify.py` | hlasová oznámení (accessible_output2) + stavový panel jako fallback; režimy hlasu a rozlišení čtečky vs. systémového hlasu |
| `uloziste.py` | nastavení přes QSettings, nastavení hlasu a bezpečný JSON s vlastními melodiemi |
| `pruvodce.py` | čistá logika průvodce: přepočet dob na sekundy, rytmické klepání, odpočítání, spojení „před/po“, rytmické příklady |
| `gui/` | hlavní okno, dialog nastavení, správce a editor vlastních melodií, průvodce rytmem, dialog statistik (PyQt6, česky) |
| `tests/` | pytest sady (offscreen, bez zvuku) |

## Vlastní melodie

**V aplikaci (bez úpravy zdrojového kódu):** v dialogu Nastavení je
tlačítko „Správce vlastních melodií…“ (klávesa S). V otevřeném správci:

1. „Nová melodie…“ otevře editor: název, druh (smutná/vítězná), tempo,
   mezertonová pauza a seznam tónů (tón + délka v taktech + pauza po tónu).
   Tlačítka „Přidat tón“, „Nahradit“, „Odebrat“ upravují seznam; zkušební
   přehrávání má vlastní tlačítko pro každý tón (F6 přehraje celý dosud
   zadaný seznam).
2. „Upravit vybranou melodii…“ otevře tutéž editační obrazovku s vyplněnými
   údaji; uložením se melodie přepíše, „Zrušit“ původní verzi nechá beze
   změny.
3. „Smazat vybranou melodii…“ melodie po potvrzení smaže — i z disku.

Uložené melodie se objeví ve výběrech smutné a vítězné melodie s poznámkou
„(vlastní)“ a platí pro ně stejná pravidla jako pro přednastavené
(transpozice do všech tónin, kontrola tónů mimo stupnici). Pokud je
právě vybraná vlastní melodie smazána, automaticky se oba výběry vrátí
na výchozí melodii.

**Úložiště:** nastavení (včetně režimu hlasu) drží `QSettings` — na
Windows je to registr `HKCU\Software\PristupnyHudebniPamatovak`, protože
aplikace nepoužívá INI soubor. Proto jsou vlastní melodie v samostatném
JSON souboru v datech aplikace:

```
%APPDATA%\PristupnyHudebniPamatovak\HudebniPamatovak\vlastni_melodie.json
```

(Pokud by `QSettings` pracoval s souborem INI, JSON leží vedle něj.)
Zápis je atomický přes dočasný soubor; neplatná melodie se nezapíše a
poškozený soubor se při startu srozumitelně ohlásí — přednastavené melodie
zůstávají vždy a poslední platná definice se nepřepíše.

**Ve zdrojovém kódu (pro vývojáře):** melodie se definují jednou
v tónině C a automaticky se transponují do všech
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

## Průvodce rytmem a fanfárami

Dialog vysvětlí základy rytmu a nabídne vzory fanfár k vyzkoušení.
Otevře se tlačítkem „Průvodce rytmem a fanfárami“ **v editoru vlastní
melodie** i **ve správci melodií** (v editoru přináší jeho rozpracovanou
melodii jako první položku výběru).

**Co dialog obsahuje:**

1. **Vysvětlení tempa a délek** — co je BPM, jak se počítá délka jedné
   doby (60 ÷ tempo), jak se zapisuje délka tónu a pauza v dobách a že
   se mezertonová pauza přičítá v sekundách nezávisle na tempu. Pole
   tempo / délka / pauza / mezertonová pauza lze zadat přímo z
   klávesnice a výsledek se přepočítává živě („1 doba = … s, zadaný
   tón = … s“).
2. **Rytmické příklady** — tři krátké ukázky (stejné čtvrtky, osminky a
   čtvrtky, vítězný rytmus 3 + 3 + 2) s českým popisem a vypočtenou
   délkou v sekundách.
3. **Vzor fanfáry k úpravě** — výběr ze **tří originálních, volně
   vymyšlených** ukázek (nejde o oficiální znělky žádných hokejových
   ani jiných klubů): krátká vítězná, energetická gólová a slavnostní
   zakončení. Každý vzor má tóny, tempo, délky a pauzy; seznam tónů
   jde upravit poli délka / pauza + „Změnit vybraný tón“.
   **Vzory se upravují vždy přes kopii** — `VZOROVE_FANFARY` zůstávají
   beze změny a „Otevřít vzor v editoru…“ vytvoří vždy novou kopii
   s novým ID a názvem „… (vlastní úprava)“.
4. **Poslech a porovnání** — „Přehrát jen rytmus“ (krátké klepy místo
   tónů), „Přehrát rytmus s odpočítáním“ (4 zvukové údery po jedné
   době tempa; text „raz, dva, tři, čtyři“ jen vysvětluje pořadí,
   aplikace ho nahlas nevyslovuje), „Přehrát melodii“, „Zastavit
   přehrávání“, „Zaznamenat současný stav“ a „Porovnat rytmus před a
   po“ (oba rytmy za sebou v jednom přehrávání s pauzou 1,5 s mezi
   nimi). Při změně vzoru se zaznamenaný stav „před“ automaticky
   obnoví na nově načtený vzor.

**Jak je to se časem:** rytmické klepání vychází z přesného
`casovy_plan()` — pro původní krok `D` (délka zvuku) + `P` (pauza) a
impuls `I` (0,08 s, zkrácený na `D`, je-li kratší) je pauza po impulsu
`max(0, D + P − I)`, takže nástupy i celková délka zůstávají stejné
jako u původní melodie a mezitónová pauza se nezapočítá dvakrát.

Přehrávání jde přes worker hlavního okna (typ „ukazka“) — GUI se
neblokuje, fokus se po ukázce vrací do průvodce a zavření průvodce
během přehrávání ho kooperativně přeruší bez zničení dialogu.

## Hlasový výstup — režimy

Režim se volí v dialogu Nastavení (sekce „Hlasový výstup“) a ukládá se
trvale. Textová oznámení zůstávají na stavovém panelu vždy — v každém
režimu a bez ohledu na to, zda hlas funguje.

| Režim | Chování |
|---|---|
| `vypnuto` („Hlas vypnutý“) | Aplikace nehlasitě nemluví vůbec; všechna hlášení jsou jen na stavovém panelu. |
| `jen_odecitas` („Hlas jen s potvrzenou čtečkou obrazovky“) | Hlasitě mluví jen tehdy, když je skutečně aktivní známá čtečka obrazovky (NVDA, JAWS, System Access, Dolphin, PC Talker, Window-Eyes, ZDSR) a její `is_active()` to potvrdí. Bez potvrzení zůstává zticha, i kdyby byl dostupný systémový hlas SAPI. |
| `vcetne_systemu` („Hlas i bez čtečky (systémový hlas)“) — **výchozí** | Chování jako před zavedením režimů: nejdřív se pokusí mluvit přes potvrzenou čtečku, bez ní použije systémový hlas. |

Pravidla pro „potvrzení čtečky“ (ověřena proti nainstalované
`accessible_output2` 0.17):

- Samotná dostupnost `Auto()` ani přítomnost systémového hlasu (SAPI5)
  se za potvrzení čtečky NEPOVAŽUJE.
- `is_active()`, který vyhodí výjimku nebo u výstupu chybí (takto se
  chová sapi4), se za potvrzení aktivity nepovažuje.

V dialogu Nastavení je „Zjistit stav hlasu“ (srozumitelně vypíše, zda je
potvrzena čtečka, zda je dostupný systémový hlas a jaký režim platí) a
„Zkušební hláška“ — ta přehraje zkušební text přes právě dostupný výstup
podle zvoleného režimu a přepíše jen hlášení v dialogu, ne hlášení herní.

## Přístupnost — co je a co není ověřeno

**Ověřeno automaticky (offscreen testy):** přístupné názvy a popisy všech
ovládacích prvků (žádné generické „Tlačítko 1“), propojení popisků přes
`setBuddy`, čitelnost textu chyby a zbývajících pokusů na stavovém panelu
(včetně přístupného názvu panelu), kontext kláves 1–7 (neaktivní v modálních
dialozích a číselných polích), návrat fokusu po kole a po zavření dialogů,
bezpečné odložení zavírání, skutečné ukončení workeru (`wait()` + `isFinished()`),
fungování bez zvukového zařízení. Dále sekce hlasového výstupu v nastavení
(tři režimy, stav, zkušební hláška), přístupnost správce a editoru vlastních
melodií, že po dokončení zkušební ukázky zůstane editor otevřený s fokusem
uvnitř něj a že smazání právě vybrané melodie aktualizuje oba výběry,
uložené hodnoty i interní reference (bez změny nesouvisejícího nastavení).
U průvodce rytmem dále: přístupné názvy a popisy všech prvků, buddy
popisky, žádné posuvníky, pořadí Tab přes `nextInFocusChain`, přepočet
dob na sekundy podle tempa, ochrana `VZOROVE_FANFARY` (úpravy i uložení
kopie s novým ID), návrat fokusu po zavření editoru do průvodce i po
průvodci do správce a do editoru, přehrání bez blokování GUI s návratem
fokusu, kooperativní zastavení při zavření během přehrávání, porovnání
„před/po“ v jediném workeru a to, že ukázky nemění herní logiku ani
chování kroků s `impuls=False`.

**Není fyzicky ověřeno:** průběh s reálně spuštěným NVDA nebo JAWS
(včetně chování režimu `jen_odecitas` s reálnou čtečkou), reálný
hlasový výstup **ani ruční průchod průvodcem rytmem** (kroky 11–12
výše zatím nebyly provedeny — jsou to kandidáti na ruční test).
Testy hlasových režimů pracují s věrnými atrapami
výstupů `accessible_output2`, ne s živou čtečkou. Přítomnost
`setAccessibleName()` sama o sobě kompatibilitu
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
11. Nastavení → Správce vlastních melodií → „Průvodce rytmem“: NVDA by
    měl číst nadpis, vysvětlení tempa a pole tempo; Tab vede přes
    rytmické příklady, výběr vzoru, seznam tónů a tlačítka poslechu;
    „Přehrát jen rytmus“ spustí ukázku a po jejím skončení se fokus
    vrátí na tlačítko; „Zavřít“ se stejnou ukázku přeruší a fokus se
    vrátí do správce.
12. Týž průvodce otevřete i z editoru melodie a po jeho zavření se fokus
    musí vrátit na tlačítko průvodce v editoru.

S JAWS postupujte stejně (JAWS čte stejné standardní názvy přístupnosti).

## Známá omezení

- Při startu v režimu `QT_QPA_PLATFORM=offscreen` Qt varuje, že nenajde
  adresář s písmy; na běžném Windows s reálnou obrazovkou toto varování
  nevzniká (Qt používá systémová písma).
- Výchozí oktáva 4; rozsah tlačítek je přibližně C4–A5 podle tóniny (u
  tónin s ostrým základem může horní stupeň přesáhnout do oktávy 6).
- Hlasová oznámení používají `accessible_output2`; výběr výstupu se řídí
  zvoleným režimem (viz „Hlasový výstup“). Pokud není žádný výstup k
  dispozici, text zůstává čitelný na přístupném stavovém panelu.
- Nastavení se na Windows ukládá do registru (`QSettings` v nativním
  formátu), ne do INI souboru; vlastní melodie proto mají vlastní JSON
  v `%APPDATA%` (viz „Vlastní melodie“).
- Při testech s hlasem může `accessible_output2` vyvolat u SAPI tichou
  systémovou výjimku („Windows fatal exception 0xe0000002“) — je to
  předexistující jev knihovny/SAPI, na výsledcích testů se neprojevuje.
