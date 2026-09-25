# Dota Build Helper

A Windows companion for Dota 2: select a hero and position, compare builds from real matches, and follow item timings, skills and talent choices in a compact overlay.

**[Download the Windows installer](https://github.com/absalom86/dota-build-helper/releases/latest)** · [Detailed user guide](docs/USER_GUIDE.md)

## Quick setup for players

**Use [DotaBuildHelper-Setup.exe](https://github.com/absalom86/dota-build-helper/releases/latest/download/DotaBuildHelper-Setup.exe).** Run the installer and open **Dota Build Helper**. Windows 10/11 x64 is required. You do **not** need Python, Git, source code, or a terminal.

The app opens **Quick setup** on first launch. You can reopen it from the button at the top of the app.

1. **Save your STRATZ key.** Click **Get a key**, sign in to STRATZ and obtain an API token, then paste it and click **Save key**. A key privately shared with permission can also be used, subject to STRATZ's terms. No key is included; shared keys share limits. Existing saved keys are kept.
2. **Click Connect Dota.** The app finds Dota in your Steam libraries and installs its connection file automatically. No manual folder copying is needed for a detected installation. If several installations exist, choose one; if none is found, select the Dota installation folder once. The choice is remembered.
3. **Click Launch Dota.** Close Dota first if it is already running. This starts it through Steam with **`-gamestateintegration`** included. Use the helper's launch button each time; it does not permanently change Steam's launch settings.

Keep the helper open, choose your position **1–5** in **Builds**, and start a bot match. Detected heroes load builds automatically; the first available build is selected. You can change hero, position or build anytime. Manual hero/position changes stick for the match; **Resume detection** switches back to automatic selection.

**That's the normal setup.** Keep the default overlay and detection settings initially. OCR installation, screen calibration, overlay repositioning and shop-guide export are optional. Draft previews are labelled unconfirmed until strategy-time data arrives; missing draft data still needs manual hero selection. Role recognition is experimental, so selecting your position is the simplest starting point.

The overlay appears below the top-right stats when Dota is foreground. Use borderless/windowed fullscreen if it is hidden. Confirm clock, inventory and skill updates under **Overlay & connection** in the bot match before relying on them. A launch request or installed config alone does not prove that Dota is sending data.

<details>
<summary>Prefer Steam's Play button, need manual setup, or want the portable EXE?</summary>

To launch directly from Steam, add this once under **Dota 2 → Properties → General → Launch Options**:

```text
-gamestateintegration
```

Keep existing options, separated by spaces, then fully restart Dota. The helper's **Launch Dota** button already supplies this option for that launch.

If automatic connection-file installation fails, use **Overlay & connection → Export Dota game-state config…** and save `gamestate_integration_build_helper.cfg` into:

```text
<Dota installation>\game\dota\cfg\gamestate_integration\
```

Find the installation via **Steam → Dota 2 → Manage → Browse local files**. Create the final folder if needed. Export from your own helper: the config contains a private local connection token. The app backs up an existing helper config before replacing it and leaves other apps' configs alone.

The [portable DotaBuildHelper.exe](https://github.com/absalom86/dota-build-helper/releases/latest/download/DotaBuildHelper.exe) includes the same Quick setup flow. The installer is recommended for its Start menu shortcut and bundled instructions. Downloads are unsigned; releases include SHA-256 checksums.

</details>

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
| No game connection | Open Quick setup, reconnect/repair Dota, close Dota and use Launch Dota. Run only one helper instance. If using Steam Play, add the launch option there once. |
| Hero not detected during draft | Wait for a confirmed pick/strategy phase, or choose the hero manually. Draft field delivery varies. |
| Clock works but items/skills do not | Check their separate status indicators. A working clock does not prove those fields arrived. |
| Overlay hidden | Enable the overlay; try borderless fullscreen and Preview / reposition; check Ctrl+F8. Exclusive fullscreen is not verified. |
| STRATZ 401/403 | Check your token and account API access; save a replacement token if needed. |
| STRATZ 429 | Wait until the displayed retry time. Saved searches remain usable; repeated clicks do not bypass the cooldown. |
| Fewer than ten builds | The API may lack enough unique games for this hero/position or have missing data. Try another lookup later; results are not fabricated. |
| Quantity seems wrong | Inspect recorded/estimated labels, run Check quantities, or save a correction. Source logs can omit items. |
| Guide absent in Dota | Check the Steam account folder, restart Dota, and manually select the guide for the correct hero. Actual shop loading must be tested on your PC. |

Settings, encrypted credentials, cache and saved searches live in `%LOCALAPPDATA%\DotaBuildHelper` for the installed/portable app. `DOTA_HELPER_HOME` can override that folder. Do not share its contents. Optional OCR requires a separate Tesseract installation and calibration; it is not required for manual use or game-state integration.

**Updating:** close the helper normally and run the new installer under the same Windows account. Your key, settings and saved searches stay in the shared user-data folder; replacing the portable EXE also keeps them. Existing profiles do not repeat first-run setup. The key field stays empty intentionally and shows **Saved key in use**; you do not need to re-enter it. Settings and replaced credentials have last-good backups. If the key is present but unreadable, reopen the app under the Windows account that saved it—do not replace it just because another account cannot decrypt it. Only one helper can open the same profile at a time.

Patch data is bundled and can lag behind Dota updates. Item timings are examples, not deadlines. Missing source counts, exact skill levels, live draft delivery and current-map camp timings remain limited by available data.

<details>
<summary>For developers: run from source, test and build</summary>

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

</details>

## Repository access

This repository is public so anyone can read the code and download releases. Direct write access is reserved for **@absalom86**. Forks and proposed pull requests do not grant permission to change this repository. Do not include API keys, exported game-state configs, settings or game captures in issues or contributions.

## Attribution

Independent companion; not affiliated with Valve, STRATZ, OpenDota or Dota2ProTracker. Dota 2 and its marks belong to Valve. Builds use [STRATZ](https://stratz.com/api) and [OpenDota](https://docs.opendota.com/); D2PT is not scraped. Bundled metadata comes from [OpenDota constants](https://github.com/odota/dotaconstants). See [third-party notices](packaging/THIRD-PARTY.txt) and bundled license texts for dependency terms.
