# User guide

For installation and STRATZ/Steam setup, see the [README](../README.md).

## Overlay

The preferred default width is 270 pixels, placed at the top-right with a 160-pixel gap below the top edge for game stats. The overlay stays within the screen, including Windows display scaling. It uses columns and temporarily smaller text when needed, keeping your preferred width, position and text size for when there is room again. Crowded pregame views can use three columns; draft suggestions use a full-width column to avoid unnecessary wrapping. **Position below top-right game stats** restores the top-right placement; the exact gap may need adjustment for your HUD scale.

Open **Overlay & connection** and enable **Preview / reposition** to drag the overlay or change its width. Set **Preferred width** from 270–600 pixels, **Overlay text size** from 11–16 pixels, opacity and a Ctrl+function-key shortcut (default **Ctrl+F8**). The fit status reports the actual size and any temporary text adjustment. Exceptionally long content shows a **More below** notice and a scrollbar usable in Preview, instead of extending offscreen. Returning to Dota resets that view to the top. While Dota is foreground, the overlay becomes click-through and does not request focus. Outside Dota it hides unless preview is enabled.

The full major-item build, next skill and recorded talent picks are kept. The highlighted starting-buy card includes item quantities and disappears at 1:00. Early components have their own section until 5:00; consumables stay in a separate **Supplies** section until 10:00 by default. These temporary sections show purchases from one minute ago through two minutes ahead, with full lane-purchase summaries available as Preview tooltips. Change **Laning supplies until** to 5–15 minutes. Wards after the starting buy and recipes remain hidden. Optional item advice and compact lane pull/stack timers sit below the build; timer windows remain approximate and camp availability is unknown.

Borderless fullscreen is the target mode. Exclusive fullscreen capture/overlay visibility is **not verified**. Test your configuration before relying on it. The app does not inject into Dota or change display settings.

### Invoker spell reference

Selecting Invoker manually or receiving his confirmed hero from game state shows all ten spell recipes automatically, even before a build lookup finishes. The reference uses the **default keys**: Q = Quas, W = Wex, E = Exort; enter the three orbs, press R to Invoke, then use the spell's displayed D/F slot and target as required. Custom/legacy bindings are not detected. The table lists orb recipes, not current spell availability or cooldowns.

The compact spell reference uses five rows with two spells per row, with each recipe above its full spell name. When the overlay uses a wider, split layout, the reference uses one column beside the build. All ten recipes remain available without scrolling. The table is hidden while draft recommendations are displayed or another hero is selected.

### Kez combo reference

Selecting Kez shows a compact card beside the build, with nine sequences grouped into early game, mid game, Scepter and defense. The **Sai:** or **Katana:** label identifies your starting form, before the first key; an opening D switches out of that form. It also works before a lookup finishes. It hides during draft recommendations and when you change heroes. Use **Preview / reposition** to inspect it without a live match; hover the card for full ability names and execution notes.

These use **default QWER keys**, with **D = Switch Discipline** and **attack = right-click**. Begin in the stated stance with every required ability learned and ready. Custom bindings, current stance, cooldowns and Scepter ownership are not detected by this reference. Only the three sequences under **After Aghanim's Scepter** require Scepter; both defensive sequences work without it. Shard does not substitute for Scepter.

| Stage / purpose | Start | Sequence |
| --- | --- | --- |
| Early: parry trade | Sai | E → successful parry → D → Q |
| Early: chase | Sai | Q → D → W → attack |
| Mid: marked burst | Sai | R → wait for the mark → D → Q → W → attack |
| Mid: fight / heal | Katana | Q → W → R |
| Scepter: Rush + Echo | Katana | D → Q → D → Q → attack |
| Scepter: silence engage | Katana | D → W → D → W → D → Q → D → Q |
| Scepter: Veil + Echo + Dance | Katana | D → R → wait for mark → D → Q → R |
| Defense: Grapple + Veil escape | Katana | W (tree) → land → D → R |
| Defense: Dance + retreat | Katana | R → finish → W (tree) |

For the parry, face the attacker and wait for a successful block. For Q → W, begin within Echo Slash range and Grapple after the first slash; Raptor Dance supplies area damage and healing. Without Scepter, corresponding ability slots share cooldowns. With Scepter, cast the first spell within three seconds after each switch to preserve the paired ability's cooldown; weapon spells refresh D. Abilities already cooling down are not refreshed. Katana E is a baseline active ability; Shard upgrades it and the parry.

**What does Katana D → Q → D → Q → attack do?** Start in Katana with Scepter and the abilities ready:

1. **D:** switch to Sai and open Scepter's protected-cast window.
2. **Q:** activate Falcon Rush. The protected cast leaves Echo Slash ready and refreshes D.
3. **D:** switch back to Katana; Falcon Rush stays active.
4. **Q:** aim Echo Slash through the target. Rush adds secondary attacks to the slashes.
5. **Attack:** right-click to follow up while Rush remains active.

This is a short damage combo. The opening D is necessary for the Scepter protection; simply starting in Sai and pressing Q can put Echo Slash on cooldown. Position within Echo Slash range before the second Q. The short sequence provides neither a silence nor a mark. The longer **silence engage** starts with Talon Toss and Grappling Claw to silence and approach the target, then uses the same Rush/Echo combination. These spell sequences still require aiming and appropriate targets; they are not a promise that every hit will connect.

**Ultimate combination:** with Scepter, **Katana D → R → mark → D → Q → R** uses Raven's Veil, Echo Slash and Raptor Dance. Cast Veil as the first spell within three seconds of the opening switch so Dance stays available. Let Veil's mark reach the target, switch back, and use Echo to trigger the mark before Dance. Begin close enough for Dance; it heals from damage dealt and does not guarantee that enemies stay in range.

**Defensive retreats:** **Katana W (tree) → land → D → R** grapples toward safety, then uses Veil's basic dispel, movement speed and invisibility to retreat. Let the grapple finish before switching and casting Veil, then move away without attacking or casting: those actions break invisibility, and detection can still reveal you. **Katana R → finish → W (tree)** uses Dance near enemies, then grapples away after it completes. Dance's healing requires damage to targets; casting it away from enemies is not a free heal. Both sequences need a reachable tree, enough mana and ready abilities. These short retreats are practical combinations derived from the ability mechanics, not measured popularity data.

The card abbreviates the Katana/Sai pairs as **Echo/Rush**, **Claw/Toss**, **Impale/Parry** and **Dance/Veil**. Full names are Echo Slash/Falcon Rush, Grappling Claw/Talon Toss, Kazurai Katana/Shodo Sai and Raptor Dance/Raven's Veil.

These are curated practice sequences, not measured popularity rankings or automatic inputs. Mechanics were checked against [Valve's Kez data](https://www.dota2.com/hero/kez) on 27 September 2026; combo references are [Chili's carry guide](https://steamcommunity.com/sharedfiles/filedetails/?id=3460471608), [A Book of Five Wings' mid guide](https://steamcommunity.com/sharedfiles/filedetails/?id=3433837612) and [Brain Damage's Falconer's Cookbook](https://steamcommunity.com/sharedfiles/filedetails/?id=3513065509). Guide advice can age between patches; follow the current in-game ability descriptions.

### Shadow Shaman lane and combo reference

Selecting Shadow Shaman shows lane, Blink control and healing tips immediately, even before a build loads. Game detection uses the same selection path. The card hides during draft recommendations and for other heroes. Enable **Preview / reposition** to read the full execution notes by hovering the card.

- **Lane:** use **Q · Ether Shock** to secure a ranged creep your core cannot safely last-hit, ideally hitting an enemy hero too. Let your core take the last hit when possible. This tip does not override the selected build's skill order or require Q at level 1.
- **Blink control:** **Blink → W · Hex → R · Mass Serpent Ward → E · Shackles**. Blink close enough for both disables, place wards within attack range of the target, then let Shackles channel. Moving or casting another spell interrupts your channel. Check mana and spell readiness first; enemy allies can still interrupt you.
- **Low health:** Shackles heals you while channeling, including on enemy or neutral creeps. Choose a healthy creep that can survive the channel, away from enemy interruptions and dangerous camp attacks. Avoid taking your core's last hits and preserve mana for a save or kill. Use Tango or an available Stick/Wand **before** the channel. If you have a spare Iron Branch, plant it and eat its tree with Tango for double regeneration duration; this consumes the branch. Use a Healing Salve from safety when appropriate.

These are static tips with **default QWER bindings**; Blink uses your item-slot key. The card does not detect low health, spell readiness or custom bindings and sends no inputs to Dota. Mechanics checked on 29 September 2026 against [Valve's Shadow Shaman data](https://www.dota2.com/datafeed/herodata?language=english&hero_id=27), the [DotaCoach support guide](https://steamcommunity.com/sharedfiles/filedetails/?id=2699962568), and the [Tango description](https://dotacoach.gg/en/items/tango). Follow current in-game descriptions after patches.

### Use a selected build in Dota's shop

1. Select a game/build, review its starting-quantity preview, then click **Export to Dota shop…** below it.
2. Save the `.build` file in `Steam/userdata/<your account>/570/remote/guides`. The app discovers local Dota accounts and asks which one when several exist. If Steam isn't found, choose this folder yourself or copy the exported file there later.
3. Restart Dota after your current game. Open the shop's guide selector for that hero and choose the guide titled **Helper · Hero Position · Player/MMR · Match**.

Recorded starting quantities, including saved corrections, are preserved as repeated item entries. Missing quantities cannot be recovered by export alone; use **Edit quantities** when you know the correct count. Recorded, estimated, and corrected quantities retain their evidence in guide notes and item tooltips. Early components and full item milestones are grouped by time, with a separate supplies section for recorded purchases in the first ten minutes; hover items for timings. Unlike the timed overlay, these saved guide sections stay available throughout the match. Skills and talents appear as a recorded sequence in the overview. Exact hero-level assignments are unavailable, so the export does not add skill level-up prompts. Continue using the overlay for these.

The app remembers your chosen account folder. Each route gets its own stable filename, and the **Shop guide** status shows its match ID and whether the export is up to date, changed, or missing. Export again after changing quantities or when the status requests it. “Up to date” describes the saved file; it does not confirm that Dota loaded or selected it. Selecting another build in the helper does not switch your guide inside Dota. These are local guides, not Workshop uploads. Native formatting was checked against files saved by Dota on this PC and [a native guide example](https://github.com/Darktex/d2pt-guides/blob/main/examples/sven_carry_example.build). Actual shop visibility and purchases still need an in-game test.

### Starting quantities and source checks

The preview labels every item **recorded**, **estimated**, or **corrected**. Recorded means a purchase event exists; it does not prove that the provider captured the whole starting inventory. Tango quantities count purchased packs, not the charges remaining during play. **Edit quantities** saves a correction for the selected match and hero without changing the original purchase log. **Reset to source** removes that correction and restores recorded counts, including the usual labelled branch estimate where applicable.

For uncorrected STRATZ builds, one recorded starting branch and fewer than six non-ward starting purchases produce **two branches (estimated)**. This requested fallback is a guess, not an inventory-slot calculation. It does not apply to OpenDota builds or override explicit corrections.

After selection, the app can compare that STRATZ game's starting purchases with OpenDota in the background. Only the selected match is checked, and matching the player requires an explicit account ID or player slot. Older saved builds without that identity ask you to refresh the lookup. **Check quantities** shows the comparison; if counts disagree, choosing **No** keeps the current counts, and **Yes** saves the OpenDota counts as an accepted correction. Automatic checks never replace quantities. Saved corrections take priority; reset them before requesting another source comparison. Matching logs corroborate recorded counts but still do not prove complete starting inventory. Unavailable results leave the build usable.

## Updating the app

From v0.1.14, the packaged app checks GitHub for a newer stable installer at startup, at most once a day. Click **Updates → Download**, then **Install and restart** after your match. The app verifies the download, saves and closes, and the installer reopens the installed copy. **Later** postpones the reminder for a day. **Check now** checks manually; GitHub rate-limit cooldowns still apply.

Your STRATZ key, settings and saved searches remain in `%LOCALAPPDATA%\DotaBuildHelper`. Do not uninstall first or delete that folder. For older versions, run the latest installer manually once. A portable copy is not overwritten by the updater: it installs the app, which you can then open from the Start menu. If checking or downloading fails, keep using the current app or use the [latest release page](https://github.com/absalom86/dota-build-helper/releases/latest).

## Optional endgame references

In **Builds**, open **Endgame options** beside **Skills & talents**. Choose from up to three distinct recorded six-slot finishes for the same hero and position. The app uses loaded games and saved searches, preferring patch evidence, pro sources and higher-rated pubs. It shows the source match, rating and patch; older or unverified patches remain labelled. Switching an example does not select that game or change your purchase timings, skill order or progress.

Six-slot finishes are optional ideas for what to build towards. They never promote a game in the match list or replace a higher-ranked result. Short games remain selectable. No extra API calls are made solely to find a finish, and no items are invented if a complete recorded example is unavailable. Saved examples survive subsequent searches. Shop exports include the chosen example in a separate reference section and credit the other game when applicable. The overlay continues following your selected game.

## Draft helper

Open **Draft helper**, enter up to five confirmed enemy picks, and choose **Any hero**, **Carry**, or **Support**. Suggestions update after edits; turn off automatic updates to use **Suggest picks** manually. Use **Exclude hero** for allied picks and bans. Enemy picks and excluded heroes cannot be recommended. Duplicate/conflicting selections are rejected.

The table ranks up to ten heroes and shows each one's strongest and weakest observed matchup. Select a row for individual win counts, sample sizes and source links. **Use selected hero in Builds** opens that hero's build search; it does not pick a hero in Dota. **Show suggestions in overlay** displays up to eight picks. Confirmed local-player game state switches the overlay back to build guidance. **Clear draft** resets enemy picks and exclusions; **New match** resets the draft too.

Draft picks fill when Dota supplies usable team/pick data; otherwise use manual enemy entry. Live player-mode availability is not guaranteed. OpenDota's matchup aggregation covers roughly a rolling year of tracked matches and does not expose patch, position or rank filters. It is **not specifically current-patch or high-MMR evidence**. The Carry/Support pools use broad metadata tags, not position-specific matchup results. Ally selections only exclude unavailable heroes; team synergy is not modeled.

Ranking requires at least 20 observed games against **every** chosen enemy. OpenDota returns the queried enemy's wins, so candidate wins are `games - enemy_wins`. Each pair is shrunk toward 50% with 100 neutral prior games, then the pairs are averaged equally. This is a historical matchup score, **not a full-draft win probability or a causal counter advantage**. A top-ranked hero can still have unfavorable matchups. Pair counts may overlap and are never summed as independent draft matches. If one enemy's data fails, no partial-draft ranking is shown. Results from an outdated selection are discarded.

Matchup responses are cached for six hours and read immediately, with visibly labeled stale fallback. Missing enemy responses are fetched concurrently within an eight-second foreground budget. Slow aggregation fails promptly and leaves the draft editable. No D2PT scraping or extra credentials are required.

## Connect Dota

Use **Quick setup** at the top of the app. Save a STRATZ key, click **Connect Dota** to automatically find the installation and write the connection file, then **Launch Dota**. Close Dota before launching. The launch button supplies `-gamestateintegration` each time; it does not edit Steam's saved launch options. If you use Steam's Play button, add that option in Steam once. Test the connection in a bot match.

A folder prompt appears only when discovery finds no installation or multiple installations. The chosen folder is remembered. The app validates the Dota executable before writing its own config and backs up a previous helper config. Permission errors are shown so you can use the manual export fallback.

For manual setup, export the config under **Overlay & connection**, put it in `<Dota install>/game/dota/cfg/gamestate_integration/`, add `-gamestateintegration` in Steam and fully restart Dota.

The receiver binds only to `127.0.0.1:38765` and checks a generated token. The token lives in the app's local settings; keep the exported configuration local. Quick setup installs the config when you click Connect Dota. Do not run multiple copies on the same port.

Local-player GSI can confirm a hero in strategy/pregame/in-progress phases, provide the game clock and update inventory/skills. Hero-selection-phase messages are not treated as proof of lock-in. Spectator-shaped payloads are ignored. These integrations are tested with fixtures and a local HTTP round-trip; actual Dota delivery remains to be tested.

During selection, three matching local-hero updates over at least two seconds can preload a build as a labelled **draft preview**. Hovering a hero can produce a preview; it becomes confirmed only after strategy-time data arrives. Changing the preview hero triggers at most one lookup per ten seconds, using saved searches when available. Disable previews under **Builds → More options** if you prefer to wait for confirmation.

Change the hero or position dropdown anytime to reload builds and keep a manual override for that field. A position change preserves received inventory and skills for the same hero. A manually selected different hero does not receive another hero's inventory or skills. **Resume detection** releases both overrides and waits for fresh game data. Overrides also clear on a detected new game. Automatic hero selection follows subsequent hero swaps reported by Dota.

Assigned position uses optional **Draft role recognition** under **Overlay & connection**. Install Tesseract with English data, calibrate only your assigned-role label, and enable recognition. Three high-confidence reads during fresh draft telemetry apply the role and refresh an existing hero's builds. The app keeps your saved position if OCR is off or inconclusive; it does not infer an assigned position from a hero's common role. Role OCR is experimental and needs verification on your draft screen.

Connection diagnostics track **Hero**, **Clock**, **Inventory**, **Charges**, and **Skills** independently, with a fresh/stale/missing status and time since each was received. A working clock does not imply that item or skill data arrived. Received charges are tracked separately from item quantities; they do not establish how many Tango packs were bought. Item completion and inventory-dependent hints require fresh inventory data. This pass does not add automatic restock advice from missing or stale charges.

The game clock freezes if telemetry becomes stale, rather than continuing through an unknown pause. **Sync manual clock** switches to an explicitly labeled manual estimate; pause it yourself when the match pauses. Check **Use game clock** to switch back.

## Screen recognition

Screen recognition is local, opt-in, and needs calibration for the display layout:

1. Select your hero in the Builds tab.
2. Set the monitor number. Click **Calibrate region**, then Alt-Tab to Dota during the five-second countdown.
3. On the captured image, drag around **your own confirmed hero portrait**, not the hero browser or another player's slot.
4. Click **Save selected hero's reference** and Alt-Tab back to the same portrait during its countdown.
5. Enable local capture. Save references for other heroes as needed.

Matching requires three agreeing frames, a similarity threshold and separation from other saved references. Blank captures are rejected. A candidate remains available for 30 seconds after Alt-Tab so you can confirm it. Screen matching alone cannot establish lock-in: use **Use detected hero**, or let GSI confirm it. Recalibrate after resolution, monitor or HUD changes. This is calibrated image comparison, not a universal OCR model. No screenshots are uploaded; only explicitly saved portrait crops are retained.

## How the builds are sourced

STRATZ HTTP 429 means an API request allowance has been exhausted. The app now saves the server's `Retry-After` time and blocks new requests across lookups/restarts until that time. Fresh response-cache hits and saved tournament builds remain usable. After the displayed time, click **Find builds** to retry; the app does not poll during cooldown.


- **Recommended builds** combines tournament games, pro-player games, and high-ranked pubs from the last **90 days across patches**. Premier events precede other tournaments, pro players and pubs; rated pubs sort by MMR, then rank, with newest games breaking equal-rating ties. A patch difference does not mark a recent game outdated or demote it. Patch numbers remain reference information. Previously saved games remain selectable; games within 90 days rank ahead of older saved examples. This ranks known event/player categories, not measured team strength.
- STRATZ pub discovery continues through available guide summaries in pages of 50 until the shared eight-second deadline. When guides run out, it checks up to 40 active high-ranked players' hero/position-filtered histories, with up to 50 matching games per player. Targeted STRATZ detail requests contain up to ten games each. Every usable game found stays selectable, including games with the same purchase/skill sequence; ten is not a search target or result limit. Results appear progressively.
- Pub discovery requires ranked Immortal games and verifies the actual hero and position again in match details. It uses a rolling 90-day window independent of patch release dates. The app removes legacy patch-age warnings from recent saved builds as well. Enough builds cannot be guaranteed for every unusual hero/position combination. Missing purchases, missing skills and source errors are reported; other roles and synthetic builds are never used to fill the count.
- STRATZ match bracket and player leaderboard rank are labeled separately. Neither is numeric MMR. User-supplied reference IDs are comparison games, not proof that guide discovery reproduces D2PT's list. Source patch labels are preserved even when they differ from bundled metadata; an unavailable version shows as unknown. Exact hero-level skill assignments are still unavailable from the lightweight upgrade list.
- The STRATZ credential is saved with Windows DPAPI encryption, bound to the Windows user, in the app's data directory. Replace it in **Overlay & connection → STRATZ connection**. An optional `STRATZ_API_TOKEN` environment variable takes precedence. Credentials are excluded from settings, response-cache names, error messages and the executable. A copied EXE needs a separately saved credential on another Windows account.
- **OpenDota · recent pubs** remains optional. A single OpenDota Explorer query selects up to 100 sampled ranked pubs containing the hero from the last 90 days, with all ten recorded rank tiers Immortal (`avg_rank_tier = 80`, `num_rank_tier = 10`). It uses the public-match table's indexed hero arrays; it does not page through every high-level game. Match details still validate date, position, purchases, ranked lobby and conflicting profile ranks.
- This is an independent OpenDota sample, **not D2PT coverage or the highest numeric MMR games**. Immortal brackets cannot distinguish 7k from 10k. An empty sample remains empty; old league games are not silently substituted.
- **Avg. MMR** and **Avg. rank** are separate columns, so a game's MMR does not hide its rank. `PRO` appears beside the player name. `—` means unavailable, and `(bracket)` identifies a broader match-rank fallback rather than an observed average. STRATZ's `averageRank` is used only when it supplies a valid medal-scale value; a player's profile rank is never used as the match average.
- The helper samples OpenDota's public live feed in the background at most every two minutes while running outside Offline demo. Positive `average_mmr` readings and hero IDs are stored by exact match ID in a separate local cache, retained for up to 30 days (10,000 games maximum), and applied to matching builds and saved searches. Recommended/STRATZ searches also resolve captured games containing the selected hero, alongside the normal search with a separate eight-second limit. STRATZ verifies completion, role and build details; missing games can use an independently parsed OpenDota build with a matching estimated position. Verified Immortal games below 7,000 MMR are eligible; lower-MMR OpenDota games need explicit Immortal match-rank evidence or ten recorded Immortal profiles, with no conflicting lower ranks. Those profiles qualify discovery but are never converted into numeric MMR or substituted for the average-rank column. Tournament and demo rows do not receive pub ratings. A late MMR reading can improve ordering without changing a manually selected build, and verified averages survive detail refreshes and provider changes. Feed failures keep prior readings, and HTTP 429 pauses requests. There is no extra API key or Steam login. Coverage is limited to games observed in the live feed; this cannot recover arbitrary old match MMR or a player's private MMR. Newly captured games may still be live or unparsed; retry once build data becomes available.
- **Legacy league examples** retains the previous hero-match endpoint as a separate optional source. That endpoint joins league records and is unsuitable for reproducing D2PT's pub list. Its profile-rank evidence remains MMR unverified.
- `position_est` supplies the **estimated** position (1–5). The desktop uses position only, with no separate lane filter. Unknown positions never silently match a requested position.
- OpenDota and STRATZ accept games from the last 90 days without requiring the latest patch. Their actual patch labels are retained; neither provider substitutes another role.
- Each row is one specific game: player, result, date, match ID, evidence, starting purchases and item timings. Click a row to follow that exact game's purchases and skills. Distinct games remain available even when their purchase/skill sequences match. Timings are never averaged.
- Starting purchases come from negative-time purchase-log entries, with repeated purchases preserved. Saved corrections and the explicitly labelled STRATZ branch estimate affect displayed quantities; original purchase logs remain intact. Purchases at exactly 0:00 stay in early purchases rather than being silently reclassified as starting items.
- Skills are the selected match's upgrade sequence. The available `ability_upgrades_arr` does **not establish exact hero levels**, and this version does not infer them. Facets are source variant numbers, not translated facet names. Situational counter explanations are not yet generated.
- **All usable games found are retained.** Discovery, combined results, provider snapshots and saved searches have no ten-game limit. Searches continue through available candidates within the shared eight-second budget; requests use small batches. Ranking determines order, not which games survive. Refreshes replace a matching game with its latest details while retaining other matching games; imports add a choice without evicting one. The count above the match table shows the total. Automatic selection follows the top-ranked arrival until you choose a game yourself. This is not an exhaustive search of all Dota games or a global numeric MMR ranking.
- Complete pub snapshots load immediately for five minutes (legacy source: 30 minutes). Partial snapshots are shown immediately, then rechecked so later-cached games can appear. Search status reports failed API calls, unfinished work and exclusion reasons. Starting purchases and skills are published together as each usable game arrives. Your explicit choice is preserved as more data arrives.
- Purchase evidence says **Observed purchase** for a selected real game's recorded event, or **Synthetic demo** for demo data. This does not indicate lookup success or verify match MMR.
- Foreground build searches have an **eight-second budget**, up to three concurrent I/O jobs and one three-second socket attempt per request. Slow I/O may finish caching after the UI stops waiting, but cannot overwrite results. Failed refreshes retain the current route. Draft searches have the same foreground budget.
- Caching accelerates repeat lookups; it cannot guarantee a useful cold result from an unavailable discovery endpoint. Errors are shown promptly rather than waiting for minutes or inventing a build. Credentials are optional via `OPENDOTA_API_KEY`; the key is neither committed nor included in cache names/errors.

D2PT is not scraped. STRATZ is implemented and requires a user-supplied key. Bundled item/hero/ability metadata was fetched on **2026-09-07**; its latest known patch is **7.41**. That is a metadata snapshot, not a perpetual current-patch guarantee. Refresh the constants before using future patches.

### Saved searches

Saved results use the same 90-day, pro and rating ordering as fresh results. Premier discovery filters OpenDota's premium leagues before limiting to 30 hero matches, so newer minor events cannot crowd TI out. STRATZ verifies position and supplies build details; ranked discovery uses the remaining time within the shared eight-second budget. The limited STRATZ league directory remains a fallback during index errors. Numeric MMR is shown only when the source supplies it; unknown values remain explicit, and actual team strength is not compared.

The search-history dropdown keeps up to 50 searches by hero, position, source and bundled patch metadata. Selecting a saved search immediately restores the builds and your selected game without waiting for a new build lookup, including after restarting the app. A selected STRATZ game's quantity comparison may run separately in the background. Existing tournament caches are imported automatically.

Automatic lookups reuse a saved search for 30 minutes, then show it immediately while checking for newer results. **Find builds** requests fresh discovery while reusing completed STRATZ match details for up to 30 days. Incomplete details are retried sooner. Offline errors and rate limits retain saved builds; refresh never bypasses the API cooldown. Updating bundled patch metadata does not invalidate recent saved games or mark them outdated. An updated discovery policy can trigger a refresh while retaining existing choices.

### Follow a game you choose

Select your hero and position, then **Browse D2PT** to inspect games yourself. Paste a numeric match ID, D2PT match link, or OpenDota match link and click **Follow this game**. Only the ID is read from the link; the selected provider (STRATZ by default, or OpenDota) independently loads it. D2PT's numeric MMR is not imported. Missing games, purchase history, wrong hero/position or dates outside the supported 90-day window produce an error without replacing the selected game. The source patch number remains visible as reference information. No live match is required.
