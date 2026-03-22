import os
import time
import traceback
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SAVE_DIR = r"E:\MyProjects\ITUassistant\data\itu_pdfs"
os.makedirs(SAVE_DIR, exist_ok=True)

FILES = {
    "facts_2024.pdf": "https://www.itu.int/itu-d/reports/statistics/wp-content/uploads/sites/5/2024/11/2402588_1e_Measuring-digital-development-Facts-and-Figures-2024_v4.pdf",
    "facts_2023.pdf": "https://www.itu.int/itu-d/reports/statistics/wp-content/uploads/sites/5/2023/11/Measuring-digital-development-Facts-and-figures-2023-E.pdf",
    "facts_2022.pdf": "https://www.itu.int/dms_pub/itu-d/opb/ind/d-ind-ict_mdd-2022-pdf-e.pdf",
    "mdd_2024_lldc.pdf": "https://www.itu.int/dms_pub/itu-d/opb/ind/D-IND-ICT_MDD-2024-2-PDF-E.pdf",
    "digital_trends_africa_2025.pdf": "https://www.itu.int/itu-d/reports/statistics/wp-content/uploads/sites/5/2025/04/2500037E_SDDT_2025_Africa_FINAL.pdf",
    "itu_annual_report_2024.pdf": "https://www.itu.int/en/council/planning/Documents/ITU-Annual-report-2024-english.pdf",
    "facts_2024_un.pdf": "https://digitallibrary.un.org/record/4074377/files/4074377.pdf",
    "facts_2023_un.pdf": "https://digitallibrary.un.org/record/4074376/files/4074376.pdf",
}

# 如需代理，取消注释并改成你的本地代理端口
PROXIES: Optional[dict] = None
# PROXIES = {
#     "http": "http://127.0.0.1:7890",
#     "https": "http://127.0.0.1:7890",
# }

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Connection": "keep-alive",
}

CHUNK_SIZE = 1024 * 256  # 256 KB
CONNECT_TIMEOUT = 20
READ_TIMEOUT = 180
MAX_RETRIES = 5


def build_session() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=MAX_RETRIES,
        connect=MAX_RETRIES,
        read=MAX_RETRIES,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)

    if PROXIES:
        session.proxies.update(PROXIES)

    return session


def get_remote_size(session: requests.Session, url: str) -> Optional[int]:
    try:
        resp = session.head(url, timeout=(CONNECT_TIMEOUT, 30), allow_redirects=True)
        if resp.ok:
            cl = resp.headers.get("Content-Length")
            return int(cl) if cl and cl.isdigit() else None
    except Exception:
        pass
    return None


def download_file(session: requests.Session, filename: str, url: str) -> bool:
    final_path = os.path.join(SAVE_DIR, filename)
    temp_path = final_path + ".part"

    existing_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
    remote_size = get_remote_size(session, url)

    if remote_size and os.path.exists(final_path) and os.path.getsize(final_path) == remote_size:
        print(f"[SKIP] {filename} already complete")
        return True

    headers = {}
    mode = "wb"

    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"
        mode = "ab"
        print(f"[RESUME] {filename} from {existing_size} bytes")

    print(f"[START] {filename}")

    try:
        with session.get(
            url,
            stream=True,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=True,
            headers=headers,
        ) as resp:
            if resp.status_code not in (200, 206):
                print(f"[FAIL] {filename} status={resp.status_code}")
                return False

            total = resp.headers.get("Content-Length")
            total = int(total) if total and total.isdigit() else None

            downloaded = existing_size
            last_print = time.time()

            with open(temp_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_print >= 1.5:
                        if remote_size:
                            pct = downloaded / remote_size * 100
                            print(f"    {filename}: {downloaded}/{remote_size} bytes ({pct:.1f}%)")
                        else:
                            print(f"    {filename}: {downloaded} bytes")
                        last_print = now

        # 简单校验
        final_size = os.path.getsize(temp_path)
        if remote_size and final_size < remote_size:
            print(f"[FAIL] {filename} incomplete: {final_size}/{remote_size}")
            return False

        os.replace(temp_path, final_path)
        print(f"[OK] {filename} saved -> {final_path}")
        return True

    except KeyboardInterrupt:
        print(f"[STOP] interrupted while downloading {filename}")
        raise
    except Exception as e:
        print(f"[ERROR] {filename}: {e}")
        traceback.print_exc()
        return False


def main():
    session = build_session()
    success = 0
    failed = []

    for filename, url in FILES.items():
        ok = download_file(session, filename, url)
        if ok:
            success += 1
        else:
            failed.append((filename, url))
        time.sleep(3)

    print("\n===== SUMMARY =====")
    print(f"Success: {success}")
    print(f"Failed: {len(failed)}")

    if failed:
        print("Failed files:")
        for name, url in failed:
            print(f" - {name}: {url}")


if __name__ == "__main__":
    main()
