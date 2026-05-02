import os
import io
import requests
import urllib.parse
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import json
import re
import time
from pdfminer.high_level import extract_text
from fastapi import FastAPI
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="自律連動型・法的リサーチAPI（完全版）")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開発中は "*" でOK。本番では源内のドメインに制限。
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ID = os.environ.get("GCP_PROJECT", "YOUR_PROJECT_ID_HERE")
LOCATION = "asia-northeast1"

vertexai.init(project=PROJECT_ID, location=LOCATION)
model_pro = GenerativeModel("gemini-2.5-pro")
model_flash = GenerativeModel("gemini-2.5-flash")

class LegalRequest(BaseModel):
    user_query: str

# --- e-Gov関連機能 ---

def fetch_egov_law(law_name: str, date: str = None) -> str:
    """e-Gov APIから指定日付（または最新）の法令全文を取得"""
    try:
        # 1. 法令番号の検索
        list_url = "https://laws.e-gov.go.jp/api/1/lawlists/2"
        res = requests.get(list_url, timeout=20)
        if res.status_code != 200: return ""
        root = ET.fromstring(res.content)
        
        matches = []
        for info in root.findall(".//LawNameListInfo"):
            name_tag = info.find("LawName")
            if name_tag is not None and law_name in name_tag.text:
                matches.append((info.find("LawNo").text, name_tag.text))
        
        if not matches: return ""
        # 最も名前に適合するものを選択（短い順）
        law_num = sorted(matches, key=lambda x: len(x[1]))[0][0]

        # 2. 全文取得 (dateがあれば当時のものを取得)
        data_url = f"https://laws.e-gov.go.jp/api/1/lawdata/{law_num}"
        params = {"date": date} if date else {}
        res = requests.get(data_url, params=params, timeout=25)
        
        if res.status_code != 200: return ""
        root = ET.fromstring(res.content)
        texts = [elem.text.strip() for elem in root.iter() if elem.text and elem.text.strip()]
        return "\n".join(texts)
    except Exception as e:
        print(f"e-Gov取得エラー: {e}")
        return ""

# --- 裁判所サイト・スクレイピング機能 ---

def scrape_pdf_full(pdf_url: str) -> str:
    """PDFを全ページ読み切り、テキスト化する"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(pdf_url, headers=headers, timeout=30)
        if res.status_code == 200:
            full_text = extract_text(io.BytesIO(res.content))
            return re.sub(r'\s+', ' ', full_text).strip()
    except: pass
    return ""

def search_precedents(q1: str, q2: str, year_from: str = "", year_to: str = "") -> list:
    """sweep_justiceロジックで判例を最大30件取得"""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    
    chain = [
        {"num": "2", "id": "1", "name": "最高裁"},
        {"num": "3", "id": "2", "name": "高裁"},
        {"num": "1", "id": "",  "name": "統合検索"}
    ]
    
    all_items = []
    for db in chain:
        if len(all_items) >= 3: break
        
        search_url = f"https://www.courts.go.jp/app/hanrei_jp/search{db['num']}"
        referer = f"https://www.courts.go.jp/hanrei/search{db['num']}/index.html"
        
        # 期間指定の反映 (yyyy形式を想定)
        params = {
            "query1": q1, "query2": q2, "courtCaseType": db['id'],
            "filter[judgeGengoFrom]": "4", "filter[judgeYearFrom]": year_from, 
            "filter[judgeMonthFrom]": "", "filter[judgeDayFrom]": "",
            "filter[judgeGengoTo]": "4", "filter[judgeYearTo]": year_to, 
            "filter[judgeMonthTo]": "", "filter[judgeDayTo]": ""
        }
        
        try:
            res = session.get(search_url, params=params, headers={"Referer": referer}, timeout=20)
            soup = BeautifulSoup(res.content, "html.parser")
            
            links = [urllib.parse.urljoin(res.url, a['href']) for a in soup.select('a[href*="/detail"]')]
            # 重複削除
            links = list(dict.fromkeys(links))
            
            for link in links:
                if len(all_items) >= 3: break
                time.sleep(0.5)
                d_res = session.get(link)
                d_soup = BeautifulSoup(d_res.content, "html.parser")
                
                item = {"source_url": link}
                for dt in d_soup.find_all("dt"):
                    key = dt.get_text(strip=True)
                    dd = dt.find_next_sibling("dd")
                    if dd: item[key] = dd.get_text("\n", strip=True)
                
                pdf_link = d_soup.find("a", href=lambda x: x and "hanrei-pdf" in x)
                if pdf_link:
                    pdf_url = urllib.parse.urljoin(link, pdf_link['href'])
                    item["pdf_text"] = scrape_pdf_full(pdf_url)
                
                all_items.append(item)
        except: continue
        
    return all_items

# --- メインロジック ---

@app.post("/generate-report")
def generate_report(request: LegalRequest):
    # 1. プロンプト解析 (Gemini Flash)
    # ここで法令、キーワード、期間を抽出する
    analysis_prompt = f"""
    ユーザーの質問: {request.user_query}
    
    上記に基づき、以下の情報をJSON形式で出力してください。
    - law_names: 関連する法律名のリスト (最大5件)
    - search_keywords: 判例検索用の単語2つ (スペース区切り)
    - year_from: 期間指定があればその開始年 (数値のみ。なければ"")
    - year_to: 期間指定があればその終了年 (数値のみ。なければ"")
    """
    analysis_res = model_flash.generate_content(analysis_prompt).text
    # JSON抽出用の簡易クレンジング
    json_str = re.search(r'\{.*\}', analysis_res, re.DOTALL).group()
    analysis = json.loads(json_str)
    
    # 2. 現行法令の取得
    current_laws = {}
    for name in analysis.get("law_names", []):
        text = fetch_egov_law(name)
        if text: current_laws[name] = text

    # 3. 判例の取得 (最大30件)
    kws = analysis.get("search_keywords", "").split()
    q1 = kws[0] if len(kws) > 0 else ""
    q2 = kws[1] if len(kws) > 1 else ""
    
    cases = search_precedents(q1, q2, year_from=analysis.get("year_from", ""), year_to=analysis.get("year_to", ""))
    cases = cases[:5]  # ここを追加！pkill -f uvicorn

    # ヒットしない場合の再試行（リサーチワードをより一般的なものに調整）
    if not cases:
        retry_prompt = f"「{request.user_query}」を判例検索するために、より一般的でヒットしやすい単語2つをスペース区切りで出せ。"
        retry_kw = model_flash.generate_content(retry_prompt).text.strip().split()
        if len(retry_kw) >= 2:
            cases = search_precedents(retry_kw[0], retry_kw[1])

    # 4. 当時施行法の取得 (連動検索)
    # 判例の中身から「判決年月日」と「法条」を抜き出して旧法を取得
    historical_laws = []
    if cases:
        # 代表的な数件から情報を抽出する指示
        case_samples = [{"裁判年月日": c.get("裁判年月日", ""), "参照法条": c.get("参照法条", ""), "本文一部": c.get("pdf_text", "")[:500]} for c in cases[:5]]
        extraction_prompt = f"""
        以下の判例情報から、判決当時の法令を検索するために「法律名」と「判決年月日のYYYYMMDD形式」のペアをJSONリストで出力してください。
        {json.dumps(case_samples, ensure_ascii=False)}
        """
        try:
            ext_res = model_flash.generate_content(extraction_prompt).text
            ext_json = json.loads(re.search(r'\[.*\]', ext_res, re.DOTALL).group())
            for pair in ext_json:
                h_text = fetch_egov_law(pair["法律名"], date=pair["年月日"])
                if h_text:
                    historical_laws.append({"name": pair["法律名"], "date": pair["年月日"], "text": h_text})
        except: pass

    # 5. 生データ全投入プロンプト (Gemini Pro) - 厳格なトークン制限版
    # 全体で約3万文字（約4.5万トークン）に収まるようにデータを絞り込みます

    # 現行法: 関連性が最も高い1件のみ、10,000文字
    safe_current_laws = {}
    if current_laws:
        first_law = list(current_laws.keys())[0]
        safe_current_laws[first_law] = current_laws[first_law][:10000]

    # 判例: 上位3件のみ、各4,000文字
    safe_cases = []
    for c in cases[:3]:
        safe_c = c.copy()
        if "pdf_text" in safe_c:
            safe_c["pdf_text"] = safe_c["pdf_text"][:4000]
        safe_cases.append(safe_c)
    
    # 当時法 (旧法): 最初の1件のみ、10,000文字
    safe_historical_laws = []
    if historical_laws:
        safe_historical_laws.append({
            "name": historical_laws[0]["name"], 
            "date": historical_laws[0]["date"], 
            "text": historical_laws[0]["text"][:10000]
        })

    final_prompt = f"""
    以下の資料を全て読み込み、ユーザーの質問に対して現在の法令に基づいた正確なレポートを作成してください。

    【ユーザーの質問】
    {request.user_query}

    ---
    【参考資料1：最新法令（e-Gov）】
    {json.dumps(safe_current_laws, ensure_ascii=False)}

    ---
    【参考資料2：関連判例 上位3件（裁判所サイト 生データ）】
    {json.dumps(safe_cases, ensure_ascii=False)}

    ---
    【参考資料3：事件当時の法令（逆引き取得）】
    {json.dumps(safe_historical_laws, ensure_ascii=False)}
    """

    # 送信前に念のためターミナルに文字数を出力して確認
    print(f"--- 最終プロンプト文字数: {len(final_prompt)} 文字 ---")

    response = model_pro.generate_content(final_prompt)
    
    return {
        "status": "success",
        "analysis": analysis,
        "report": response.text
    }
# ==========================================
# AWS genai-web 連携専用エンドポイント
# (既存の /generate-report には一切影響しません)
# ==========================================
from fastapi import Request

# ==========================================
# AWS連携用：絶対に422エラーを出さない無敵エンドポイント
# ==========================================
@app.post("/predict")
async def predict_aws(body: dict):
    try:
        # 厳しい自動チェックを外し、届いたJSONをそのまま開ける
        # body = await request.json()

        # ▼ 追加1：AWSから送られてきたナマのデータをすべてログに出す
        print(f"=== [DEBUG] AWSからの受信データ ===\n{body}", flush=True)
        
        user_prompt = ""
        if isinstance(body, dict):
            # 1. AWS(genai-web)の標準仕様である "inputs" の中身を最優先で取得
            if "inputs" in body and isinstance(body["inputs"], dict):
                for val in body["inputs"].values():
                    if isinstance(val, str) and val.strip() != "":
                        user_prompt = val
                        break
            
            # 2. 予備ルート（システムIDの誤認を防ぐため、一番長い文字列を質問とみなす）
            if not user_prompt:
                strings = []
                for key, val in body.items():
                    if isinstance(val, str) and "history" not in key.lower():
                        strings.append(val)
                if strings:
                    user_prompt = max(strings, key=len)
        
        # ▼ 追加2：抽出ロジックが何を「質問」として認識したかログに出す
        print(f"=== [DEBUG] 抽出したプロンプト ===\n{user_prompt}", flush=True)
                    
        # 文字が届いていなかった場合の安全策
        if not user_prompt:
            return {"outputs": f"【データ受信エラー】文字が届きませんでした。AWSから届いた中身: {body}"}

        # --- 以下は既存のレポート生成処理 ---
        analysis_prompt = f"ユーザーの質問: {user_prompt}\n上記に基づき、関連する法律名(law_names:最大1件のリスト)と検索単語2つ(search_keywords:スペース区切り)をJSONで出力してください。"
        analysis_res = model_flash.generate_content(analysis_prompt).text
        
        import json, re
        json_match = re.search(r'\{.*\}', analysis_res, re.DOTALL)
        analysis = json.loads(json_match.group()) if json_match else {"law_names": [], "search_keywords": ""}
        
        laws = {}
        for name in analysis.get("law_names", []):
            text = fetch_egov_law(name)
            if text: laws[name] = text[:10000] 
        
        kws = analysis.get("search_keywords", "").split()
        q1 = kws[0] if len(kws) > 0 else ""
        q2 = kws[1] if len(kws) > 1 else ""
        cases = search_precedents(q1, q2)
        safe_cases = [{"裁判年月日": c.get("裁判年月日", ""), "pdf_text": c.get("pdf_text", "")[:4000]} for c in cases[:3]]

        final_prompt = f"""
        ユーザーの質問に対して現在の法令・判例に基づいた正確なMarkdownレポートを作成してください。
        【質問】 {user_prompt}
        【法令】 {json.dumps(laws, ensure_ascii=False)}
        【判例】 {json.dumps(safe_cases, ensure_ascii=False)}
        """
        response = model_pro.generate_content(final_prompt)
        
        return {"outputs": response.text}

    except Exception as e:
        return {"outputs": f"【Python内部エラー】{str(e)}\n受信データ: {body}"}