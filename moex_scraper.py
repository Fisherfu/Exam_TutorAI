"""
moex_scraper.py  ← 精簡版 v2
- 年度：民國 110~115 年（西元 2021~2026）
- 去重：URL 去重 + 【檔案內容 MD5 去重】（同份試卷不同類科會被剔除）
- 目標考試：高考三級 / 地方特考三等 / 原住民族 / 身障特考

用法：python moex_scraper.py
"""

import hashlib
import requests
from bs4 import BeautifulSoup
import os, time, json, re
from datetime import datetime
from urllib.parse import urljoin
import data_loader

# ──────────────────────────────────────────────
# 設定（讀取 config.json）
# ──────────────────────────────────────────────
config = data_loader.load_config()

BASE_URL     = "https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx"
DOWNLOAD_DIR = "downloaded_pdfs"
LOG_FILE     = "scraper_log.json"

TARGET_EXAM_KEYWORDS = config.get("target_exam_keywords", ["高等考試三級", "地方政府公務人員", "原住民族", "身心障礙"])
TARGET_SUBJECT       = config.get("target_subject", config.get("subject_name", "社會學"))

# 民國 110~115 年 → 西元 2021~2026
YEAR_RANGE    = list(range(2021, 2027))
REQUEST_DELAY = 2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9",
}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ──────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────
def get_tokens(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    ids  = ["__VIEWSTATE","__VIEWSTATEGENERATOR","__EVENTVALIDATION","__VIEWSTATEENCRYPTED"]
    return {i: (soup.find("input",{"id":i}) or {}).get("value","") for i in ids}


def safe_post(session, data, timeout=30):
    for attempt in range(3):
        try:
            time.sleep(REQUEST_DELAY)
            r = session.post(BASE_URL, data=data, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"    ⚠️ 請求失敗（{attempt+1}/3）: {e}")
            time.sleep(5)
    return None


# ──────────────────────────────────────────────
# 核心流程
# ──────────────────────────────────────────────
def fetch_exam_list(session, year):
    """取得該年度符合關鍵字的考試清單"""
    print(f"  取得 {year-1911} 年考試清單...")
    r = session.get(BASE_URL, headers=HEADERS, timeout=30)
    tokens = get_tokens(r.text)

    data = {
        **tokens,
        "__EVENTTARGET": "", "__EVENTARGUMENT": "",
        "ctl00$holderContent$wUctlExamYearStart$ddlExamYear": str(year),
        "ctl00$holderContent$wUctlExamYearEnd$ddlExamYear":   str(year),
        "ctl00$holderContent$ddlExamCode": "",
        "ctl00$holderContent$btnYear": "依考試年度設定考試簡稱",
    }
    r = safe_post(session, data)
    if not r:
        return [], None

    soup   = BeautifulSoup(r.text, "html.parser")
    select = soup.find("select", {"id": "ctl00_holderContent_ddlExamCode"})
    if not select:
        return [], soup

    matched = []
    for opt in select.find_all("option"):
        code = opt.get("value","").strip()
        name = opt.get_text(strip=True)
        if not code or name in ("","所有考試簡稱..."):
            continue
        if any(kw in name for kw in TARGET_EXAM_KEYWORDS):
            matched.append({"code": code, "name": name})

    return matched, soup


def search_pdfs(session, page_soup, year, exam):
    """搜尋特定考試，回傳含社會學的 PDF 連結"""
    tokens = get_tokens(str(page_soup))
    data = {
        **tokens,
        "__EVENTTARGET": "", "__EVENTARGUMENT": "",
        "ctl00$holderContent$wUctlExamYearStart$ddlExamYear": str(year),
        "ctl00$holderContent$wUctlExamYearEnd$ddlExamYear":   str(year),
        "ctl00$holderContent$ddlExamCode": exam["code"],
        "ctl00$holderContent$btnSearch": "查詢",
        "ctl00$holderContent$hidStatus": "1",
    }
    r = safe_post(session, data)
    if not r:
        return []

    soup  = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", {"id": "ctl00_holderContent_tblExamQand"})
    if not table:
        for t in soup.find_all("table"):
            if TARGET_SUBJECT in t.get_text():
                table = t; break
    if not table:
        return []

    links = []
    for row in table.find_all("tr"):
        if TARGET_SUBJECT not in row.get_text(separator=" ", strip=True):
            continue
        for a in row.find_all("a", href=True):
            href      = a["href"]
            link_text = a.get_text(strip=True)
            is_pdf    = any([".pdf" in href.lower(), "QandADown" in href,
                             "試題" in link_text, "題目" in link_text])
            if not is_pdf:
                continue
            full_url = (href if href.startswith("http")
                        else f"https://wwwq.moex.gov.tw{href}" if href.startswith("/")
                        else urljoin(BASE_URL, href))
            links.append({"url": full_url, "link_text": link_text,
                          "excerpt": row.get_text(separator=" ",strip=True)[:100]})
    return links


def file_md5(path: str) -> str:
    """計算檔案 MD5（用於內容去重）"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_pdf(session, url, filename, meta, seen_hashes: set) -> str:
    """
    下載 PDF。
    - 跳過已存在的同名檔
    - 下載後計算 MD5：若已有相同內容，刪除並回傳 'dup'
    - 成功回傳 'ok'，失敗回傳 'fail'
    """
    fpath = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(fpath) and os.path.getsize(fpath) > 1024:
        # 既有檔案也要查重
        h = file_md5(fpath)
        if h in seen_hashes:
            os.remove(fpath)
            mpath = fpath + ".meta.json"
            if os.path.exists(mpath):
                os.remove(mpath)
            return "dup"
        seen_hashes.add(h)
        print(f"    ✅ 已存在：{filename}")
        return "ok"

    try:
        time.sleep(1)
        r = session.get(url, headers=HEADERS, timeout=60, stream=True)
        if r.status_code != 200:
            print(f"    ❌ HTTP {r.status_code}")
            return "fail"
        with open(fpath, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        # ── 內容去重 ──
        h = file_md5(fpath)
        if h in seen_hashes:
            os.remove(fpath)  # 內容重複，刪除
            print(f"    🗑️  內容重複，刪除：{filename}")
            return "dup"
        seen_hashes.add(h)

        kb = os.path.getsize(fpath) / 1024
        print(f"    ✅ {filename}  ({kb:.0f} KB)")
        with open(fpath + ".meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return "ok"

    except Exception as e:
        print(f"    ❌ {e}")
        return "fail"



# ──────────────────────────────────────────────
# 主程式
# ──────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"  考選部社會學考古題下載器（精簡版 v2）")
    print(f"  年度：{YEAR_RANGE[0]-1911}~{YEAR_RANGE[-1]-1911} 年（民國）")
    print(f"  去重策略：URL 去重 ＋ 檔案內容 MD5 去重")
    print("=" * 60)

    session     = requests.Session()
    seen_urls   = set()   # URL 層去重
    seen_hashes = set()   # 內容層去重（MD5）← 關鍵！
    log         = {"start_time": datetime.now().isoformat(),
                   "downloaded": [], "failed": [], "dup_skipped": 0}
    total_dl    = 0

    for year in YEAR_RANGE:
        print(f"\n📅 民國 {year-1911} 年")
        exams, page_soup = fetch_exam_list(session, year)

        if not exams:
            print(f"  ⚠️ 無符合考試")
            continue

        print(f"  符合考試：{len(exams)} 個")
        for ex in exams:
            print(f"    [{ex['code']}] {ex['name'][:55]}")

        for exam in exams:
            print(f"\n  🔍 {exam['name'][:50]}")
            pdf_links = search_pdfs(session, page_soup, year, exam)

            if not pdf_links:
                print(f"    ⚠️ 找不到社會學 PDF")
                continue

            # URL 去重
            unique_links = []
            for lk in pdf_links:
                if lk["url"] not in seen_urls:
                    seen_urls.add(lk["url"])
                    unique_links.append(lk)

            url_dup = len(pdf_links) - len(unique_links)
            if url_dup:
                print(f"    URL 去重：{url_dup} 個")
            if not unique_links:
                print(f"    ⚠️ 無新 URL")
                continue

            for i, lk in enumerate(unique_links):
                safe  = re.sub(r'[\\/:*?"<>|]', "_", exam["name"][:40])
                fname = f"{year-1911}_{safe}_{i+1}.pdf"
                meta  = {
                    "year": year, "roc_year": year-1911,
                    "exam_code": exam["code"], "exam_name": exam["name"],
                    "subject": TARGET_SUBJECT,
                    "link_text": lk["link_text"], "url": lk["url"],
                    "source_text": lk["excerpt"],
                }
                result = download_pdf(session, lk["url"], fname, meta, seen_hashes)
                if result == "ok":
                    total_dl += 1
                    log["downloaded"].append({**meta, "filename": fname})
                elif result == "dup":
                    log["dup_skipped"] = log.get("dup_skipped", 0) + 1
                else:
                    log["failed"].append({**meta, "filename": fname})

    log["end_time"]         = datetime.now().isoformat()
    log["total_downloaded"] = total_dl
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"  ✅ 完成！")
    print(f"  保留 PDF（唯一內容）：{total_dl} 個")
    print(f"  內容重複已刪除：    {log.get('dup_skipped', 0)} 個")
    print(f"  📁 {DOWNLOAD_DIR}/")
    if log["failed"]:
        print(f"  ⚠️ 下載失敗：{len(log['failed'])} 個")
    print("=" * 60)
    print("\n➡️  下一步：python pdf_to_questions.py")



if __name__ == "__main__":
    main()
