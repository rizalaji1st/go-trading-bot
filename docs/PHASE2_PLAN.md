# Phase 2 — Public Access & Rate Limiting

> **Status:** Done | **Timeline:** 1 day | **Goal:** Safe public Telegram bot

## Overview

The Telegram bot was previously accessible to anyone but had no protection
against abuse. A single user could exhaust the OpenCode Go API quota in
minutes by spamming `/analyze` or `/ai`.

Phase 2 added rate limiting, caching, admin controls, and usage monitoring
to make public access safe.

## Changes

### 1. Per-User Rate Limiting

```
RATE_MAX = 5           # max requests per user per hour
RATE_WINDOW = 3600     # sliding window in seconds
```

- In-memory sliding window per user ID
- Returns error message when limit exceeded
- Auto-cleans expired entries
- Applies to: `/analyze`, `/list`, `/ai`, `/status`, `/risk`

### 2. AI Response Caching

```
CACHE_TTL = 3600       # 1 hour
_cache: dict[str, tuple[timestamp, result]]
```

- `/analyze BBCA` → cached for 1 hour (same symbol = instant reply)
- `/ai <question>` → cached per exact question (1 hour)
- `/list` → top-5 batch result cached (1 hour)
- Cache hit shown with `↻ Dari cache` label

### 3. Command Logging

All commands logged to stdout/systemd journal:
```
[username@userid] /analyze BBCA
[keybs@1094401966] /ai Apakah BBCA...
```

### 4. Admin Panel (`/admin`)

Owner-only commands (verified against `TELEGRAM_CHAT_ID`):

| Command | Output |
|---|---|
| `/admin stats` | Total requests, active users, cache size, quota usage % |
| `/admin cache` | Clear all cached AI responses |
| `/admin users` | List active users with request counts |

Automatic warning when quota >80% in `/admin stats`.

### 5. Public-Facing Changes

| Before | After |
|---|---|
| No rate limit | 5 req/jam/user |
| No cache | 1 jam TTL |
| No log | Semua command tercatat |
| No admin | `/admin` untuk owner |
| No quota monitoring | Alert di `/admin stats` |

## Impact

| Scenario | Before | After |
|---|---|---|
| 1 user normal | 5 req/jam | 5 req/jam (nocache) |
| 1 user spams 100x | 100 req = ~$0.50 waste | Blocked at 5 req |
| 50 users in group | 250 req in 10 min = quota habis | 250 req capped by cache |
| Same stock 5 users | 5 API calls | 1 API call + 4 cache hits |
| Owner needs control | None | `/admin stats` `/admin cache` |

## Files Changed

| File | Change |
|---|---|
| `telegram_bot.py` | Full rewrite: rate limiter, cache, admin, logging |
