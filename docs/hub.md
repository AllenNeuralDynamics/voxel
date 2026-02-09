# Voxel Hub

A facility portal for discovering and accessing Voxel microscopes on the network.

## Purpose

In a multi-microscope facility, users need to know what's available, what's online, and how to access it. Voxel Hub provides a single entry point for browsing microscopes, checking their status, and connecting to their control interfaces.

Hub is a convenience layer on top of the existing architecture. Each microscope remains fully self-contained — Hub going down does not affect individual microscope operation.

## Architecture

```
                    Internal DNS
                  hub.facility.org
                        |
                   +---------+
                   |  Caddy  |  TLS, routing, health checks
                   +---------+
                   /    |     \
                  /     |      \
     /exaspim2-1/*   /exaspim2-2/*    /
          |              |            |
    rig host :8000  rig host :8000   SvelteKit app
    (Voxel API+UI)  (Voxel API+UI)   (Hub portal)
```

**Caddy** handles TLS termination, DNS, proxying to rig hosts, and health checking. It routes rig paths directly to each host and serves the Hub portal at the root.

**SvelteKit (Bun)** renders the portal UI. It does not proxy rig traffic — Caddy handles that. The SvelteKit app fetches rig status to display in the dashboard.

**Rig hosts** continue to serve their own Voxel web UI and API independently. Hub proxies to them through Caddy but does not replace them.

## Features

### Microscope Discovery

- Dashboard showing all known microscopes with online/offline/in-use status
- Health polling via each rig's `/health` endpoint
- Click-through access to any online microscope's control UI (proxied through Caddy)

### Rig Templates

- Central registry of rig configuration templates
- Browse, version, and share configurations across microscopes
- New microscopes can bootstrap from known-good templates

### Session Visibility

- Which microscopes are in active sessions
- Who is using them and for how long
- Useful for scheduling and troubleshooting

## Stack

| Component | Role |
|-----------|------|
| Caddy | Reverse proxy, TLS, health checks, rig routing |
| SvelteKit | Portal UI (dashboard, template browser) |
| Bun | SvelteKit runtime |
| Docker | Containerized deployment |

## Discovery Model

Static configuration file listing known rigs:

```yaml
rigs:
  - name: exaspim2-1
    host: 10.128.133.64
    port: 8000
  - name: exaspim2-2
    host: 10.128.133.46
    port: 8000
```

Caddy polls each rig's `/health` endpoint to determine online status. The SvelteKit app reads this status to render the dashboard.

## Design Principles

- **Hub is optional.** Every microscope works independently without it.
- **Hub does not control microscopes.** It discovers and routes to them. Each Voxel instance is the control surface.
- **Caddy proxies, SvelteKit renders.** Don't reimplement reverse proxy logic in application code.
- **Start simple.** Static rig list, health polling, dashboard. Add complexity only when needed.

## Future Enhancements

- **Dynamic rig discovery.** Implement self-registration (rigs announce themselves to Hub at startup) for dynamic rig discovery.
- **Advanced routing.** Support more sophisticated routing strategies.
- **User authentication.** Add user authentication and authorization for secure access.
- **Logging and monitoring.** Integrate logging and monitoring tools for better observability.
