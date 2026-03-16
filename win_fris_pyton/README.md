# Display Refresh Rate Switcher

Windows 11 program ami automatikusan valtoztatja a kijelzo frissitesi frekvenciajat jatekok inditasakor es leallitasakor.

**Szerzo:** ManSzabi

## Funkciok

- Automatikus frekvenciavaltas jatek inditasakor/leallitasakor
- Jatekonkenti kulon frekvencia beallitas
- Tobb monitor tamogatas, kivalaszthato melyiket allitsa
- System tray ikon a jelenlegi frekvencia kijelzesevel
- Bejelentkezeskor automatikusan elindul (Task Scheduler)

## Telepites

### 1. Python telepitese

Toltsd le es telepitsd a Python 3.10+ verziojat: https://www.python.org/downloads/

Telepitesnel jelold be a **"Add Python to PATH"** opciot.

### 2. Projekt letoltese

```bash
git clone https://github.com/manszabi/win_fris_pyton.git
cd win_fris_pyton
```

### 3. Fuggosegek telepitese

```bash
pip install -r requirements.txt
```

Fuggosegek:
- `psutil` — futo processek figyelese
- `pywin32` — Windows API (kijelzo beallitasok)
- `pystray` — system tray ikon
- `Pillow` — ikon kep generalas

### 4. Task Scheduler telepitese (automatikus inditas)

Futtasd **adminisztratorkent**:

```bash
python install_task.py install
```

Ez letrehozza a Task Scheduler feladatot es azonnal el is inditja a programot. Minden bejelentkezeskor automatikusan elindul.

## Hasznalat

### Kezzel inditas (teszteles)

```bash
python tray.py
```

### Task Scheduler parancsok

Futtasd **adminisztratorkent**:

```bash
python install_task.py install   # Telepites + azonnali inditas
python install_task.py start     # Inditas
python install_task.py stop      # Leallitas
python install_task.py remove    # Eltavolitas
```

### Kilepes

Jobb klikk a tray ikonra (ora melletti terulet) → **Kilepes**

## Beallitasok

A `config.json` fajlt kell szerkeszteni. A program menet kozben is ujraolvassa, nem kell ujrainditani.

```json
{
    "monitor": 1,
    "default_refresh_rate": 120,
    "check_interval": 5,
    "games": {
        "Diablo IV.exe": 300,
        "valorant.exe": 240,
        "GTA5.exe": 144,
        "RocketLeague.exe": 165
    }
}
```

| Beallitas | Leiras |
|-----------|--------|
| `monitor` | Melyik monitort allitsa (1 = elso, 2 = masodik, stb.) |
| `default_refresh_rate` | Alapertelmezett frekvencia Hz-ben (jatek nelkul) |
| `check_interval` | Milyen gyakran ellenorizze a futo jatekokat (masodpercben) |
| `games` | Jatekok listaja: `"exe_nev": frekvencia_hz` formatumban |

### Uj jatek hozzaadasa

Add hozza a jatek exe nevet es a kivant frekvenciat a `games` szekciohoz:

```json
"games": {
    "cs2.exe": 240,
    "Fortnite.exe": 165
}
```

A jatek exe nevet a Task Manager-ben (Feladatkezelo) nezheted meg a jatek futasa kozben.

### Tamogatott frekvenciak lekerdezese

```bash
python refresh_switcher.py
```

Kiirja az osszes monitor tamogatott frekvenciait.

## Tray ikon

- **Sotet hatter + szam**: nincs jatek, alapertelmezett frekvencia
- **Zold hatter + szam**: jatek fut, emelt frekvencia
- **Tooltip** (egeret ra): program neve + jelenlegi Hz + jatek neve

## Logok

A program a `service.log` fajlba logol a projekt mappaban.

- **Maximalis meret:** 500 KB + 1 backup fajl (`service.log.1`), osszesen ~1 MB
- **Log szint:** WARNING — csak jatek inditasa/leallitasa es hibak kerulnek a logba
- **Rotacio:** ha eleri az 500 KB-ot, automatikusan atnevezi `.log.1`-re es uj fajlt kezd
