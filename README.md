# YouTube Live Chat (Python)

YouTubeのライブチャットをAPIキーなしで取得し、SQLiteに保存します。GUIランチャー付き。

## セットアップ
```bash
pip install -r requirements.txt
```

## CLIで取得
```bash
python youtube_chat.py <videoId|channelId|@handle> [--store-dir DIR] [--print]
# 例:
python youtube_chat.py @NintendoJP --print
python youtube_chat.py dQw4w9WgXcQ --store-dir data
```
- `--print` で取得中にコンソールへ表示。
- DBは `comments.db` が `--store-dir` またはカレントに作成。

## GUIランチャー
- `gui_live_chat.pyw` をダブルクリックで起動（Windows）。
- 上段に動画ID/チャンネルID/`@handle` を入力、Start で開始、Stop で停止。
- 「Print comments to console」はデフォルトON（コンソール付きで起動時に表示）。外すと抑止。
- 保存先ディレクトリを指定しない場合はカレントに `comments.db`。

## DB確認
Pythonスクリプトで表示:
```bash
python view_comments.py [--store-dir DIR] [--limit 50] [--json]
```
- `--json` でJSON出力、デフォルトは簡易行表示。

sqlite3で直接:
```bash
sqlite3 comments.db "SELECT timestamp, author, text, kind, amount_text FROM comments ORDER BY timestamp_ms DESC LIMIT 20;"
```

## モジュール概要
- `youtube_chat.py` : ライブチャット取得ロジック（スクレイピングで apiKey / continuation 抽出、`get_live_chat` ループ、保存）。
- `chat_store.py`   : SQLite保存/取得ヘルパー。スキーマはJS版と同等 (`parts_json`, `colors_json` 列あり)。
- `gui_live_chat.pyw`: Tkinter GUIランチャー。
- `view_comments.py`: 取得済みコメントの閲覧用ツール。

## 注意
- YouTubeの仕様変更で動かなくなる可能性があります。
- 連続リクエストになるので、自分の責任で利用してください。***
