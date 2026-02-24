import asyncio
import json
import os
import re
import sys
from typing import Any

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
}

CONTRIBUTORS_REGEX = re.compile(r"(?P<contributors>翻译：[^#]+)")
TITLE_REGEX = re.compile(r"第(?P<number>\d+)话「(?P<title>[^」]+)」")


async def get_mangas(cookie: str = "") -> dict[str, Any]:
    headers = HEADERS.copy()
    if cookie:
        headers["cookie"] = cookie

    total = 2
    res: dict[str, Any] = {}
    page = 1

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        while len(res) < total and page <= 500:
            url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space/search?host_mid=13148307&page={page}&offset={page}&keyword=%E6%BC%AB%E7%94%BB&features=itemOpusStyle,opusBigCover,forwardListHidden"

            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

                items = data.get("data", {}).get("items", [])
                if not items:
                    break

                for idx, i in enumerate(items):
                    try:
                        opus_data = i["modules"]["module_dynamic"]["major"]["opus"]
                        content = opus_data["summary"]["text"]

                        if "#SEKAI四格漫画#" not in content:
                            continue

                        contributors_match = CONTRIBUTORS_REGEX.search(content)
                        title_match = TITLE_REGEX.search(content)

                        if not contributors_match or not title_match:
                            continue

                        number = int(title_match.group("number"))
                        if number > total:
                            total = number

                        res[str(number)] = {
                            "id": number,
                            "title": title_match.group("title"),
                            "manga": opus_data["pics"][0]["url"],
                            "date": i["modules"]["module_author"]["pub_ts"],
                            "url": "https:" + opus_data["jump_url"],
                            "contributors": {
                                line.split("：", 1)[0].strip(): line.split("：", 1)[1].strip()
                                for line in contributors_match.group("contributors").strip().split()
                                if "：" in line
                            },
                        }

                        print(f"Captured: {number}")
                    except (KeyError, IndexError, TypeError) as e:
                        print(f"Skip item parse error: page={page}, index={idx}, type={type(e).__name__}")
                        continue

                page += 1

            except httpx.HTTPError as e:
                print(f"Request failed: {e}")
                break

    return res


async def main() -> None:
    filename = sys.argv[1] if len(sys.argv) > 1 else "mangas/mangas.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    cookie = os.getenv("BILIBILI_COOKIE", "")
    mangas = await get_mangas(cookie=cookie)
    sorted_mangas = dict(sorted(mangas.items(), key=lambda item: item[1]["id"], reverse=True))

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(sorted_mangas, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
