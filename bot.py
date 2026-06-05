"""
X 引用ポスト自動化ボット（GitHub Actions版）
- フォロー中アカウントをXから動的取得
- Nitter RSSで新着ポストを検知
- ツイートURLをコンポーズに直接入力して引用投稿
- 15分ごとに実行（随時対応）
"""
import json, os, re, random, time, feedparser
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

MY_USERNAME = "HamaichiChannel"

NITTER_INSTANCES = ["nitter.net", "nitter.poast.org", "nitter.privacydev.net", "lightbrd.com"]

MAX_QUOTES_PER_RUN = 5      # 1回の実行で最大5件引用
MAX_PER_ACCOUNT   = 1       # アカウントあたり最大1件
SEEN_FILE         = "last_seen.json"
FOLLOWING_FILE    = "following.json"

# 野球関連キーワード（これを1つ以上含む投稿のみ引用）
BASEBALL_KEYWORDS = [
    # ─── 基本 ───
    "野球", "プロ野球", "ベースボール", "baseball", "Baseball", "⚾",

    # ─── NPBチーム（正式・略称・英語） ───
    "マリーンズ", "千葉ロッテ", "ロッテ",
    "読売", "巨人", "ジャイアンツ",
    "阪神", "タイガース",
    "ソフトバンク", "ホークス",
    "オリックス", "バファローズ",
    "西武", "ライオンズ",
    "楽天", "イーグルス",
    "日本ハム", "ファイターズ",
    "DeNA", "ベイスターズ",
    "中日", "ドラゴンズ",
    "広島", "カープ",
    "ヤクルト", "スワローズ",
    "埼玉西武", "北海道日本ハム", "東北楽天", "福岡ソフトバンク",
    "横浜DeNA", "東京ヤクルト",

    # ─── リーグ・機構 ───
    "パ・リーグ", "パリーグ", "セ・リーグ", "セリーグ",
    "NPB", "日本野球機構", "PacificLeague", "CentralLeague",

    # ─── MLB球団 ───
    "MLB", "メジャー", "大リーグ",
    "ドジャース", "Dodgers",
    "ヤンキース", "Yankees",
    "エンジェルス", "Angels",
    "カブス", "Cubs",
    "レッドソックス", "Red Sox",
    "メッツ", "Mets",
    "パドレス", "Padres",
    "マリナーズ", "Mariners",
    "レイズ", "Rays",
    "ブルージェイズ", "Blue Jays",
    "アストロズ", "Astros",
    "ブレーブス", "Braves",

    # ─── 日本人MLB選手 ───
    "大谷翔平", "大谷",
    "ダルビッシュ", "ダルビッシュ有",
    "山本由伸", "山本",
    "鈴木誠也",
    "今永昇太", "今永",
    "吉田正尚", "吉田",
    "菊池雄星",
    "千賀滉大", "千賀",
    "藤浪晋太郎", "藤浪",
    "前田健太", "前田",

    # ─── NPB主要選手（ロッテ中心＋有名選手） ───
    "佐々木朗希", "朗希",
    "吉井", "種市", "小島", "石川歩",
    "安田尚憲", "安田", "中村奨吾", "荻野",
    "ポランコ", "ソト",

    # ─── プレー・記録 ───
    "ホームラン", "本塁打", "HR", "アーチ",
    "ヒット", "安打", "長打", "二塁打", "三塁打",
    "三振", "奪三振", "K", "空振り",
    "四球", "死球", "フォアボール",
    "盗塁", "タイムリー", "犠飛", "スクイズ",
    "満塁", "サヨナラ", "逆転", "同点",
    "先制", "追加点", "ダメ押し",
    "完封", "完投", "QS", "クオリティスタート",
    "ノーヒット", "ノーノー", "パーフェクト",
    "防御率", "ERA", "打率", "OPS", "WAR",
    "奪三振率", "WHIP", "勝率",

    # ─── 投手関連 ───
    "投球", "登板", "先発", "中継ぎ", "リリーフ", "抑え", "クローザー",
    "セーブ", "ホールド", "勝利投手", "敗戦投手",
    "直球", "ストレート", "変化球", "スライダー", "カーブ",
    "フォーク", "チェンジアップ", "カットボール", "ツーシーム",
    "球速", "最速", "160km", "150km",

    # ─── 試合・結果 ───
    "勝利", "勝ち", "負け", "敗戦", "引き分け",
    "連勝", "連敗", "連続", "首位", "最下位", "順位",
    "貯金", "借金", "マジック", "優勝", "Ｖ", "優勝争い",
    "プレーオフ", "CS", "クライマックス", "日本シリーズ",
    "胴上げ", "優勝決定",

    # ─── ポジション ───
    "投手", "捕手", "一塁手", "二塁手", "三塁手", "遊撃手",
    "外野手", "内野手", "指名打者", "DH",
    "バッテリー", "二遊間",

    # ─── 大会・イベント ───
    "オールスター", "ドラフト", "トレード", "FA", "海外FA",
    "キャンプ", "春季", "秋季", "オープン戦", "交流戦",
    "甲子園", "高校野球", "センバツ", "選手権",
    "WBC", "プレミア12", "侍ジャパン", "代表",
    "U-18", "U-23",

    # ─── スタジアム ───
    "ZOZOマリン", "ペイペイドーム", "バンテリンドーム",
    "マツダスタジアム", "神宮", "東京ドーム", "甲子園",
    "横浜スタジアム", "ハマスタ", "ベルーナドーム",
    "楽天モバイル", "エスコンフィールド",

    # ─── 放送・メディア ───
    "DAZN", "スポナビ", "スポーツナビ",
    "Tver", "AbemaTV", "テレ東野球",
    "中継", "実況", "解説", "ハイライト",

    # ─── その他野球用語 ───
    "スタメン", "ベンチ", "一軍", "二軍", "ファーム",
    "昇格", "降格", "抹消", "登録",
    "球場", "マウンド", "ブルペン", "ダグアウト",
    "応援", "チャンステーマ", "ヒッティングマーチ",
    "始球式", "試合前", "試合後",
]

def is_baseball_related(text):
    """野球関連キーワードが含まれているか判定"""
    return any(kw in text for kw in BASEBALL_KEYWORDS)

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

# ──────────────────────────────────────────
# フォロー一覧の取得・キャッシュ
# ──────────────────────────────────────────
def load_following():
    if os.path.exists(FOLLOWING_FILE):
        with open(FOLLOWING_FILE) as f:
            return json.load(f)
    return []

def save_following(accounts):
    with open(FOLLOWING_FILE, "w") as f:
        json.dump(accounts, f)

def fetch_following_list(page):
    """Xのフォロー中ページをスクレイピングしてアカウント一覧を返す"""
    print(f"フォロー一覧を取得中...")
    page.goto(f"https://x.com/{MY_USERNAME}/following", wait_until="domcontentloaded")
    time.sleep(4)

    accounts = set()
    for scroll_attempt in range(20):  # 最大20回スクロール（約200アカウント対応）
        handles = page.evaluate("""() => {
            const cells = document.querySelectorAll('[data-testid="UserCell"]');
            const result = [];
            for (const cell of cells) {
                // UserCellの最初のaタグのhrefからハンドルを取得
                const links = cell.querySelectorAll('a[href]');
                for (const link of links) {
                    const href = link.getAttribute('href');
                    if (href && /^\\/[A-Za-z0-9_]{1,50}$/.test(href)) {
                        result.push(href.slice(1));
                        break;
                    }
                }
            }
            return result;
        }""")
        prev = len(accounts)
        for h in handles:
            accounts.add(h)

        # スクロールして次を読み込む
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

        if len(accounts) == prev and scroll_attempt > 2:
            break  # 増えなくなったら終了

    # 自分自身・システムアカウントを除外
    skip = {MY_USERNAME.lower(), "home", "explore", "notifications", "messages",
            "search", "settings", "i", "compose"}
    result = [h for h in accounts if h.lower() not in skip]
    print(f"フォロー一覧取得完了: {len(result)} アカウント")
    return result

# ──────────────────────────────────────────
# Nitter RSS から新着ポスト取得
# ──────────────────────────────────────────
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

def fetch_new_posts(account, last_seen_id):
    for instance in NITTER_INSTANCES:
        try:
            feed = feedparser.parse(f"https://{instance}/{account}/rss", request_headers={"User-Agent": "Mozilla/5.0"})
            if not feed.entries:
                continue
            new = []
            for e in feed.entries:
                tid = extract_tweet_id(e.link)
                if not tid:
                    continue
                if tid == last_seen_id:
                    break
                text = re.sub(r"<[^>]+>", "", e.get("summary", e.get("title", "")))
                # 返信・RTはスキップ
                if text.lstrip().startswith("@") or text.lstrip().startswith("RT @"):
                    continue
                # 野球関連でなければスキップ
                if not is_baseball_related(text):
                    print(f"  [{account}] 野球無関係スキップ: {text[:40]!r}")
                    continue
                new.append((tid, text))
            if new or feed.entries:  # フィードが取れたなら成功
                return new
        except Exception as ex:
            print(f"  [{account}] {instance} 失敗: {ex}")
    return []

# ──────────────────────────────────────────
# 引用投稿
# ──────────────────────────────────────────
def quote_tweet(page, account, tweet_id, comment):
    tweet_url = f"https://x.com/{account}/status/{tweet_id}"
    post_text = f"{comment}\n{tweet_url}"

    page.goto("https://x.com/home", wait_until="domcontentloaded")
    time.sleep(3)

    # コンポーズエリアを開く
    compose = None
    try:
        compose = page.locator('[data-testid="tweetTextarea_0"]').first
        compose.wait_for(state="visible", timeout=8000)
        compose.click()
        time.sleep(1)
    except PWTimeoutError:
        try:
            page.locator('[data-testid="SideNav_NewTweet_Button"]').first.click(timeout=5000)
            time.sleep(2)
            compose = page.locator('[data-testid="tweetTextarea_0"]').first
            compose.wait_for(state="visible", timeout=8000)
        except PWTimeoutError:
            print(f"  コンポーズが開けません: {tweet_id}")
            page.screenshot(path=f"debug_err_{tweet_id}.png")
            return False

    # テキスト入力
    try:
        compose.fill(post_text)
        time.sleep(1)
    except Exception as e:
        print(f"  テキスト入力失敗: {e}")
        return False

    # 投稿ボタンクリック
    posted = False
    for sel in ['[data-testid="tweetButtonInline"]', '[data-testid="tweetButton"]']:
        try:
            btn = page.locator(sel).first
            btn.wait_for(state="visible", timeout=4000)
            btn.click()
            posted = True
            break
        except Exception:
            pass
    if not posted:
        try:
            r = page.evaluate("""() => {
                for (const s of ['[data-testid="tweetButtonInline"]','[data-testid="tweetButton"]']) {
                    const b = document.querySelector(s);
                    if (b) { b.click(); return s; }
                }
                return null;
            }""")
            if r:
                posted = True
        except Exception:
            pass

    if not posted:
        print(f"  投稿ボタンなし: {tweet_id}")
        page.screenshot(path=f"debug_err_{tweet_id}.png")
        return False

    time.sleep(3)
    print(f"  引用完了: @{account} / {tweet_id} / {comment}")
    return True

# ──────────────────────────────────────────
# メイン
# ──────────────────────────────────────────
def main():
    # CookieをSecretから読み込み（BOM除去）
    cookies_json = os.environ.get("X_COOKIES", "[]").lstrip('﻿').strip()
    cookies = json.loads(cookies_json)

    seen = load_seen()
    targets = []

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
        if "home" not in page.url:
            print("ログイン失敗。処理中止。")
            browser.close()
            return

        # フォロー一覧を取得（キャッシュ済みがあれば併用、毎回更新）
        following = fetch_following_list(page)
        if not following:
            following = load_following()  # フォールバック
        if following:
            save_following(following)
        else:
            print("フォロー一覧取得失敗")
            browser.close()
            return

        # 各アカウントの新着ポストをチェック（Nitter RSS）
        for account in following:
            new_posts = fetch_new_posts(account, seen.get(account))
            if not new_posts:
                continue
            # 最新IDを記録
            seen[account] = new_posts[0][0]
            for tid, txt in new_posts[:MAX_PER_ACCOUNT]:
                targets.append((account, tid, txt))
                if len(targets) >= MAX_QUOTES_PER_RUN:
                    break
            if len(targets) >= MAX_QUOTES_PER_RUN:
                break

        save_seen(seen)

        if not targets:
            print("引用するポストなし")
            browser.close()
            return

        # 引用投稿実行
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
