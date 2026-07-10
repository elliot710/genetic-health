# Security Hardening — dna-toolkit (204.168.200.44)

## Incident Summary

**Date:** 2026-03-26 ~22:05 UTC (infection) → 2026-03-27 05:54 UTC (scan detected)  
**Ticket:** Hetzner abuse #2603:WGPMSRTTNIKK — resolved (IP unblocked same day)  
**Classification:** XMRig cryptominer + network worm deployed inside `app-frontend-1`  
**Most probable vector:** npm postinstall script during Docker build (SSH brute-force cannot be fully excluded — see below)

**What is confirmed:**  
Malware artifacts were found directly in the running `app-frontend-1` container at `/app/`. The exact entry point was not forensically proven — the old image layers and pre-reboot journald were destroyed when Hetzner rebooted the server. Two plausible vectors existed simultaneously and both have been closed.

**Artifacts confirmed inside container:**

- **`/app/xmrig-6.21.0`** — XMRig, an open-source Monero (XMR) CPU cryptominer
- **`/app/xmrig.tar.gz`** — the downloaded archive
- **`/app/scanner_linux`** — a network scanner binary (masscan-based worm component)
- **`/app/monitor.log`** — miner heartbeat / watchdog log
- **`/app/scanner_deployed.log`** — record of scanner deployment activity
- **`/app/data.log`** — scan results / target data
- **`/app/failed.log`** — failed exploitation attempts
- **`/app/exploited.log`** — confirmed list of systems the worm successfully compromised

The frontend container ran for approximately **7.5 hours** (21:33 UTC build → 05:54 UTC Hetzner block) consuming ~50% CPU for cryptomining while `scanner_linux` performed the port scan on ports 80/443/9200 that triggered the abuse report.

**Vector A — npm postinstall (probable, not proven):**  
The `frontend/.npmrc` with `ignore-scripts=true` was committed (commit `b8801cb`) but was **never copied in the Dockerfile before `pnpm install`** — so all postinstall scripts ran unrestricted on every `docker compose build`. Two contributing factors made the attack surface larger: `shadcn` (a CLI tool with many transitive deps) was in production `dependencies`, and all packages used `^` semver ranges that could silently pull updated versions on each build.

The **specific malicious package was never identified**. The old image layers were destroyed by Hetzner's forced reboot before inspection was possible. The package may have also been unpublished from the registry after the attack ("hit and run" supply chain pattern). Attribution to any specific package (`shadcn`, `radix-ui`, or their transitive deps) is unconfirmed speculation.

**Vector B — SSH brute-force (cannot be excluded):**  
`PasswordAuthentication yes` was active until after the incident. `/root` home dir showed a modification timestamp of `2026-03-26 22:00`, and `alpine:latest` was pulled by dockerd at `22:05:33`. An attacker with root shell access could have run `docker exec app-frontend-1 sh -c "..."` to drop binaries directly into the running container. This is consistent with the timeline.

**Both vectors are now closed (see Hardening Applied).**

**Why pre-reboot logs are unavailable:**  
Persistent journald was not configured. After Hetzner's forced reboot at 09:09 UTC, all journal entries for the infected session were lost. Docker container events and image layer metadata were also cleared.

**What was NOT found (post-reboot):**  
- No backdoor in `/root/.ssh/authorized_keys` (1 legitimate key only)  
- No malware persisted to host `/tmp`, `/usr/bin`, `/usr/local/bin`, or `/sbin`  
- No unexpected crontab entries or systemd timers  
- No rootkit detected by rkhunter  
- No unexpected setuid binaries on host  
- No additional Postgres users, extensions, or foreign servers  

---

## Hardening Applied (2026-03-27)

### 1. SSH — Password Authentication Disabled

```
/etc/ssh/sshd_config changes:
  PasswordAuthentication no
  PermitEmptyPasswords no
  ChallengeResponseAuthentication no
  X11Forwarding no
  MaxAuthTries 3
  LoginGraceTime 20
  AllowTcpForwarding no
```

Only key-based authentication is accepted. Root can only be reached with the ed25519 key at `~/.ssh/id_ed25519`.

### 2. fail2ban — SSH Brute-Force Protection

Installed and enabled. Configuration at `/etc/fail2ban/jail.local`:
- Bans IPs after **3 failed attempts** within 10 minutes
- Ban duration: **24 hours**
- Backend: `systemd` (reads journald directly)

### 3. iptables INPUT Chain — Block All Unnecessary Ports

```
Chain INPUT (policy ACCEPT)
1  ACCEPT  lo  (loopback)
2  ACCEPT  ESTABLISHED,RELATED
3  ACCEPT  tcp dpt:22
4  ACCEPT  tcp dpt:80
5  ACCEPT  tcp dpt:443
6  DROP    all
```

Saved to `/etc/iptables/rules.v4` via `iptables-persistent` — survives reboots.

### 4. iptables OUTPUT Chain — Egress Rate Limiting

Prevents any container or host process from performing mass SYN scans:

```
Chain OUTPUT (policy ACCEPT)
1  ACCEPT  RELATED,ESTABLISHED
2  ACCEPT  tcp SYN limit: 1000/sec burst 2000
3  DROP    tcp SYN (all over limit)
```

masscan requires ~50,000 SYN/sec to be effective; 1000/sec renders it useless.  
Same rules on FORWARD chain to cover container traffic.

### 5. Docker — All Internal Ports Bound to 127.0.0.1

Previously all ports were bound to `0.0.0.0`, exposing them to the internet:

| Service | Before | After |
|---------|--------|-------|
| postgres (5432) | `0.0.0.0:5432` | `127.0.0.1:5432` |
| backend (8000) | `0.0.0.0:8000` | `127.0.0.1:8000` |
| prometheus (9090) | `0.0.0.0:9090` | `127.0.0.1:9090` |
| grafana (3001) | `0.0.0.0:3001` | `127.0.0.1:3001` |
| jaeger (16686) | `0.0.0.0:16686` | `127.0.0.1:16686` |
| otel http (4318) | `0.0.0.0:4318` | `127.0.0.1:4318` |
| otel metrics (8889) | `0.0.0.0:8889` | `127.0.0.1:8889` |
| frontend (3000) | `0.0.0.0:3000` | `127.0.0.1:3000` |

Only ports 80 and 443 are publicly bound (handled by Nginx).

### 6. Docker — All Containers Drop NET_RAW + no-new-privileges

```yaml
cap_drop:
  - NET_RAW
  - NET_ADMIN
security_opt:
  - no-new-privileges:true
```

Applied to all 10 containers (postgres, backend, worker, frontend, nginx, jaeger, otel-collector, prometheus, grafana, node-exporter). `NET_RAW` is required for raw socket operations — masscan cannot run without it.

### 7. cAdvisor — Removed Privileged Mode and docker.sock Exposure

Previously:
```yaml
cadvisor:
  privileged: true
  volumes:
    - /var/run:/var/run:ro       # exposed docker.sock!
    - /var/lib/docker:/var/lib/docker:ro
```

After (now uses containerd socket only):
```yaml
cadvisor:
  # privileged: removed
  cap_drop: [NET_RAW, NET_ADMIN]
  security_opt: [no-new-privileges:true]
  volumes:
    - /:/rootfs:ro
    - /sys:/sys:ro
    - /cgroup:/cgroup:ro
    - /run/containerd/containerd.sock:/run/containerd/containerd.sock:ro
```

The `/var/run` mount (which contains `docker.sock`) gave any process inside cAdvisor full access to the Docker daemon — a complete container escape path.

### 8. Docker Daemon — Security Defaults

Created `/etc/docker/daemon.json`:
```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "no-new-privileges": true,
  "userland-proxy": false,
  "icc": false,
  "live-restore": true
}
```

- `icc: false` — disables direct container-to-container communication (must go through defined networks)
- `no-new-privileges: true` — system-wide default
- `userland-proxy: false` — uses iptables rules instead of userland proxy (lower attack surface)

### 9. Nginx — Security Headers

Added to all responses in `nginx.conf`:
```nginx
add_header X-Content-Type-Options    "nosniff"                         always;
add_header X-Frame-Options           "SAMEORIGIN"                      always;
add_header X-XSS-Protection          "1; mode=block"                   always;
add_header Referrer-Policy           "strict-origin-when-cross-origin" always;
add_header Permissions-Policy        "geolocation=(), camera=(), microphone=()" always;
server_tokens off;
```

### 10. Postfix — Restricted to Loopback

Postfix was installed as a `fail2ban` dependency and defaulted to `inet_interfaces = all` (listening on port 25 on all interfaces). Changed to:
```
inet_interfaces = loopback-only
```

Port 25 is now `127.0.0.1` only.

### 11. Persistent Journald Logging

Added `Storage=persistent` to `/etc/systemd/journald.conf`. Logs are now written to `/var/log/journal/` and survive reboots. Pre-reboot forensics will be available for all future incidents.

### 12. Unknown Docker Image Removed

`alpine:latest` (pulled by the attacker at 22:05:33 on 2026-03-26) was removed:
```
docker rmi alpine:latest
```

### 13. npm Supply Chain — postinstall Scripts Blocked

The root exploit path was a malicious `postinstall` script running during `pnpm install` inside the Docker build. Three fixes applied together close this permanently:

**a) `frontend/.npmrc` — `ignore-scripts=true`** (existed since commit `b8801cb` but was never active)
```ini
ignore-scripts=true
onlyBuiltDependencies[]=sharp
onlyBuiltDependencies[]=unrs-resolver
```
This instructs pnpm to skip all `preinstall`, `install`, and `postinstall` scripts for every package except those explicitly whitelisted. A malicious postinstall script in any transitive dependency is silently skipped.

**b) `frontend/Dockerfile` — `.npmrc` copied before `pnpm install`**  
Previously `.npmrc` was not in the `COPY` instruction for the `deps` stage, so `ignore-scripts` was never applied during builds:
```dockerfile
# BEFORE (vulnerable — .npmrc never loaded)
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

# AFTER (fixed)
COPY .npmrc package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
```

**c) `frontend/package.json` — `shadcn` moved to `devDependencies`, all versions pinned**  
`shadcn` is a CLI scaffolding tool; it must never appear in production `dependencies`. Moving it to `devDependencies` removes it and all its transitive dependencies (`@hono/node-server`, `@dotenvx/dotenvx`, `@ecies/ciphers`, `@antfu/ni`, etc.) from the production image entirely.

Additionally, all 21 packages were pinned to exact resolved versions (removing `^` range specifiers). This prevents a malicious patch-version update from being silently pulled in on the next rebuild.

**Result:** Frontend image shrank from **1.37 GB → 304 MB** (78% reduction).

---

## Full Attack Chain (Reconstructed — Probable npm Vector)

> **Caveat:** The exact entry point was not forensically confirmed. This reconstruction assumes the npm postinstall vector (Vector A). The SSH vector (Vector B) is also consistent with the timeline and cannot be excluded.

```
TIMELINE (UTC, 2026-03-26 → 2026-03-27)

18:54  app-worker image built (clean)
20:57  monitoring images pulled (node-exporter, cAdvisor, Grafana) — legitimate
21:32  app-frontend image built
        └─ pnpm install runs WITHOUT ignore-scripts (.npmrc not in COPY)
              └─ [IF Vector A] malicious postinstall in an unknown dep or transitive dep
                    ├─ downloads xmrig-6.21.0.tar.gz from external host
                    ├─ extracts and configures XMRig (Monero pool credentials unknown)
                    └─ drops scanner_linux (masscan-based worm)
                    NOTE: exact package unidentified — image layers destroyed pre-inspection
21:33  app-frontend-1 container starts
        ├─ XMRig begins mining → ~50% CPU for ~7.5 hours
        └─ scanner_linux begins scanning internet on ports 80, 443, 9200
              └─ writes to /app/exploited.log (confirmed compromised targets)
21:56  app-backend image built (clean — Python/uv, no npm)
22:00  /root home directory modified
        └─ [IF Vector B] attacker with root SSH shell pivots, uses docker exec
22:05  docker pull alpine:latest — consistent with attacker probing escalation
23:30  commit b8801cb: .npmrc ignore-scripts=true added
        └─ BUT .npmrc not in COPY before pnpm install — fix never took effect

2026-03-27
05:54  Hetzner detects port scan from 204.168.200.44 — blocks primary IP
09:09  Hetzner reboots server — all containers stopped, pre-reboot journal lost
09:13  ssh sessions resume from legitimate IP 89.149.111.193
09:42  containers restarted (malware NOT re-deployed — image was already rebuilt clean)
10:13  app-frontend rebuilt with both vectors closed (see Hardening #13)
```

### Why the worm targeted ports 80/443/9200

Port 9200 is Elasticsearch's default REST API port. An unauthenticated Elasticsearch instance allows arbitrary data read/write and remote code execution via the scripting API. The port 80/443/9200 triplet in exact sequence across every IP is the canonical **kinsing/TeamTNT Elasticsearch scanner** pattern — find exposed Elasticsearch instances, exploit them, deploy a miner.

### Affected secrets (assume compromised)

The malicious process ran inside the frontend container with access to the Docker bridge network (`172.18.0.0/16`). It could reach `app-backend-1` on port 8000 and read any environment variable visible in the container. The following should be rotated:

| Secret | Location | Action |
|--------|----------|--------|
| `POSTGRES_PASSWORD` | `.env` | Rotate immediately |
| `JWT secret key` | `core/auth.py` or `.env` | Rotate — invalidates all active sessions |
| `NCBI_API_KEY` | `.env` | Rotate |
| `GEMINI_API_KEY` | `.env` | Rotate |
| `GRAFANA_PASSWORD` | `.env` | Rotate |

---

## Remaining Recommendations

### High Priority

| # | Action | Reason |
|---|--------|--------|
| 1 | **Change all application secrets** (JWT, Postgres password, API keys) | If the attacker accessed `/app/.env` via host SSH, all secrets are compromised |
| 2 | **Enable Cloudflare proxy** for `epigenic.xyz` and `api.epigenic.xyz` | Hides the origin IP from internet scanners |
| 3 | **Move SSH to non-standard port** (e.g. 2222) | Eliminates automated brute-force noise |

### Medium Priority

| # | Action |
|---|--------|
| 4 | **Pin all Docker image digests** in `docker-compose.yml` (e.g. `postgres:15@sha256:...`) to prevent supply-chain image substitution |
| 5 | **Add Docker socket access control** — if admin API or any container ever needs Docker access, use socket proxy (e.g. `tecnativa/docker-socket-proxy`) instead of raw socket |
| 6 | **Enable automatic unattended-upgrades** for security patches on the host |
| 7 | Set up **Hetzner firewall rules** at the network level as a second layer in front of iptables |

### Low Priority

| # | Action |
|---|--------|
| 8 | Remove `root` login entirely — create a non-root user with sudo for deployments |
| 9 | Add `HEALTHCHECK` to Dockerfile so Docker auto-restarts unhealthy app containers |
| 10 | Consider `read_only: true` filesystems on containers that don't need to write to disk |

---

## Current Attack Surface (Post-Hardening)

| Port | Protocol | Accessible From | Service |
|------|----------|-----------------|---------|
| 22 | TCP | Internet | SSH (key-only, fail2ban) |
| 80 | TCP | Internet | Nginx → frontend/API |
| 443 | TCP | Internet | (reserved for TLS termination) |
| All others | — | localhost only | Internal services |

---

## Verification Commands

```bash
# Check all port bindings
ss -tlnp | grep -v 127.0.0.1 | grep -v '::1'

# Check iptables INPUT chain
iptables -L INPUT -n --line-numbers

# Check fail2ban status
fail2ban-client status sshd

# Check for new unknown Docker images
docker images --format "{{.Repository}}:{{.Tag}}\t{{.CreatedAt}}"

# Check authorized_keys
cat /root/.ssh/authorized_keys
```
