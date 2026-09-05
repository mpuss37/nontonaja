# Scraping Flow

Technical breakdown of how each source extracts stream URLs.

## LK21 (Source 1 — 480p)

### Search
```
1. GET https://tv12.lk21official.cc/search → get body[data-search_url] (API base)
2. GET {api_base}/search.php?s={query}&page=1
   Headers:
     Referer: {BASE_URL}/search?s={query}
     X-Requested-With: XMLHttpRequest
     Accept: application/json
   Response: JSON {data: [{slug, title, year, type}]}
   - type "series" → media_type="tv", else "movie"
3. Fallback: _search_browse()
   - Browse /populer + /latest
   - Parse article elements: a[href] → slug, h3.poster-title → title,
     span.year → year, img[itemprop='image'] → image (prefer data-src),
     span.rating → rating, div.genre → genre
   - span.episode presence → media_type="tv"
   - Filter: query_lower in title.lower()
```

### Stream Extraction
```
1. GET https://tv12.lk21official.cc/{slug}
   - Guard: reject if <title>Lk21 - Nonton Film</title> + no main-player
2. Regex 1: data-url="([^"]+)" → all player URLs
3. For each player URL, try VID extraction:
   - Regex 2: hownetwork\.xyz/video\.php\?id=([^&\s]+)  (old-style)
   - Regex 3: playeriframe\.sbs/iframe/p2p/([^/\s]+)    (new-style)
   - First match wins
4. POST https://cloud.hownetwork.xyz/api2.php?id={vid}
   Headers:
     Referer: {BASE_URL}/
     Origin: {BASE_URL}
   Body (form-encoded):
     r={BASE_URL}/
     d=tv12.lk21official.cc
   Response: {"file": "https://cloud.hownetwork.xyz/.../480.m3u8"}
5. Return: m3u8 URL + Referer: "https://cloud.hownetwork.xyz/"
```

## FlixHQ (Source 2/3 — 720p/1080p)

### Search
```
1. GET https://flixhq.ws/search/{query} (spaces → dashes)
2. Parse div.film-poster elements:
   - a[href] → media_id via _extract_id(href) (strip domain, take path)
   - img → image (prefer data-src)
   - a.title attribute or a.text → title
   - "/series/" in href → media_type="tv", else "movie"
3. Parse div.film-detail elements (matched by index):
   - h3.film-name → title refinement
   - span.fdi-item[0] → year
   - span.fdi-item[2] → duration
```

### Stream Extraction
```
1. GET https://flixhq.ws/{media_id}
2. Regex: const pl_url = '([^']+)'  → embed page URL
3. GET {pl_url} (embed/listing page)
4. Parse ul > li > a[data-id] → server links
   - Prefer any with "subdrc" in data-id
   - Fallback: first link
5. GET {embed_url} (data-id attribute = full URL)
6. Regex 1: https?://[^\s"'<>]+\.m3u8[^\s"'<>]*  → m3u8 URL
7. Regex 2: https?://srt\.[^\s"'<>]+\.vtt[^\s"'<>]*  → subtitle URLs (deduplicated via set)
```

## IDLIX (Sub Indo Provider)

### Search
```
GET https://z2.idlixku.com/api/search?q={query}
Headers: User-Agent: Mozilla/5.0 ... Chrome/127.0.0.0
Response: {results: [{id, title, releaseDate, contentType, posterPath}]}
- Year: releaseDate[:4]
- Image: posterPath → prefix https://image.tmdb.org/t/p/w500 if relative
- contentType defaults to "movie"
```

### Stream Extraction (Pentos Flow)
```
0. Load cached renewal tokens from ~/.config/nontonaja/idlix_tokens.json

1. FAST PATH (token exists for content_id):
   POST /api/watch/session/refresh-claim
   Body: {"renewalToken": cached}
   → If kind="pentos": update cache, go to step 5

2. FULL CLAIM (_claim):
   a. GET /api/watch/play-info/{content_type}/{content_id}
      → {"gateToken": "..."}

   b. POST /api/watch/session/claim
      Body: {"gateToken": gate_token}
      → If kind="pentos" immediately: return (rare)

   c. SKIP ATTEMPT:
      POST /api/watch/session/claim (same gateToken)
      → If kind="pentos": return

   d. WAIT FALLBACK:
      wait_s = (unlockAt - serverNow) / 1000  ← milliseconds!
      _countdown() prints \rwaiting Ns..., sleeps 1s per tick
      After wait:
      POST /api/watch/session/claim (third attempt)
      → Return response

3. REDEEM (_redeem):
   POST {pentos["redeemUrl"]}
   Headers:
     User-Agent + Content-Type: application/json
     Origin: https://z2.idlixku.com
     Referer: https://z2.idlixku.com/
   Body: {"claim": pentos["claim"]}
   Response: {
     "url": "https://...config.json?...",
     "subtitles": [{"path": "...*.vtt"}]
   }

4. Return: m3u8 URL + subtitle paths from subtitles[].path

5. Token cache saved to ~/.config/nontonaja/idlix_tokens.json
   (no TTL check — relies on API rejection if expired)
```

## Local Proxy (IDLIX HLS Rewrite)

### Problem
IDLIX CDN serves CMAF segments with obfuscated extensions (.jpg, .css, .js). ffmpeg rejects these extensions causing playback delays.

### Solution
```
1. GET {master_url} — fetch master playlist
2. Parse #EXT-X-STREAM-INF → select highest BANDWIDTH variant
3. GET {sub_url} — fetch segment playlist
4. Rewrite m3u8:
   - #EXT-X-MAP:URI="..." → http://127.0.0.1:{port}/init.mp4
   - Lines starting with http → http://127.0.0.1:{port}/seg/{idx}.ts
   - Tags/comments → passthrough
5. Start ThreadingHTTPServer (allow_reuse_address=True)
6. Serve:
   - GET /playlist.m3u8 → rewritten m3u8 (Content-Type: application/vnd.apple.mpegurl)
   - GET /init.mp4 → proxy init_url
   - GET /seg/{N}.ts → proxy seg_map[N]
7. Force Content-Type: video/mp4 if response doesn't contain "video"
```

### Flow Diagram
```
mpv → localhost:PORT/playlist.m3u8
         ↓
    proxy serves rewritten m3u8 (URLs point to localhost/seg/N.ts)
         ↓
    mpv requests localhost/seg/N.ts
         ↓
    proxy fetches original CDN URL (obfuscated .jpg/.css/.js)
         ↓
    serves as video/mp4 → ffmpeg accepts
```

## Subtitle Merging

### Option 2/3 (FlixHQ + IDLIX)
```
1. Fetch FlixHQ stream → video URL + FlixHQ subtitle URLs (srt.*.vtt)
2. Search IDLIX by title → exact match or substring containment
3. Fetch IDLIX stream → extract subtitle paths from redeem response
4. Combine: flixhq_subs + idlix_subs
5. Download each to temp dir:
   - File: sub_{lang}.ext (.vtt or .srt based on URL)
   - Language: extracted from URL after last _ before .
6. Pass to mpv: --sub-file={path} for each
7. Cleanup: shutil.rmtree(sub_dir)
```

### Cross-Source Deduplication
```
Search-time (_search):
  - Normalize: strip " (YYYY)" suffix, lowercase
  - LK21 results first, deduplicated by normalized title
  - FlixHQ added if normalized title NOT in LK21 set
  - IDLIX added if normalized title NOT in existing set
  - Sort: year descending, then alphabetical

Stream-time (_get_stream):
  - IDLIX matched to FlixHQ via word-overlap scoring (50% threshold)
  - Prefer matching media_type (movie vs tv)
```
