"""
X 引用ポスト自動化ボット（GitHub Actions版）
- Nitter RSSで新着ツイートを検知
- Playwrightのheadless ChromeでXに引用ポスト
- CookieはGitHub Secretsから読み込み
- ツイートURLをコンポーズに直接入力して引用投稿
"""
import json, os, re, random, logging, time, feedparser
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# 監視対象アカウント
ACCOUNTS = ["MLBJapan", "chibalotte_pr", "DAZNJPNBaseball", "PacificleagueTV"]

NITTER_INSTANCES = ["nitter.poast.org", "nitter.privacydev.net", "lightbrd.com", "nitter.net"]
MAX_QUOTES_PER_ACCOUNT = 2
SEEN_FILE = "last_seen.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# キーワード → ハッシュタグ
KEYWORD_COMMENTS = [
    (["勝", "勝利", "サヨナラ", "逆転", "完封", "連勝"],
     ["#プロ野球 #マリーンズ #千葉ロッテ", "#プロ野球 #千葉ロッテ #マリーンズ"]),
    (["本塁打", "ホームラン", "HR", "満塁", "打点", "安打", "タイムリー"],
     ["#プロ野球 #マリーンズ #千葉ロッテ", "#千葉ロッテ #マリーンズ #プロ野球"]),
    (["三振", "奪三振", "セーブ", "ホールド", "登板", "先発"],
     ["#プロ野球 #マリーンズ #千葉ロッテ", "#マリーンズ #千葉ロッテ #プロ野球"]),
    (["MLB", "大リーグ", "メジャー", "大谷", "ダルビッシュ"],
     ["#MLB #プロ野球 #マリーンズ", "#MLB #マリーンズ #プロ野球"]),
    (["パ・リーグ", "パリーグ", "順位", "首位"],
     ["#パリーグ #プロ野球 #マリーンズ", "#プロ野球 #パリーグ #千葉ロッテ"]),
]
DEFAULT_COMMENTS = [
    "#プロ野球 #マリーンズ #千葉ロッテ",
    "#千葉ロッテ #マリーンズ #プロ野球",
    "#マリーンズ #千葉ロッテ #プロ野球",
]

def generate_comment(text):
    for keywords, comments in KEYWORD_COMMENTS:
        if any(kw in text for kw in keywords):
            return random.choice(comments)
    return random.choice(DEFAULT_COMMENTS)

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return json.load(f)
    return {}

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f)

def extract_tweet_id(url):
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else None

def fetch_new_tweets(account, last_seen_id):
    for instance in NITTER_INSTANCES:
        try:
            feed = feedparser.parse(f"https://{instance}/{account}/rss")
            if not feed.entries:
                continue
            new = []
            for e in feed.entries:
                tid = extract_tweet_id(e.link)
                if not tid or tid == last_seen_id:
                    break
                text = re.sub(r"<[^>]+>", "", e.get("summary", e.get("title", "")))
                # 返信（@から始まる）やリツイート（RT @）はスキップ
                if text.lstrip().startswith("@") or text.lstrip().startswith("RT @"):
                    continue
                new.append((tid, text))
            print(f"[{account}] {instance} から {len(new)} 件取得")
            return new
        except Exception as ex:
            print(f"[{account}] {instance} 失敗: {ex}")
    return []

def quote_tweet(page, account, tweet_id, comment):
    """
    ツイートURLをコンポーズボックスに入力して引用投稿する。
    ドロップダウン操作不要 = 確実に動作する。
    """
    tweet_url = f"https://x.com/{account}/status/{tweet_id}"
    post_text = f"{comment}\n{tweet_url}"

    # ホームに戻ってコンポーズエリアをクリック
    page.goto("https://x.com/home", wait_until="domcontentloaded")
    time.sleep(3)

    try:
        # コンポーズエリア（ポストボタン or テキストエリア）
        compose = page.locator('[data-testid="tweetTextarea_0"]').first
        compose.wait_for(state="visible", timeout=10000)
        compose.click()
        time.sleep(1)
    except PWTimeoutError:
        # フォールバック: 「ポスト」ボタンからコンポーズ画面を開く
        try:
            page.locator('[data-testid="SideNav_NewTweet_Button"]').first.click(timeout=5000)
            time.sleep(2)
            compose = page.locator('[data-testid="tweetTextarea_0"]').first
            compose.wait_for(state="visible", timeout=8000)
        except PWTimeoutError:
            print(f"  コンポーズエリアが開けません: {tweet_id}")
            page.screenshot(path=f"debug_nocompose_{tweet_id}.png")
            return False

    # テキスト入力（ハッシュタグ + ツイートURL）
    try:
        compose.fill(post_text)
        time.sleep(1)
        page.screenshot(path=f"debug_{tweet_id}.png")
    except Exception as e:
        print(f"  テキスト入力失敗: {e}")
        return False

    # 投稿ボタンをクリック
    try:
        post_btn = page.locator('[data-testid="tweetButton"]').first
        post_btn.wait_for(state="visible", timeout=5000)
        post_btn.click()
        time.sleep(3)
        print(f"  引用完了: {tweet_id} / {comment}")
        return True
    except PWTimeoutError:
        print(f"  投稿ボタンなし: {tweet_id}")
        page.screenshot(path=f"debug_nopost_{tweet_id}.png")
        return False

def main():
    seen = load_seen()
    targets = []
    for account in ACCOUNTS:
        new_tweets = fetch_new_tweets(account, seen.get(account))
        if not new_tweets:
            print(f"[{account}] 新規なし")
            continue
        seen[account] = new_tweets[0][0]
        for tid, txt in new_tweets[:MAX_QUOTES_PER_ACCOUNT]:
            targets.append((account, tid, txt))
    save_seen(seen)

    if not targets:
        print("引用するツイートなし")
        return

    # CookieをSecretから読み込み（BOM除去）
    cookies_json = os.environ.get("X_COOKIES", "[]").lstrip('﻿').strip()
    cookies = json.loads(cookies_json)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        )
        context.add_cookies(cookies)
        page = context.new_page()

        # ログイン確認
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        time.sleep(3)
        print(f"現在のURL: {page.url}")

        total = 0
        for account, tid, txt in targets:
            print(f"[{account}] 引用中: {tid}")
            if quote_tweet(page, account, tid, generate_comment(txt)):
                total += 1
            time.sleep(5)

        browser.close()
    print(f"完了: {total} 件引用")

if __name__ == "__main__":
    main()
