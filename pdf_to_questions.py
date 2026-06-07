"""
pdf_to_questions.py  ← 改良版
- 自動去除重複 PDF（依檔案大小 hash 判斷）
- 改用 gemini-1.5-flash（免費版每日 1500 次，不再 429）
- 加入 retry 機制與速率控制

用法：python pdf_to_questions.py
"""

import os
import sys
import json
import glob
import hashlib
import time
from datetime import datetime

import pdfplumber
import google.generativeai as genai
from dotenv import load_dotenv

# ──────────────────────────────────────────────
# 設定區
# ──────────────────────────────────────────────
DOWNLOAD_DIR       = "downloaded_pdfs"
QUESTION_BANK_FILE = "question_bank.json"
MIN_TEXT_LENGTH    = 200
MAX_TEXT_TO_GEMINI = 8000
API_DELAY          = 5   # 每次 API 呼叫間隔秒數（避免超頻）
MAX_RETRIES        = 3

EXAM_CATEGORY_MAP = {
    "高等考試三級": "高考三級",
    "地方政府公務人員": "地方特考三等",
    "原住民族": "原住民族考試",
    "身心障礙": "身障特考",
}

# ──────────────────────────────────────────────
# 初始化 Gemini（強制使用 gemini-1.5-flash）
# ──────────────────────────────────────────────
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("❌ 找不到 GEMINI_API_KEY，請確認 .env 檔案")
    sys.exit(1)

genai.configure(api_key=api_key)
# 明確指定 gemini-flash-lite-latest（免費版配額較高）
MODEL_NAME = "models/gemini-flash-lite-latest"
model = genai.GenerativeModel(MODEL_NAME)
print(f"✅ 使用模型：{MODEL_NAME}")


# ──────────────────────────────────────────────
# 工具函式
# ──────────────────────────────────────────────
def file_hash(path: str) -> str:
    """計算檔案 MD5（用於去重複）"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def deduplicate_pdfs(pdf_files: list[str]) -> list[str]:
    """依檔案內容去除重複，回傳唯一 PDF 清單"""
    seen_hashes = {}
    unique = []
    dup_count = 0

    for path in pdf_files:
        h = file_hash(path)
        if h not in seen_hashes:
            seen_hashes[h] = path
            unique.append(path)
        else:
            dup_count += 1

    if dup_count:
        print(f"  🗑️  去除重複：{dup_count} 個（原 {len(pdf_files)} → 唯一 {len(unique)}）")
    return unique


def extract_pdf_text(pdf_path: str) -> str | None:
    """使用 pdfplumber 提取 PDF 全文"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    pages_text.append(txt)
            full_text = "\n".join(pages_text).strip()
            return full_text if full_text else None
    except Exception as e:
        print(f"    ❌ PDF 解析失敗: {e}")
        return None


def parse_with_gemini(text: str, attempt: int = 0) -> list[dict]:
    """呼叫 Gemini 解析題目，含 retry 機制"""
    prompt = f"""
你是台灣公務人員考試「社會學」科目的專業解析器。

以下是從 PDF 解析出來的考試試題文字。
台灣高考與特考的社會學通常為「申論題」（每份試卷約 4 題）。
請找出所有的「申論題」並以嚴格 JSON 格式輸出。

【解析規則】
1. 提取完整的題目文字（包含題號與配分可視情況保留）。
2. type 固定為 "essay"。
3. explanation 請用繁體中文提供解析，點出這題的核心社會學考點、建議答題方向與可引用的理論學者，約 100~150 字。
4. 忽略任何無關的試場規則文字。
5. 若找不到任何題目，輸出 {{"questions": []}}。

【試題文字】
{text[:MAX_TEXT_TO_GEMINI]}

【輸出格式（嚴格 JSON，不加 markdown code block）】
{{
  "questions": [
    {{
      "q": "完整題目內容...",
      "type": "essay",
      "explanation": "本題考點為..."
    }}
  ]
}}
"""
    try:
        time.sleep(API_DELAY)
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        data = json.loads(response.text)
        return data.get("questions", [])

    except Exception as e:
        err_str = str(e)

        # 429 Rate Limit → 等待後重試
        if "429" in err_str and attempt < MAX_RETRIES:
            wait = 65
            if "retry_delay" in err_str:
                try:
                    import re
                    secs = re.search(r'"seconds":\s*(\d+)', err_str)
                    if secs:
                        wait = int(secs.group(1)) + 5
                except Exception:
                    pass
            print(f"    ⏳ API 速率限制，等待 {wait} 秒後重試 (第 {attempt+1} 次)...")
            time.sleep(wait)
            return parse_with_gemini(text, attempt + 1)

        # JSON 解析失敗
        if "JSONDecodeError" in type(e).__name__ or "json" in err_str.lower():
            try:
                import re
                clean = response.text.strip()
                clean = re.sub(r"```[a-z]*\n?", "", clean).strip("` \n")
                return json.loads(clean).get("questions", [])
            except Exception:
                pass

        print(f"    ❌ Gemini 呼叫失敗: {e}")
        return []


def detect_exam_category(exam_name: str) -> str:
    for keyword, category in EXAM_CATEGORY_MAP.items():
        if keyword in exam_name:
            return category
    return "其他"


def load_bank() -> dict:
    if os.path.exists(QUESTION_BANK_FILE):
        with open(QUESTION_BANK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"questions": [], "metadata": {"total": 0, "last_updated": None, "sources": []}}


def save_bank(bank: dict):
    bank["metadata"]["total"] = len(bank["questions"])
    bank["metadata"]["last_updated"] = datetime.now().isoformat()
    with open(QUESTION_BANK_FILE, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# 主程式
# ──────────────────────────────────────────────
def main():
    import re

    print("=" * 60)
    print("  PDF 考古題解析器（改良版）")
    print(f"  模型：{MODEL_NAME}（每日 1,500 次免費額度）")
    print("=" * 60)

    # 找所有 PDF
    all_pdfs = sorted(glob.glob(os.path.join(DOWNLOAD_DIR, "*.pdf")))
    if not all_pdfs:
        print(f"\n❌ {DOWNLOAD_DIR}/ 找不到 PDF，請先執行 moex_scraper.py")
        return

    print(f"\n原始 PDF 數：{len(all_pdfs)}")

    # ── 去重複 ──
    unique_pdfs = deduplicate_pdfs(all_pdfs)
    print(f"唯一 PDF 數：{len(unique_pdfs)}\n")

    bank = load_bank()
    already_parsed = {q.get("source_file") for q in bank["questions"]}
    new_q_total = 0

    for idx, pdf_path in enumerate(unique_pdfs, 1):
        filename = os.path.basename(pdf_path)

        # 跳過已解析
        if filename in already_parsed:
            print(f"[{idx}/{len(unique_pdfs)}] ⏭️  已解析：{filename[:60]}")
            continue

        print(f"\n[{idx}/{len(unique_pdfs)}] 📄 {filename[:60]}")

        # 載入 meta
        meta_path = pdf_path + ".meta.json"
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

        # 提取文字
        text = extract_pdf_text(pdf_path)
        if not text or len(text) < MIN_TEXT_LENGTH:
            print(f"  ⚠️  文字量不足（可能為掃描圖），略過")
            continue
        print(f"  文字：{len(text):,} 字元 → Gemini 解析中...")

        # Gemini 解析
        questions = parse_with_gemini(text)

        if not questions:
            print(f"  ⚠️  未找到申論題")
            continue

        # 附加 metadata
        exam_name = meta.get("exam_name", filename)
        roc_year  = meta.get("roc_year", 0)

        for i, q in enumerate(questions):
            q["id"]            = f"{filename[:-4]}-Q{i+1:02d}"
            q["source"]        = exam_name
            q["year"]          = roc_year
            q["exam_type"]     = exam_name
            q["exam_category"] = detect_exam_category(exam_name)
            q["subject"]       = "社會學"
            q["source_file"]   = filename
            q["type"]          = "essay"

        bank["questions"].extend(questions)
        new_q_total += len(questions)

        label = f"{roc_year}年 {exam_name[:40]}"
        if label not in bank["metadata"]["sources"]:
            bank["metadata"]["sources"].append(label)

        print(f"  ✅ 新增 {len(questions)} 題（目前累計：{len(bank['questions'])} 題）")
        save_bank(bank)  # 即時儲存

    print("\n" + "=" * 60)
    print(f"  ✅ 全部完成")
    print(f"  本次新增：{new_q_total} 題")
    print(f"  題庫總計：{bank['metadata']['total']} 題")
    print(f"  儲存至：{QUESTION_BANK_FILE}")
    print("=" * 60)
    print("\n➡️  下一步：streamlit run app.py")


if __name__ == "__main__":
    main()
