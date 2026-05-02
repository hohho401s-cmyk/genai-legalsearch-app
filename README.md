
# 法令・判例検索＆AI解説API (Lawsy API)

## 概要
ユーザーからの自然言語による質問を受け取り、関連する日本の法令や判例を自動で検索・取得し、生成AI（Google Gemini）を用いて本格的な法的レポートを作成するAPIです。
e-Gov APIと直接連携して最新の法令条文（XML）を取得するほか、最高裁判所のウェブサイトから判例PDFをスクレイピングして内容を解析する機能を備えています。

## 主な機能
* **法令の自動検索・取得**: ユーザーの質問からAIが適切な法令名を推測し、e-Gov API（`https://laws.e-gov.go.jp/api/1/lawdata/`）へ通信して全文を取得します。
* **判例のスクレイピング＆PDF解析**: 最高裁判所の検索システムにアクセスし、該当する判例のPDFをダウンロード。`pdfplumber`等のライブラリを用いてテキストを抽出・解析します。
* **法的レポートの生成**: 取得した一次情報（法令・判例）をGemini（Flash / Pro）に渡し、法的根拠に基づいた重厚感のある解説レポートを自動生成します。

## 構成ファイル
* `api_main.py` : メインのAPIサーバー。リクエストの受付と、e-Gov APIへの通信ロジックを含みます。
* `sweep_justice.py` : 最高裁判所の判例検索を実行するモジュール。
* `scrape_justice.py` : 取得した判例PDFのダウンロードおよびテキスト抽出処理（スクレイピング）を行います。
* `requirements.txt` : 実行に必要なPythonライブラリ（`beautifulsoup4`, `pdfplumber` など）の一覧。
* `Dockerfile` / `Procfile` : Google Cloud Runやその他のコンテナ環境へデプロイするための設定ファイル。

## 必須の環境変数
本APIを動作させるには、以下の環境変数を設定する必要があります。
* `GEMINI_API_KEY`: Google Gemini APIを利用するためのAPIキー
* `GCP_PROJECT`: （※必要に応じて）Google CloudのプロジェクトID

## 環境構築と動かし方 (ローカルでの実行)

1. リポジトリをクローンします。
```bash
git clone https://github.com/hohho401s-cmyk/genai-legalsearch-app.git
cd genai-legalsearch-app.git
```

2. 必要なライブラリをインストールします。
```bash
pip install -r requirements.txt
```

3. 環境変数を設定し、メインプログラムを起動します。（以下はLinux/Macの例）
```bash
export GEMINI_API_KEY="あなたのAPIキー"
python api_main.py
```
※FastAPIやFlask等を使用している場合は、指定の起動コマンド（`uvicorn`など）を使用してください。

## デプロイについて
本リポジトリには `Dockerfile` および `Procfile` が含まれており、Google Cloud Runなどのコンテナベースのサーバーレス環境へシームレスにデプロイすることが可能です。
デプロイ前に、ソースコード内のプロジェクトID等の環境依存情報がダミー化されているか確認してください。

## 注意事項
* 本APIは、e-Govおよび裁判所の公開データを利用しています。各サイトの利用規約およびスクレイピングの節度を守ってご利用ください。
* 生成されるレポートはAIによる推論を含んでおり、実際の法的アドバイスを代替するものではありません。
