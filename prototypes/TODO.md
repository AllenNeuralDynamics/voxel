# To do

Work to remember, in no particular order.

## Alerts in the core

`Issue`, `Problem` and `Alert` are defined in `vxlib.issues`. Not built yet:

1. **A watchdog prototype for "a camera stopped sending".** The relay notes when each camera that has a stream last
   sent a frame; a small task keeps a set of stalled cameras (a `Cell`) that changes when a camera goes quiet for too
   long and when it sends again. That set is 1 more trigger for the alerts. Build it here first, to see how much code
   it adds, before anything goes into `src`.
2. **The first alerts.** A `Computed` of `Alert`s over cached state in the base `Instrument`, each check a small pure
   function, with `since` kept from the last result for the same code and `loc`. An instrument kind adds its own
   checks through a hook, as it adds view fields. Start with `camera.no_frames` (from the watchdog) and
   `device.inconsistent_with_profile` (named 2026-11-20): each device's live value against the active profile, for
   selectors, wheels, laser power, focus axes and camera settings. They go out as `instrument.alerts`. The app adds
   Restore to these rows and lists them under Issues › Now (the Lab's "live changes" list).

The app keeps its own request failures as a separate feature. See `feed.md` for how alerts reach a screen.
