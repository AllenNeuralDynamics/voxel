# Issues

An issue is something that is wrong now, or something that went wrong. The Issues tab in the bottom panel lists them.
The chips in the Live pane and the Devices pages show the issues about their device, channel or route.

## Conditions and events

- **A condition** is wrong now, for example "Filter wheel 1 does not match the profile". A check finds it. It ends when
  the cause is fixed, so it cannot be dismissed. The Issues tab shows it under "Now".
- **An event** went wrong at a time, for example a request that failed. It ends when it is dismissed, or when the same
  request works later. The Issues tab shows it under "Earlier".

A new error shows 1 toast. A warning shows none.

## Rules

- Each issue is defined 1 time: 1 code in `IssueCode`, and 1 check or 1 failure that makes it. Pages read it from
  `issues`. They do not test for it again.
- Only `reportFailure` shows a failure. It adds the event and shows the toast. An Oxlint rule in `web/station/vite.config.ts` blocks `toast.error`
  outside this folder.
- `reportFailure` lives in [`@voxel/kit/failures`](../../../../../kit/src/failures.ts), so the model, kit and utils can call it
  without importing this folder.
  `index.ts` registers `recordFailure` as its handler.
- A failure carries its own context. A failed request finds its subject in its API path, so a call site adds only what
  the error cannot know, such as a clearer title.
- A check only reads. It gives the conditions that are true now, and it never changes the state.
- The store keeps only what exists nowhere else: the failures. It gets the conditions from the live state.

## Add an issue

- **A condition:** add its code to `IssueCode`. Then write its check in `checks/`, in the file for its subject, and
  list the check in `checks/index.ts`. `checks/lasers.ts` is a short example.
- **An event:** wrap the work that can fail in `reportFailure`.

## Decisions

- The store is a module value, not a Svelte context. `reportFailure` runs in click handlers and async code, where a
  context is not available.
- The codes are 1 type, like the backend's `Violation.code`. So a typo fails the type check, and 1 place lists every
  kind of issue.
- Only the station shell connects the store. In the dashboard window, failures show only as toasts.
- The events live only in the window. A new instrument session or a reload clears them. The logs keep the history.
- The tests that turn a control off, such as `!connected || error || busy`, are not issues. They stay in the controls.

## Planned issues

These conditions are planned for "Now". "Needs" says what the backend must report before the check can be built.

| Issue                                                 | Level            | Actions                   | Needs                         |
| ----------------------------------------------------- | ---------------- | ------------------------- | ----------------------------- |
| A camera sends no frames                              | Error            | Open device, Show in logs | Nothing                       |
| A stage move failed, or the target is outside travel  | Error            | Show in logs              | Nothing                       |
| A node is disconnected, or its link is slow           | Error or warning | Open Devices              | The link state of each node   |
| A laser is not ready (warming up, interlock, fault)   | Warning or error | Open device               | The ready state of each laser |
| Not enough disk space, or the remote store is offline | Error            | Change destination        | The free disk space           |

Also planned: a warning when an exposure is longer than the waveform period allows, with an "Open profile" action.
