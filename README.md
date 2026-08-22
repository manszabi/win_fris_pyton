# Display Refresh Rate Switcher

Windows 11 program, ami automatikusan valtoztatja a kijelzo frissitesi
frekvenciajat jatekok inditasakor es leallitasakor.

**Szerzo:** ManSzabi · **Verzio:** 2.0

## Funkciok

- Automatikus frekvenciavaltas jatek inditasakor/leallitasakor
- Jatekonkenti kulon frekvencia beallitas
- **Az eloszor elinditott jatek beallitasa nyer** — a kesobb inditott jatekok nem irjak felul
- Tobb monitor tamogatas: sorszam **vagy nev** szerinti kivalasztassal
- System tray ikon a jelenlegi frekvencia kijelzesevel
- Onmagat javito mukodes: alvas/hibernalas utani Windows-visszaallast korrigal
- Kilepeskor visszaallitja az alapertelmezett frekvenciat
- Egypeldany-vedelem: ket parhuzamos peldany nem tud egymas ellen dolgozni
- Bejelentkezeskor automatikusan elindul (Task Scheduler)
- **Takarekos**: a hattermunka ellenorzesenkent kb. ezredmasodpercekben merheto
  (lasd az [Eroforrasigeny](#eroforrasigeny) reszt)

## Telepites

Eloszor telepitsd a **Python 3.10+** verziojat:
https://www.python.org/downloads/ — telepiteskor jelold be az
**"Add Python to PATH"** opciot.

Utana toltsd le a projektet, es **kattints duplan a `telepites.bat` fajlra**.

```bash
git clone https://github.com/manszabi/win_fris_pyton.git
cd win_fris_pyton
```

A `telepites.bat` mindent elintez:

1. **Sajat virtualis kornyezetet keszit** a `.venv` mappaban (csak az elso
   inditaskor). A csomagok igy nem a rendszer Pythonjaba kerulnek, es nem
   keverednek mas programok csomagjaival.
2. **Ellenorzi a fuggosegeket**, es csak akkor telepit, ha kell.
3. **Letrehozza a Task Scheduler feladatot**, es azonnal el is inditja a
   programot. Minden bejelentkezeskor automatikusan elindul.

**Rendszergazdai jog altalaban nem szukseges.** Ha "Access is denied" hibat
kapsz, inditsd a `telepites.bat`-ot jobb klikk -> *Futtatas rendszergazdakent*
modon.

| Parancs | Mit csinal |
|---------|------------|
| `telepites.bat` | Telepites vagy javitas (barmikor ujra futtathato) |
| `telepites.bat frissit` | A csomagok frissitese a legujabb verziora |
| `telepites.bat admin` | Emelt jogu feladat (adminkent futo jatekok figyelesehez) |
| `eltavolitas.bat` | Az automatikus inditas kikapcsolasa |

Az `eltavolitas.bat` a `.venv` mappat es a `config.json`-t **nem** torli; ha
azokat is meg akarod szuntetni, egyszeruen tordold a projekt mappat.

> **A projekt mappajat a telepites utan ne helyezd at.** Az utemezett feladat
> a `.venv` Pythonjara mutat teljes utvonallal. Ha megis athelyezed, futtasd
> ujra a `telepites.bat`-ot -- felulirja a feladatot az uj utvonallal.

<details>
<summary>Telepites kezzel, virtualis kornyezet nelkul</summary>

```bash
pip install -r requirements.txt
python -m refreshswitcher install
```

Ez a rendszer Pythonjaba telepit. Mukodik, de a `telepites.bat` az ajanlott
ut, mert elkuloniti a csomagokat.
</details>

| Fuggoseg | Miert kell |
|----------|------------|
| `psutil` | futo processzek figyelese |
| `pywin32` | Windows API (kijelzo beallitasok) |
| `pystray` | system tray ikon |
| `Pillow` | ikon kep generalas |

## Hasznalat

```bash
python -m refreshswitcher tray      # tray ikon inditasa (alapertelmezett)
python -m refreshswitcher run       # konzolos futtatas, hibakeresehez
python -m refreshswitcher status    # monitorok es tamogatott frekvenciak
python -m refreshswitcher check     # csak a config.json ellenorzese
python -m refreshswitcher install   # automatikus inditas be
python -m refreshswitcher remove    # automatikus inditas ki
python -m refreshswitcher start     # inditas
python -m refreshswitcher stop      # leallitas
python -m refreshswitcher task-status  # az utemezett feladat allapota
```

> **Virtualis kornyezet eseten** a `python` helyett a venv Pythonjat kell
> hasznalni: `.venv\Scripts\python -m refreshswitcher status`. Ha veletlenul
> a rendszer Pythonjat hasznalod, a program ezt megmondja, es nem
> stacktrace-szel all le. A `status` parancs kiirja, melyik Pythont hasznalja.

A regi inditoszkriptek tovabbra is mukodnek (`python tray.py`,
`python install_task.py install`, `python refresh_switcher.py`).

### Kilepes

Jobb klikk a tray ikonra → **Kilepes**. A program ilyenkor visszaallitja az
alapertelmezett frekvenciat.

## Beallitasok

A `config.json` fajlt kell szerkeszteni. **A program menet kozben ujraolvassa**,
nem kell ujrainditani. Hibas JSON eseten az utolso ervenyes beallitas marad
ervenyben, es a hiba a naploba kerul.

```json
{
    "monitor": 1,
    "default_refresh_rate": 120,
    "check_interval": 5,
    "enforce_default": true,
    "restore_on_exit": true,
    "log_level": "WARNING",
    "games": {
        "Diablo IV.exe": 300,
        "valorant.exe": 240,
        "GTA5.exe": 240,
        "RocketLeague.exe": 240
    }
}
```

| Beallitas | Leiras | Alapertelmezett |
|-----------|--------|-----------------|
| `monitor` | Monitor sorszama (1 = elso) **vagy** neve (pl. `"\\\\.\\DISPLAY2"`, `"AW2725"`) | `1` |
| `default_refresh_rate` | Frekvencia Hz-ben, ha nem fut jatek | `60` |
| `check_interval` | Ellenorzes gyakorisaga masodpercben (0.5–3600) | `5` |
| `enforce_default` | Jatek nelkul is kenyszeritse-e az alapertelmezettet | `true` |
| `restore_on_exit` | Kilepeskor allitsa-e vissza az alapertelmezettet | `true` |
| `log_level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `WARNING` |
| `games` | `"exe_nev": frekvencia_hz` parok | `{}` |

A jatek exe nevet a Feladatkezeloben (Task Manager) nezheted meg futas kozben.
A nev **kis/nagybetu-fuggetlen**, es a `.exe` vegzodes elhagyhato — a `"cs2"`
es a `"CS2.exe"` ugyanazt jelenti.

## Eroforrasigeny

A program **nem porgeti a processzort**: ket ellenorzes kozott alszik, es a
felebredest esemeny szakitja meg (kilepes, rendszeresemeny), nem ciklikus
ebredezes.

Egy ellenorzesi kor munkaja:

| Lepes | Koltseg |
|-------|---------|
| `config.json` beolvasasa | nehany szaz bajt a fajlrendszer gyorsitotarabol; a feldolgozas csak tenyleges valtozaskor fut |
| Monitorok felsorolasa | nehany Win32 hivas |
| Futo processzek atnezese | a processznevet **processzenkent egyszer** kerdezzuk le, es megjegyezzuk `(pid, inditasi ido)` szerint -- ez a legdragabb resz, es igy koronkent szinte ingyen van |
| Tamogatott frekvenciak | felbontasonkent egyszer, utana gyorsitotarbol |

Amivel a legtobbet tehetsz a fogyasztas ellen:

- **`check_interval` novelese** (pl. `10`): aranyosan kevesebb kor.
- **Rovid `games` lista**: ha ures, a program a processzeket sem nezi at.

Memoria: a tray ikonok gyorsitotarazva vannak, de csak a tenylegesen
megjelenitett szamokhoz (nehany kis kep), a processznev-gyorsitotar pedig
minden korben ujraepul, igy a megszunt processzek nem maradnak benne.

## Viselkedes gyakori helyzetekben

| Helyzet | Mi tortenik |
|---------|-------------|
| **Ket jatek fut egyszerre** | Az **eloszor elinditott** jatek frekvenciaja marad ervenyben. A masodik jatek beallitasa nem ervenyesul. |
| **Az elso jatek bezarul, a masodik fut tovabb** | A masodik jatek beallitasa lep ervenybe. Es igy tovabb, amig van futo jatek. |
| **A jatek a hatterben fut (visszateres az asztalra)** | **Semmi** — a program a *futo processzt* figyeli, nem az elotereben levot. A frekvencia valtozatlan marad, nincs villogas. |
| **Minden jatek bezarul** | Visszaall a `default_refresh_rate` ertekre. |
| **A kert Hz-et nem tudja a monitor** | A program **nem** valtoztat semmit, a monitor a jelenlegi modjan marad. A tray ikon **borostyan** szinu lesz, a tooltip kiirja a tamogatott frekvenciakat, es a naploba is bekerul — **egyszer**, nem minden korben. A config javitasa utan magatol ujraprobalja. |
| **A Windowsban alacsonyabb Hz van beallitva a kertnel** | `enforce_default: true` (alapertelmezett) eseten a program felemeli a `default_refresh_rate` ertekre. Ha kezzel akarod allitani a Hz-et, allitsd `enforce_default: false`-ra — ekkor csak jatek indulasakor nyul hozza. |
| **Alvas / hibernalas utan a Windows visszaall 60 Hz-re** | A program a Windows energia-esemenyeire is felirakozik, ezert az ebredes *azonnal* ellenorzest valt ki -- nem kell megvarni a kovetkezo `check_interval`-t. Ilyenkor a gyorsitotarazott dontesek (tamogatott modok, korabbi hibak) is elavulnak, es ujra megkerdezzuk a drivert. |
| **Ebredes utan a monitor meg nem jelentkezett be** | Par masodpercig nem talalhato: a program ujraprobal, es mivel az ebredes nullazza a hibaritkitast, a helyreallas masodperceken belul megtortenik. Az alvas es az ebredes idopontja is bekerul a naploba. |
| **Kijelzo kihuzasa futas kozben** | Ha a kivalasztott monitor eltunt, a tray ikon **piros** lesz, es a naploba hiba kerul. A program **nem all le**, hanem egyre ritkabban ujraprobal (max. 60 mp), es visszadugaskor magatol helyreall. |
| **Kijelzo kihuzasa elcsusztatja a sorszamokat** | A program eszreveszi, hogy a kivalasztott sorszam mas fizikai kijelzore mutat, es figyelmeztet a naploban. **Rogzitett kivalasztashoz add meg a monitor nevet** sorszam helyett. |
| **A Windows `Generic PnP Monitor`-nak nevezi a kijelzot** | Ebredes vagy ujracsatlakozas utan a monitor neve atmenetileg ilyenre valtozik, amig a driver be nem tolti a monitor adatait. A nev szerinti kivalasztas ilyenkor sem esik szet: a program megjegyzi, melyik eszkozhoz tartozott a nev, es azt hasznalja tovabb (egyszer naplozza is). |
| **A program osszeomlik vagy megszakad** | A frekvenciavaltas *dinamikus* (nem irodik a registrybe), igy egy ujrainditas visszahozza a Windows eredeti beallitasat. |
| **Nincs `config.json`** | A program **letrehozza** az alapertelmezettet az exe mellett, es elindul. |
| **A `config.json` hibas (elgepelt JSON)** | A tray ikon **piros** lesz, a tooltip kiirja a hiba helyet (sor/oszlop). A menubol megnyithato a config es a naplo; a javitas utan magatol ujratolt. |
| **Rossz Pythont hasznalsz (nem a venv-et)** | A program ertheto hibaval all le, es megmondja, melyik csomag hianyzik es melyik Pythont hasznalja -- nem dob stacktrace-t. |
| **Ket peldany indul el** | A masodik peldany azonnal kilep (nevesitett mutex), igy nem tudnak egymas ellen dolgozni. |

### Monitor rogzitese nev szerint

Tobb kijelzo eseten ez a megbizhatobb, mert a kihuzas/visszadugas nem
csusztatja el:

```bash
python -m refreshswitcher status
```

majd a kiirt nevbol egy egyedi reszlet:

```json
{ "monitor": "AW2725DF" }
```

A nev kis/nagybetu-fuggetlen, es reszlet is eleg. Ha a Windows atmenetileg
`Generic PnP Monitor`-kent jelenti a kijelzot (ez tipikusan alvas utan
fordul elo), a program a nevhez korabban azonositott eszkozt hasznalja
tovabb, es errol egyszer figyelmeztetest ir a naploba.

Ha a monitor neve nalad allandoan ingadozik, add meg helyette az
**eszkoznevet**, amit a `status` parancs zarojelben ir ki:

```json
{ "monitor": "\\\\.\\DISPLAY1" }
```

## Tray ikon

| Szin | Jelentes |
|------|----------|
| **Sotet szurke** + szam | Nincs jatek, alapertelmezett frekvencia |
| **Zold** + szam | Jatek fut, emelt frekvencia |
| **Borostyan** + szam | A kert frekvencia nem allithato be (lasd a tooltipet) |
| **Piros** `!` | Hiba: nincs ervenyes config vagy nem talalhato a monitor |

A tooltip (egeret ra) mutatja a program nevet, a jelenlegi Hz-et, a jatek nevet
es a monitort. A menuben megnyithato a `config.json` es a naplofajl is.

## Naplozas

A program a `refreshswitcher.log` fajlba logol az exe/szkript melletti mappaba.
Ha az a mappa nem irhato (pl. `C:\Program Files`), automatikusan a
`%LOCALAPPDATA%\RefreshSwitcher` mappaba valt.

- **Maximalis meret:** 512 KB + 2 backup fajl, osszesen ~1,5 MB
- **Alapertelmezett szint:** `WARNING` — jatekvaltasok es hibak
- **Kezeletlen kivetelek** (a hatterszalakban is) mindig a naploba kerulnek
- **Alvas / ebredes** idopontja is bekerul, igy az ebredes utani hibaknak van elozmenye
- A **`pystray` sajat hibai** (pl. a tray uzenethurok hibai) szinten ide kerulnek —
  enelkul az "eltunt a tray ikon, es semmi nincs a naploban" tipusu hiba
  kivizsgalhatatlan volna

Reszletes naplo hibakeresehez:

```json
{ "log_level": "DEBUG" }
```

## Onallo .exe keszitese

```bash
build.bat
```

Az eredmeny a `dist` mappaban: `RefreshSwitcher.exe` + `config.json`. Masold
mindkettot egy **irhato** mappaba (ne a `Program Files` ala), es futtasd az
exe-t. A config.json az exe *mellett* keresendo, igy Python telepitese nelkul is
szerkesztheto.

## Fejlesztes

```bash
pip install -r requirements-dev.txt
pytest -q          # tesztek (Windows nelkul is futnak)
ruff check .       # linter
ruff format .      # formazas
mypy               # tipusellenorzes
```

A tesztek hamis `win32api`/`win32con` modulokat hasznalnak (`tests/conftest.py`),
igy a teljes kijelzo-logika Windows nelkul is ellenorizheto.

### Felepites

| Modul | Feladat |
|-------|---------|
| `refreshswitcher/config.py` | Konfiguracio validalasa es biztonsagos ujratoltese |
| `refreshswitcher/display.py` | Win32 kijelzo API burkolat (korlatos ciklusok, gyorsitotar) |
| `refreshswitcher/games.py` | Futo jatekok felismerese, inditasi sorrend szerint |
| `refreshswitcher/switcher.py` | A figyelo- es valtologika (allapotgep) |
| `refreshswitcher/tray.py` | System tray felulet |
| `refreshswitcher/syswake.py` | Alvas/ebredes es kijelzovaltas eszlelese (Windows uzenetek) |
| `refreshswitcher/scheduler.py` | Task Scheduler integracio |
| `refreshswitcher/single_instance.py` | Egypeldany-vedelem |
| `refreshswitcher/logging_setup.py` | Naplozas + kezeletlen kivetelek elfogasa |
| `refreshswitcher/cli.py` | Parancssori felulet |

> **Megjegyzes:** a korabbi `service.py` (Windows szolgaltatas) eltavolitasra
> kerult. Egy Windows szolgaltatas a 0-as munkamenetben fut, ezert
> **elvileg sem tudja** megvaltoztatni a bejelentkezett felhasznalo kijelzojenek
> modjat; ezen felul a naplo utvonala fixen be volt egetve egy konkret
> felhasznalo mappajara. A helyes megoldas a Task Scheduler bejelentkezeskori
> inditasa, amit az `install` parancs allit be.
