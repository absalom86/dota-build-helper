# Dota Build Helper

A Windows companion for Dota 2: select a hero and position, compare builds from real matches, and follow item timings, skills and talent choices in a compact overlay.

**[Download the Windows installer](https://github.com/absalom86/dota-build-helper/releases/latest)** · [Detailed user guide](docs/USER_GUIDE.md)

## Quick setup for players

### 1. Install the app

Download **DotaBuildHelper-Setup.exe** from [Releases](https://github.com/absalom86/dota-build-helper/releases/latest), run it, and open **Dota Build Helper** from the Start menu. Python and dependencies are included; you do not need to install them separately. Windows 10/11, 64-bit is required.

A portable **DotaBuildHelper.exe** is also available. Releases are unsigned, so Windows may show an unknown-publisher warning. Download from this repository; each release includes SHA-256 checksums.

### 2. Add your STRATZ API key

1. Open [STRATZ API](https://stratz.com/api), sign in, and obtain an API token through your account's API access page.
2. In the helper, open **Overlay & connection → STRATZ connection**.
3. Paste the token and click **Save STRATZ key**.

No key comes with the app. Use your own token, or one privately shared by a friend with their permission and subject to STRATZ's terms. Shared tokens share request limits. Keep tokens out of screenshots, GitHub issues and source files. The app stores the key encrypted for your Windows user account.

### 3. Export your game-state config

1. In **Overlay & connection**, click **Export Dota game-state config…**.
2. In Steam, right-click **Dota 2 → Manage → Browse local files**.
3. Put the exported `gamestate_integration_build_helper.cfg` in:

   ```text
   <Dota installation>\game\dota\cfg\gamestate_integration\
   ```

   Create `gamestate_integration` if it does not exist. The filename must keep its `.cfg` extension.

Export the config from **your own helper installation**: it contains a local connection token. Do not reuse a friend's config or post it publicly. The installer does not edit Dota's files for you.

### 4. Add the Steam launch option

In **Steam → Dota 2 → Properties → General → Launch Options**, add:

```text
-gamestateintegration
```

Keep any existing launch options, separated by spaces. **Fully close and restart Dota after adding the option and config.**

### 5. Test in a bot match

1. Keep the helper open. Choose your position **1–5** in **Builds**.
2. Launch Dota in **borderless/windowed fullscreen** and start a bot match. A live matchmaking game is not required.
3. Lock in a hero. If Dota supplies your local hero during draft, three matching updates over at least two seconds preload a **draft preview**. This is not proof of lock-in; strategy-time data confirms the hero before play starts. Automatic data availability varies, so manual selection always works.
4. Click **Find builds**, then choose a match row. The first available build is selected automatically.
5. Check **Overlay & connection**: clock, inventory and skills each show their own fresh/stale/missing status.
6. Enable **Preview / reposition** to place the overlay, then disable preview for normal play. Default visibility shortcut: **Ctrl+F8**.

The overlay normally appears below the top-right game stats. It shows starting items through 1:00, early parts through 5:00, and laning supplies through 10:00 by default. The full major-item build, next skill and talent choices stay visible. Width, text size and supply duration are adjustable.

**Position detection:** open **Overlay & connection → Draft role recognition**, install Tesseract with English data, calibrate a tight crop around **your assigned-role text**, and enable recognition. Three confident matching reads during draft select the position. This is experimental screen recognition, not a confirmed assignment supplied by GSI. Without it, the app keeps your saved position. Bot/unranked games may not assign a role.

**Swaps and overrides:** change either dropdown in **Builds** whenever you swap heroes or positions. The helper reloads builds and preserves each manual choice for this match. **Resume detection** releases both overrides; a new detected match also clears them. Automatic mode follows hero swaps reported by Dota. **More options** lets you disable draft previews or automatic hero selection. Preview lookups are limited to one per ten seconds and reuse saved searches.

**Try without Dota or an API key:** choose **Offline demo**, **Anti-Mage**, position **1**, then **Find builds**. Demo builds are synthetic test data.

## Using builds

- **Compare games:** patch evidence comes before premier-event/pro/pub preferences, then match recency. Numeric MMR is shown only when the provider supplies it. This is not a ranking of team strength or a complete copy of D2PT's list.
- **Check starting quantities:** counts are labelled recorded, estimated or corrected. **Edit quantities** saves your correction; **Reset to source** removes it. Tango quantities are purchased packs, not remaining charges.
- **Compare sources:** the selected STRATZ match can be checked against OpenDota in the background. **Check quantities** lets you review disagreements. Alternative counts are never applied automatically.
- **Use the in-game shop:** click **Export to Dota shop…**, save under `Steam\userdata\<your account>\570\remote\guides`, restart Dota after your game, and choose the Helper guide in the shop. The helper remembers the folder and flags outdated exports; changing builds in the helper does not switch Dota's selected guide.
- **Draft helper:** role rankings and matchup suggestions are available; enter visible picks manually if Dota does not supply them. Invoker has a ten-spell key reference. Pull/stack cues are approximate and follow your selected position.

See the [user guide](docs/USER_GUIDE.md) for overlay controls, draft behavior, source evidence and optional portrait/role recognition.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| No game connection | Export the config from this installation, check its folder/extension, add `-gamestateintegration`, then restart Dota. Run only one helper instance. |
| Hero not detected during draft | Wait for a confirmed pick/strategy phase, or choose the hero manually. Draft field delivery varies. |
| Clock works but items/skills do not | Check their separate status indicators. A working clock does not prove those fields arrived. |
| Overlay hidden | Enable the overlay; try borderless fullscreen and Preview / reposition; check Ctrl+F8. Exclusive fullscreen is not verified. |
| STRATZ 401/403 | Check your token and account API access; save a replacement token if needed. |
| STRATZ 429 | Wait until the displayed retry time. Saved searches remain usable; repeated clicks do not bypass the cooldown. |
| Fewer than ten builds | The API may lack enough unique games for this hero/position or have missing data. Try another lookup later; results are not fabricated. |
| Quantity seems wrong | Inspect recorded/estimated labels, run Check quantities, or save a correction. Source logs can omit items. |
| Guide absent in Dota | Check the Steam account folder, restart Dota, and manually select the guide for the correct hero. Actual shop loading must be tested on your PC. |

Settings, encrypted credentials, cache and saved searches live in `%LOCALAPPDATA%\DotaBuildHelper` for the installed/portable app. `DOTA_HELPER_HOME` can override that folder. Do not share its contents. Optional OCR requires a separate Tesseract installation and calibration; it is not required for manual use or game-state integration.

Patch data is bundled and can lag behind Dota updates. Item timings are examples, not deadlines. Missing source counts, exact skill levels, live draft delivery and current-map camp timings remain limited by available data.

## Run from source

Install **Python 3.12+** and Git, then run in PowerShell:

```powershell
git clone https://github.com/absalom86/dota-build-helper.git
cd dota-build-helper
.\setup.ps1
.\launch.ps1 -Source
```

If `python` does not point to the intended installation:

```powershell
.\setup.ps1 -Python 'C:\path\to\python.exe'
```

If PowerShell blocks an unsigned script, invoke it without changing the machine policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\launch.ps1 -Source
```

Development data stays in `.local/`, which is ignored by Git. For terminal diagnostics run `.\.venv\Scripts\python.exe -m dota_helper`. For an offline demo use `.\launch.ps1 -Source -Demo`.

### Test and build

```powershell
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_history.py
.\.venv\Scripts\python.exe -m pytest tests/test_history.py -q
.\.venv\Scripts\python.exe scripts\verify_ui.py
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build-exe.ps1
.\scripts\verify-exe.ps1
```

The test suite runs without a STRATZ key or Dota. `requirements.lock.txt` records the tested dependency versions. To rebuild the installer, install **Inno Setup 6** and run `build-installer.ps1`; pass `-Compiler 'C:\path\to\ISCC.exe'` if needed. Close the helper before overwriting its executable. Build output belongs in `dist/`, not Git; publish installers as release assets.

## Repository access

This repository is public so anyone can read the code and download releases. Direct write access is reserved for **@absalom86**. Forks and proposed pull requests do not grant permission to change this repository. Do not include API keys, exported game-state configs, settings or game captures in issues or contributions.

## Attribution

Independent companion; not affiliated with Valve, STRATZ, OpenDota or Dota2ProTracker. Dota 2 and its marks belong to Valve. Builds use [STRATZ](https://stratz.com/api) and [OpenDota](https://docs.opendota.com/); D2PT is not scraped. Bundled metadata comes from [OpenDota constants](https://github.com/odota/dotaconstants). See [third-party notices](packaging/THIRD-PARTY.txt) and bundled license texts for dependency terms.
