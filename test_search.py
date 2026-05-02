import requests
from bs4 import BeautifulSoup
import time

def debug_court_structure():
    base_url = "https://www.courts.go.jp/hanrei/search1/index.html"
    
    # ブラウザが送っている指紋（Fingerprint）をHARから完全抽出
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    # セッションを開始（コネクションを維持）
    session = requests.Session()
    session.headers.update(headers)

    print("--- 手順1: 検索画面の『初期化』 ---")
    # まずはパラメータなしでアクセスし、サーバーにセッションを認識させる
    init_res = session.get(base_url, timeout=15)
    print(f"初期アクセス応答: {init_res.status_code}")

    # 人間の操作間隔を模倣
    time.sleep(1)

    print("\n--- 手順2: 検索の実行 ---")
    # Referer（遷移元）をセット。これがないと初期画面に戻される構造
    session.headers.update({"Referer": base_url})
    
    # HARファイルに基づき、空のフィルタもすべて含めた完全なパラメータセット
    params = {
        "query1": "画像",
        "query2": "著作権",
        "filter[judgeGengoFrom]": "", "filter[judgeYearFrom]": "",
        "filter[judgeMonthFrom]": "", "filter[judgeDayFrom]": "",
        "filter[judgeGengoTo]": "", "filter[judgeYearTo]": "",
        "filter[judgeMonthTo]": "", "filter[judgeDayTo]": "",
        "filter[jikenGengo]": "", "filter[jikenYear]": "",
        "filter[jikenCode]": "", "filter[jikenNumber]": "",
        "filter[courtType]": "", "filter[courtSection]": "",
        "filter[courtName]": "", "filter[branchName]": ""
    }

    res = session.get(base_url, params=params, timeout=15)
    print(f"最終URL: {res.url}")

    soup = BeautifulSoup(res.content, "html.parser")
    
    # 構造確認: 検索結果件数クラス ".module-search-result-count" を探す
    count_tag = soup.select_one(".module-search-result-count")
    
    if count_tag:
        print(f"\n✅ 成功: {count_tag.get_text(strip=True)}")
    else:
        # 失敗した場合、どこに戻されたのかをタイトルで判別
        title = soup.title.string.strip() if soup.title else "不明"
        print(f"\n❌ 失敗: 件数表示が見つかりません。")
        print(f"ページタイトル: {title}")
        if "裁判例検索" in title:
            print("→ 検索フォームに差し戻されています。セッションまたはヘッダーの拒絶です。")

if __name__ == "__main__":
    debug_court_structure()
