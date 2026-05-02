import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import urljoin

def scrape_court_data(q1, q2, limit=5):
    session = requests.Session()
    # 物理検証で成功したヘッダー
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.courts.go.jp/hanrei/search2/index.html"
    })

    # 1. 検索実行（appエンドポイント経由）
    search_url = "https://www.courts.go.jp/app/hanrei_jp/search2"
    params = {
        "query1": q1,
        "query2": q2,
        "courtCaseType": "1" # AND検索を有効にする物理スイッチ
    }
    
    print(f"--- 検索開始: {q1} + {q2} ---")
    res = session.get(search_url, params=params, timeout=15)
    soup = BeautifulSoup(res.content, "html.parser")
    
    # 件数確認
    count_tag = soup.select_one(".module-search-result-count")
    if count_tag:
        print(f"ヒット件数: {count_tag.get_text(strip=True)}")
    
    # 2. 一覧から詳細URLを抽出
    links = []
    for a in soup.select('a[href*="/detail"]'):
        links.append(urljoin(res.url, a['href']))
    
    # 重複排除
    links = list(dict.fromkeys(links))[:limit]
    print(f"取得対象: {len(links)} 件\n")

    # 3. 各詳細ページのスクレイピング
    results = []
    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}] 解析中: {link}")
        time.sleep(1) # サーバーへの礼儀
        
        detail_res = session.get(link, timeout=10)
        d_soup = BeautifulSoup(detail_res.content, "html.parser")
        
        data = {"url": link}
        
        # テーブルデータの抽出
        # <dt>項目名</dt><dd>内容</dd> の構造を正確にキャプチャ
        for dt in d_soup.find_all("dt"):
            key = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd")
            if dd:
                data[key] = dd.get_text(strip=True)
        
        # PDFリンクの抽出
        pdf_link = d_soup.find("a", href=lambda x: x and "hanrei-pdf" in x)
        if pdf_link:
            data["pdf_url"] = urljoin(link, pdf_link['href'])
            
        results.append(data)

    return results

if __name__ == "__main__":
    # 今回の検証キーワードで実行
    items = scrape_court_data("著作権", "公衆送信")
    
    print("\n" + "="*50)
    for item in items:
        print(f"\n■事件番号: {item.get('事件番号')}")
        print(f"  裁判年月日: {item.get('裁判年月日')}")
        print(f"  判示事項: {item.get('判示事項')[:100]}...")
        print(f"  PDFリンク: {item.get('pdf_url')}")
    print("="*50)
