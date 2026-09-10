# YouTube Mirror Resolver — temporal coverage patch

Apply this patch **on top of the previous `youtube-resolver-terminal-resume-patch`** by extracting it over the repository root, then restart the dashboard.

## Why this patch exists

The previous global resolver correctly migrated acoustic checkpoints to `numpy-exact` and reached 12 verified assignments, but the discovery pool still used metadata similarity as a hard admission gate. The channel index contains recent long-form videos with opaque/temporary titles such as `guns5` and `battle`; those can be real mirrors but were never assigned to any Twitch VOD. Therefore `19 assignments / 12 verified / 0 pending` did not mean full channel-window coverage.

## Changes

- Adds a **temporal completeness frontier** to global discovery.
- Lazily enriches recent flat-index entries with cached yt-dlp metadata until three consecutive uploads are safely older than the production window.
- Includes every upload overlapping the Twitch production window even when title/chapter similarity is weak or zero.
- If a recent metadata probe fails, keeps that row eligible rather than silently dropping it.
- Preserves yt-dlp `playlist_index` / `playlist_autonumber` and uses playlist order when flat entries have no dates.
- Tightens pair checkpoint reuse: only chronology-based `not_run` results are permanently reusable; transient `not_run` results reopen.
- Stores discovery reasons, index position and publish time in new assignments for auditability.
- Dashboard no longer labels terminal no-match assignments as merely “0 pending”; it shows verified / no-match / in-progress separately and explains temporal coverage.
- Does **not** invalidate existing verified assignments or fingerprints. A new Resolve production should skip terminal old assignments and work mainly on newly admitted temporal candidates.

## Expected behavior on the supplied production

The current index contains `S_mY0ESbwMY` (`guns5`, ~1h52) between Metal Gear Part 4 and Part 6 in channel recency, but it had no global assignment. After this patch it is admitted by the production-time window and receives the same all-VOD acoustic comparison as normal-titled uploads. Other recent opaque/low-signal videos (`battle`, `guns2`, `aliens2`, etc.) are also allowed into the temporal pool and can be rejected by audio instead of disappearing before verification.

## Validation

- `python -m pytest -q tests/test_youtube_resolver.py` → 78 passed
- `python -m pytest -q` → 101 passed

No dependency changes are introduced by this patch.
