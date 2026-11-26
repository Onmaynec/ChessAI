# Vision Bot 0.9.11.1 — Working UI resize hotfix

User review rejected 0.9.11's real CustomTkinter workspace. Qt preview work did not migrate the operational host. This patch addresses the working UI, not the preview.

- Native scroll viewport applies the latest requested width at most once per 80 ms while resizing.
- Board and form layout are deferred while the root resize debounce is pending; final resize explicitly schedules them even if layout mode did not change.
- Coarse board sizing and hysteresis reduce breakpoint oscillation.
- Wide session view places setup left, board and analysis right. Main action buttons no longer all expand to fill the row.
- No changes to session commands, training or saved data.

Three pure layout property checks passed on a local copy whose Git blob matches presentation_rules.py. Full CustomTkinter GUI, Windows native resizing, dropdown appearance and actual performance remain untested. This is not a full redesign or visual acceptance. User rejection remains open. Qt preview is not a substitute for functional migration. Main not merged.
