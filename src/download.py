import asyncio
import json
import os
import random
import sys
from typing import Any, TypedDict, cast

import httpx

OUTPUT_DIR = "mangas"
RETRY_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_JITTER_SECONDS = 0.2


DOWNLOAD_CONCURRENCY = 16


class MangaItem(TypedDict, total=False):
    id: int
    manga: str


def normalize_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def load_mangas(path: str) -> dict[str, MangaItem]:
    with open(path, encoding="utf-8") as f:
        raw: Any = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("Invalid JSON format: top-level object is required")

    data = cast(dict[str, Any], raw)
    res: dict[str, MangaItem] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            res[key] = cast(MangaItem, value)

    return res


def should_retry(exc: httpx.HTTPError) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or 500 <= status_code <= 599

    if isinstance(exc, httpx.RequestError):
        return True

    return False


async def download_one(client: httpx.AsyncClient, item: MangaItem, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        manga_id = item.get("id")
        manga_url = item.get("manga")

        if not isinstance(manga_id, int) or not isinstance(manga_url, str) or not manga_url:
            print(f"Skip invalid item: {item}")
            return

        url = normalize_url(manga_url)
        output_path = os.path.join(OUTPUT_DIR, f"{manga_id}.png")
        temp_path = output_path + ".tmp"

        if os.path.exists(output_path):
            print(f"Skipped: {manga_id} (already exists)")
            return

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    message = f"Non-200 response, not writing file ({manga_id}): status={resp.status_code}"
                    print(message)
                    raise httpx.HTTPStatusError(message, request=resp.request, response=resp)

                try:
                    with open(temp_path, "wb") as f:
                        f.write(resp.content)
                    os.replace(temp_path, output_path)
                except OSError as write_error:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
                    print(f"Write failed ({manga_id}): {write_error}")
                    return

                print(f"Downloaded: {manga_id} (status=200)")
                return
            except httpx.HTTPError as e:
                if not should_retry(e):
                    print(f"Download failed ({manga_id}): {e}")
                    return

                if attempt == RETRY_ATTEMPTS:
                    print(f"Download failed after {RETRY_ATTEMPTS} attempts ({manga_id}): {e}")
                    return

                wait_seconds = (BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))) + random.uniform(0, BACKOFF_JITTER_SECONDS)
                print(f"Retry {attempt}/{RETRY_ATTEMPTS - 1} (current/total retries) for {manga_id} in {wait_seconds:.2f}s: {e}")
                await asyncio.sleep(wait_seconds)


async def download_all(data: dict[str, MangaItem]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    items = list(data.values())
    semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        await asyncio.gather(*(download_one(client, item, semaphore) for item in items))


async def main() -> None:
    json_path = sys.argv[1] if len(sys.argv) > 1 else "mangas/mangas.json"
    data = load_mangas(json_path)
    await download_all(data)


if __name__ == "__main__":
    asyncio.run(main())
