# User guide

For installation and STRATZ/Steam setup, see the [README](../README.md).

## Overlay

The preferred default width is 270 pixels, placed at the top-right with a 160-pixel gap below the top edge for game stats. Height fits the content automatically. On shorter screens the overlay widens and uses columns when needed. Crowded pregame views can use three columns: full build, starting/early purchases, and skills/talents/Invoker spells. There are no nested scroll areas to operate during play. **Position below top-right game stats** restores the top-right placement; the exact gap may need adjustment for your HUD scale.

Open **Overlay & connection** and enable **Preview / reposition** to drag the overlay or change its width. Set **Preferred width** from 270–600 pixels, **Overlay text size** from 11–16 pixels, opacity and a Ctrl+function-key shortcut (default **Ctrl+F8**). Check the preview's fit status; if it reports more room is needed, move the overlay up or reduce the text size before playing. While Dota is foreground, the overlay becomes click-through and does not request focus. Outside Dota it hides unless preview is enabled.

The full major-item build stays visible, alongside the next skill and recorded talent picks. The highlighted starting-buy card includes item quantities and disappears at 1:00. Early components have their own section until 5:00; consumables stay in a separate **Laning supplies** section until 10:00 by default. Change **Laning supplies until** to 5–15 minutes. Wards after the starting buy and recipes remain hidden. Optional item advice and compact lane pull/stack timers sit below the build; timer windows remain approximate and camp availability is unknown.

Borderless fullscreen is the target mode. Exclusive fullscreen capture/overlay visibility is **not verified**. Test your configuration before relying on it. The app does not inject into Dota or change display settings.

### Invoker spell reference

Selecting Invoker manually or receiving his confirmed hero from game state shows all ten spell recipes automatically, even before a build lookup finishes. The reference uses the **default keys**: Q = Quas, W = Wex, E = Exort; enter the three orbs, press R to Invoke, then use the spell's displayed D/F slot and target as required. Custom/legacy bindings are not detected. The table lists orb recipes, not current spell availability or cooldowns.

The compact spell reference uses five rows with two spells per row, with each recipe above its full spell name. When the overlay uses a wider, split layout, the reference uses one column beside the build. All ten recipes remain available without scrolling. The table is hidden while draft recommendations are displayed or another hero is selected.

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

## Draft helper

Open **Draft helper**, enter up to five confirmed enemy picks, and choose **Any hero**, **Carry**, or **Support**. Suggestions update after edits; turn off automatic updates to use **Suggest picks** manually. Use **Exclude hero** for allied picks and bans. Enemy picks and excluded heroes cannot be recommended. Duplicate/conflicting selections are rejected.

The table ranks up to ten heroes and shows each one's strongest and weakest observed matchup. Select a row for individual win counts, sample sizes and source links. **Use selected hero in Builds** opens that hero's build search; it does not pick a hero in Dota. **Show suggestions in overlay** displays up to eight picks. Confirmed local-player game state switches the overlay back to build guidance. **Clear draft** resets enemy picks and exclusions; **New match** resets the draft too.

Draft picks fill when Dota supplies usable team/pick data; otherwise use manual enemy entry. Live player-mode availability is not guaranteed. OpenDota's matchup aggregation covers roughly a rolling year of tracked matches and does not expose patch, position or rank filters. It is **not specifically current-patch or high-MMR evidence**. The Carry/Support pools use broad metadata tags, not position-specific matchup results. Ally selections only exclude unavailable heroes; team synergy is not modeled.

Ranking requires at least 20 observed games against **every** chosen enemy. OpenDota returns the queried enemy's wins, so candidate wins are `games - enemy_wins`. Each pair is shrunk toward 50% with 100 neutral prior games, then the pairs are averaged equally. This is a historical matchup score, **not a full-draft win probability or a causal counter advantage**. A top-ranked hero can still have unfavorable matchups. Pair counts may overlap and are never summed as independent draft matches. If one enemy's data fails, no partial-draft ranking is shown. Results from an outdated selection are discarded.

Matchup responses are cached for six hours and read immediately, with visibly labeled stale fallback. Missing enemy responses are fetched concurrently within an eight-second foreground budget. Slow aggregation fails promptly and leaves the draft editable. No D2PT scraping or extra credentials are required.

## Connect Dota

1. In **Overlay & connection**, export the game-state configuration.
2. Copy that file into `<Dota install>/game/dota/cfg/gamestate_integration/` (create that folder if needed).
3. In Steam's Dota launch options add `-gamestateintegration`, then restart Dota.
4. Enter a bot match and check that the connection status changes from waiting to connected.

The receiver binds only to `127.0.0.1:38765` and checks a generated token. The token lives in the app's local settings; keep the exported configuration local. No config is installed into your game automatically. Do not run multiple copies on the same port.

Local-player GSI can confirm a hero in strategy/pregame/in-progress phases, provide the game clock and update inventory/skills. Hero-selection-phase messages are not treated as proof of lock-in. Spectator-shaped payloads are ignored. These integrations are tested with fixtures and a local HTTP round-trip; actual Dota delivery remains to be tested.

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


- **Recommended builds** is the default and combines tournament games, pro-player games, and high-ranked pubs. Patch evidence is considered first: verified current bundled patch, unknown/conflicting patch, then verified older patch. Within each group, premier events precede other tournaments, pro players, and pubs; newest games come first within each category. A recent date or famous player never proves the patch. This ranks known event/player categories, not measured team strength.
- STRATZ pub discovery targets **ten distinct, selectable purchase/skill sequences** for the chosen hero and position. It pages guide summaries in batches of 50 and backfills rejected or duplicate games. When guides run out, it checks up to 40 active high-ranked players' hero/position-filtered histories, with up to ten matching games per player. Only the target player's full build is downloaded. All work shares an eight-second deadline; results appear progressively.
- Discovery requires ranked Immortal games and verifies the actual hero and position again in match details. If recent guides are insufficient, the search expands to the bundled patch-date boundary; games older than seven days carry an **OLDER EXAMPLE** warning. Ten results cannot be guaranteed for every unusual hero/position combination. Missing purchases, missing skills, duplicate sequences and source errors are reported; other roles and synthetic builds are never used to fill the count.
- STRATZ match bracket and player leaderboard rank are labeled separately. Neither is numeric MMR. The user's reference IDs are explicitly supplied comparison games, not proof that guide discovery reproduces D2PT's list. During verification, two reference games loaded and the third returned null. STRATZ's current returned version list stopped at 7.40b while bundled metadata says 7.41; those recent games are prominently **patch unverified**, not certified current-patch. Exact hero-level skill assignments are still unavailable from the lightweight upgrade list.
- The STRATZ credential is saved with Windows DPAPI encryption, bound to the Windows user, in the app's data directory. Replace it in **Overlay & connection → STRATZ connection**. An optional `STRATZ_API_TOKEN` environment variable takes precedence. Credentials are excluded from settings, response-cache names, error messages and the executable. A copied EXE needs a separately saved credential on another Windows account.
- **OpenDota · recent pubs** remains optional. A single OpenDota Explorer query selects the latest ten sampled ranked pubs containing the hero, from the last seven days, with all ten recorded rank tiers Immortal (`avg_rank_tier = 80`, `num_rank_tier = 10`). It uses the public-match table's indexed hero arrays; it does not page through every high-level game. Match details still validate patch, position, purchases, ranked lobby and conflicting profile ranks.
- This is an independent OpenDota sample, **not D2PT coverage or the highest numeric MMR games**. Immortal brackets cannot distinguish 7k from 10k. An empty sample remains empty; old league games are not silently substituted.
- **Legacy league examples** retains the previous hero-match endpoint as a separate optional source. That endpoint joins league records and is unsuitable for reproducing D2PT's pub list. Its profile-rank evidence remains MMR unverified.
- `position_est` supplies the **estimated** position (1–5). The desktop uses position only, with no separate lane filter. Unknown positions never silently match a requested position.
- OpenDota requires the latest patch known to bundled metadata. STRATZ checks dates and reports source patch conflicts explicitly; it does not certify a conflicting version as current-patch. Neither provider substitutes another role.
- Each row is one specific game: player, result, date, match ID, evidence, starting purchases and item timings. Click a row to follow that exact game's purchases and skills. STRATZ backfills identical purchase/skill sequences so they do not inflate the ten-build count. Timings are never averaged.
- Starting purchases come from negative-time purchase-log entries, with repeated purchases preserved. Saved corrections and the explicitly labelled STRATZ branch estimate affect displayed quantities; original purchase logs remain intact. Purchases at exactly 0:00 stay in early purchases rather than being silently reclassified as starting items.
- Skills are the selected match's upgrade sequence. The available `ability_upgrades_arr` does **not establish exact hero levels**, and this version does not infer them. Facets are source variant numbers, not translated facet names. Situational counter explanations are not yet generated.
- STRATZ returns at most **10 distinct builds**, checking further candidates when necessary within its deadline. OpenDota considers at most ten candidate match details. Neither is a global top-ten numeric MMR ranking.
- Complete pub snapshots load immediately for five minutes (legacy source: 30 minutes). Partial snapshots are shown immediately, then rechecked so later-cached games can appear. Search status reports failed API calls, unfinished work and exclusion reasons. Starting purchases and skills are published together as each usable game arrives. Your explicit choice is preserved as more data arrives.
- Purchase evidence says **Observed purchase** for a selected real game's recorded event, or **Synthetic demo** for demo data. This does not indicate lookup success or verify match MMR.
- Foreground build searches have an **eight-second budget**, up to three concurrent I/O jobs and one three-second socket attempt per request. Slow I/O may finish caching after the UI stops waiting, but cannot overwrite results. Failed refreshes retain the current route. Draft searches have the same foreground budget.
- Caching accelerates repeat lookups; it cannot guarantee a useful cold result from an unavailable discovery endpoint. Errors are shown promptly rather than waiting for minutes or inventing a build. Credentials are optional via `OPENDOTA_API_KEY`; the key is neither committed nor included in cache names/errors.

D2PT is not scraped. STRATZ is implemented and requires a user-supplied key. Bundled item/hero/ability metadata was fetched on **2026-09-07**; its latest known patch is **7.41**. That is a metadata snapshot, not a perpetual current-patch guarantee. Refresh the constants before using future patches.

### Saved searches

Saved results use the same patch-first ordering as fresh results. Premier discovery filters OpenDota's premium leagues before limiting to 30 hero matches, so newer minor events cannot crowd TI out. STRATZ verifies position and supplies build details; ranked discovery fills remaining slots within the shared eight-second budget. The limited STRATZ league directory remains a fallback during index errors. Numeric MMR is shown only when the source supplies it; unknown values remain explicit. Conflicting patch metadata remains unverified, and actual team strength is not compared.

The search-history dropdown keeps up to 50 searches by hero, position, source and bundled patch metadata. Selecting a saved search immediately restores the builds and your selected game without waiting for a new build lookup, including after restarting the app. A selected STRATZ game's quantity comparison may run separately in the background. Existing tournament caches are imported automatically.

Automatic lookups reuse a saved search for 30 minutes, then show it immediately while checking for newer results. **Find builds** requests fresh discovery while reusing completed STRATZ match details for up to 30 days. Incomplete details are retried sooner. Offline errors and rate limits retain saved builds; refresh never bypasses the API cooldown. A changed bundled patch triggers a refresh and an older-metadata warning; individual source patch warnings still apply.

### Follow a game you choose

Select your hero and position, then **Browse D2PT** to inspect games yourself. Paste a numeric match ID, D2PT match link, or OpenDota match link and click **Follow this game**. Only the ID is read from the link; the selected provider (STRATZ by default, or OpenDota) independently loads it. D2PT's numeric MMR is not imported. Missing games, purchase history, wrong hero/position or dates outside the provider's supported patch-date window produce an error without replacing the selected game. STRATZ patch-metadata conflicts remain visible on the loaded game. No live match is required.
