import requests
from bs4 import BeautifulSoup
import time
import re
import json
import io
from urllib.parse import urljoin
from pdfminer.high_level import extract_text

def get_pdf_text(session, pdf_url):
    try:
        res = session.get(pdf_url, timeout=20)
        if res.status_code == 200:
            return re.sub(r'\s+', ' ', extract_text(io.BytesIO(res.content))).strip()
    except: return ""
    return ""

def scrape_detail(session, url):
    try:
        res = session.get(url, timeout=10)
        soup = BeautifulSoup(res.content, "html.parser")
        data = {"source_url": url}
        for dt in soup.find_all("dt"):
            key = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd")
            if dd: data[key] = dd.get_text("\n", strip=True)
        
        pdf_link = soup.find("a", href=lambda x: x and "hanrei-pdf" in x)
        if pdf_link:
            pdf_url = urljoin(url, pdf_link['href'])
            data["pdf_url"] = pdf_url
            print(f"  📄 PDF抽出中: {data.get('事件番号', '不明')}")
            data["pdf_full_text"] = get_pdf_text(session, pdf_url)
        return data
    except: return None

def execute_search(q1, q2):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    
    # 探索優先順位
    chain = [
        {"num": 2, "id": "1", "name": "最高裁"},
        {"num": 3, "id": "2", "name": "高裁"},
        {"num": 1, "id": "",  "name": "統合検索"}
    ]

    for db in chain:
        print(f"[探索中] {db['name']}...")
        url = f"https://www.courts.go.jp/app/hanrei_jp/search{db['num']}"
        params = {"query1": q1, "query2": q2, "courtCaseType": db['id']}
        # 空のフィルタを送らないよう調整
        headers = {"Referer": f"https://www.courts.go.jp/hanrei/search{db['num']}/index.html"}
        
        try:
            res = session.get(url, params=params, headers=headers, timeout=15)
            soup = BeautifulSoup(res.content, "html.parser")
            
            count_tag = soup.select_one(".module-search-result-count")
            count = int(''.join(filter(str.isdigit, count_tag.get_text()))) if count_tag else 0
            print(f"  -> ヒット: {count}件")

            if count > 0:
                links = list(dict.fromkeys([urljoin(res.url, a['href']) for a in soup.select('a[href*="/detail"]')]))[:5]
                items = []
                for link in links:
                    time.sleep(1)
                    item = scrape_detail(session, link)
                    if item: items.append(item)
                return items
        except: continue
    return []

if __name__ == "__main__":
    results = execute_search("著作権", "公衆送信")
    if results:
        with open("search_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        print(f"\n✅ 成功: {len(results)}件を search_results.json に保存しました。")
