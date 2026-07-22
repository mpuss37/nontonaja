# Scraping Flow

Technical breakdown of how each source extracts stream URLs.

## LK21 (Source 1 — 480p)

### Search
```
1. GET https://tv12.lk21official.cc/search → get body[data-search_url] (API base)
2. GET {api_base}/search.php?s={query}&page=1 → JSON {data: [{slug, title, year, type}]}
3. Fallback: browse /populer + /latest, filter client-side
```

### Stream Extraction
```
1. GET https://tv12.lk21official.cc/{slug} → parse HTML
2. Regex: data-url="([^"]+)" → find playeriframe.sbs URLs
3. Extract VID from: playeriframe.sbs/iframe/p2p/{vid}
4. POST https://cloud.hownetwork.xyz/api2.php?id={vid}
   Body: r={referer}, d=tv12.lk21official.cc
   Response: {"file": "https://cloud.hownetwork.xyz/.../480.m3u8"}
5. Return: m3u8 URL + Referer header
```

## FlixHQ (Source 2/3 — 720p/1080p)

### Search
```
1. GET https://flixhq.ws/search/{query} → parse HTML
2. Extract: slug, title, year from poster grid
```

### Stream Extraction
```
1. GET https://flixhq.ws/{slug} → parse embed URLs
2. Regex: pl_url from embed page
3. Fetch embed → extract m3u8 URL
4. Return: m3u8 URL + subtitles (if available)
```

## IDLIX (Sub Indo Provider)

### Search
```
GET https://z2.idlixku.com/api/search?q={query}
Response: {results: [{id, title, releaseDate, contentType}]}
```

### Stream Extraction (Pentos Flow)
```
1. GET /api/watch/play-info/{type}/{id} → gateToken
2. POST /api/watch/session/claim → {kind: "wait", unlockAt, serverNow}
   - Wait (unlockAt - serverNow) seconds
   - Try skip: immediate second claim (usually fails)
3. POST /api/watch/session/claim (again) → {kind: "pentos", redeemUrl, claim, renewalToken}
4. POST {redeemUrl} → {url: "https://...config.json?...", subtitles: [{path: "*.vtt"}]}
5. Cache renewalToken untuk refresh tanpa wait (valid ~10 menit)
```

### Subtitle Format
- URL: `https://e2e.majorplay.net/.../subs-idlix/.../*.vtt`
- Format: WebVTT
- Language: Indonesian (id)

## Local Proxy (IDLIX HLS Rewrite)

### Problem
IDLIX CDN serves CMAF segments with obfuscated extensions (.jpg, .css, .js). ffmpeg rejects these extensions causing playback delays.

### Solution
```
1. Fetch master playlist from IDLIX
2. Parse #EXT-X-STREAM-INF → find highest bandwidth sub-playlist
3. Fetch sub-playlist → parse segment URLs
4. Rewrite m3u8: all segment URLs → localhost:PORT/seg/N.ts
5. Start ThreadingHTTPServer on localhost
6. Serve rewritten m3u8 + proxy segment requests with correct Content-Type
7. mpv reads localhost URL → ffmpeg sees .ts extension → no probing delay
```

### Flow Diagram
```
mpv → localhost:PORT/playlist.m3u8
         ↓
    proxy rewrites URLs to .ts
         ↓
    proxy fetches from CDN (original URL)
         ↓
    serves as video/mp2t → ffmpeg accepts
```

## Subtitle Merging

### Option 2/3 (FlixHQ + IDLIX)
```
1. Fetch FlixHQ stream → video URL + FlixHQ subtitles
2. Search IDLIX by title → match by normalized title
3. Fetch IDLIX stream → extract subtitle URLs only
4. Combine: FlixHQ subs + IDLIX subs (sub Indo)
5. All subs downloaded to temp dir, passed to mpv via --sub-file
```

### Cross-Source Deduplication
```
- Normalize titles: strip year suffix, lowercase
- Word-overlap scoring (50% threshold)
- Prefer matching media_type (movie vs tv_series)
- LK21 results take priority over FlixHQ
```
