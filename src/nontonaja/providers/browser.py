from __future__ import annotations

import asyncio
import base64
import tempfile
from playwright.async_api import async_playwright, Page, Frame, Browser


_browser: Browser | None = None
_playwright_instance = None


async def _get_browser() -> Browser:
    global _browser, _playwright_instance
    if _browser and _browser.is_connected():
        return _browser

    _playwright_instance = await async_playwright().start()
    _browser = await _playwright_instance.chromium.launch(
        headless=True,
        executable_path="/usr/bin/chromium",
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    )
    return _browser


async def download_via_frame(video_url: str, frame: Frame, output_path: str = "") -> str:
    """Download video via fetch() from within the correct frame context."""
    if not output_path:
        output_path = tempfile.mktemp(suffix=".mp4", prefix="nontonaja-")

    # Get total size via HEAD
    total = await frame.evaluate('''async (url) => {
        const resp = await fetch(url, { method: "HEAD" });
        return parseInt(resp.headers.get("content-length") || "0");
    }''', video_url)
    total = int(total) if total else 0

    if total == 0:
        return output_path

    chunk_size = 5 * 1024 * 1024
    offset = 0

    with open(output_path, "wb") as f:
        while offset < total:
            b64 = await frame.evaluate('''async (args) => {
                const [url, start, end] = args;
                const resp = await fetch(url, {
                    headers: { "Range": "bytes=" + start + "-" + end },
                });
                const buf = await resp.arrayBuffer();
                const bytes = new Uint8Array(buf);
                let binary = "";
                for (let i = 0; i < bytes.byteLength; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                return btoa(binary);
            }''', [video_url, offset, offset + chunk_size - 1])

            data = base64.b64decode(b64)
            f.write(data)
            offset += len(data)
            if len(data) < chunk_size:
                break

    return output_path


async def find_player_frame(page: Page) -> Frame | None:
    """Find the frame containing the video player (abyssplayer.com)."""
    for frame in page.frames:
        url = frame.url or ""
        if "abyssplayer" in url or "abyss.to" in url:
            try:
                has_video = await frame.evaluate('() => !!document.querySelector("video")')
                if has_video:
                    return frame
            except Exception:
                continue
    return None


async def get_video_url_from_frame(frame: Frame) -> str | None:
    """Extract video URL from JWPlayer in the frame context."""
    import asyncio
    for _ in range(10):
        try:
            url = await frame.evaluate(
                '() => document.querySelector("video")?.src '
                '|| (typeof jwplayer !== "undefined" && jwplayer()?.getPlaylistItem()?.file) '
                '|| null'
            )
            if url:
                return url
        except Exception:
            pass
        await asyncio.sleep(1)
    return None


async def fetch_rendered(url: str, wait_for: str = "body", timeout: int = 15000) -> str:
    browser = await _get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await page.wait_for_selector(wait_for, timeout=timeout)
        await asyncio.sleep(2)
        return await page.content()
    finally:
        await page.close()


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
