# Feed proxy

Discussed on 2026-11-19, not built. Part of the web layer, after the acquisition and records. See `feed.md` for the
feed itself.

## Why

The station feed is push-only, but each client still costs the station: 1 send per client, a queue and merge for
each slow client, and 1 task per WebSocket on the event loop that runs the acquisition. The UI is for many people
on many computers, and the lab watches too.

## The idea

```text
station ──1 feed──▶ feed proxy ──▶ station UIs, on any computer
                         └──────▶ lab screens
```

- The station has 1 subscriber, the proxy, whatever the number of screens.
- The proxy is its own process, with its own GIL and CPU. It can run on another computer.
- It keeps the rule from `records.md`: no outside request runs in the station process.
- Read-only. Operations go from each UI straight to the station, never through the proxy. `ETag` / `If-Match` and
  the activity lock keep many editors safe.
- The UI gets every topic. The lab gets a fixed list of topics: the public contract.
- The lab is live through the proxy. The share service then serves only stored data: `acquisition.json`, the full
  log and history.

## How it works

1. **Upstream:** 1 WebSocket client to the station feed. It reconnects when the link drops.
2. **Topic cache:** the last value of each topic. A new screen gets `full: true` from the cache; the station never
   sees it.
3. **Fan-out:** 1 message, many readers. A frame is shared, never copied per screen.
4. **1 task per screen:** it filters topics, sends `full: true` from the cache when the screen falls behind, and
   ignores what the screen sends, except closing.

The proxy opens only the message envelope (topics, cursor, `full`). Frames (VXLF bytes) pass through unopened.

## Plan

1. Build the feed in Python, as `feed.md` says, with a small Python proxy. This tests the message format and
   "1 feed, many screens".
2. When the format is fixed, write the proxy in Rust: `tokio`, `tokio-tungstenite` upstream, `axum` WebSockets for
   screens, `tokio::sync::broadcast` with `bytes::Bytes` for the fan-out. Ship it with `maturin`
   (`bindings = "bin"`), so `uv sync` installs it and `vxl station start` can start it.

## Open

- The encoding of a state message (JSON or binary), so the proxy can read the envelope.
- How a frame message is framed: the envelope and the VXLF bytes in 1 binary WebSocket message.
- The lab's topic list.
- Whether the station limits how many operations it takes at once.
