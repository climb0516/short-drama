# Created by 青云 on 2026/10/20.
"""DramaPulse 数据抓取：短剧行业新闻 / AI 对短剧行业的影响 / ReelShort 海外热播。只用标准库。"""
import html, json, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data.json"
CST = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
KEEP_DAYS = 45          # 新闻保留天数（与历史数据合并后裁剪）
MAX_PER_SECTION = 240

# ── 搜索词 ───────────────────────────────────────────────
ZH = dict(hl="zh-CN", gl="CN", ceid="CN:zh-Hans")
EN = dict(hl="en-US", gl="US", ceid="US:en")
QUERIES = [
    # 行业
    ("短剧 when:14d", ZH), ("微短剧 when:14d", ZH), ("短剧 平台 when:14d", ZH),
    ("短剧 出海 when:14d", ZH), ("红果短剧 when:14d", ZH), ("短剧 监管 OR 广电总局 when:30d", ZH),
    ("microdrama OR micro-drama when:14d", EN), ("\"vertical drama\" OR \"short drama\" app when:14d", EN),
    ("ReelShort OR DramaBox when:14d", EN),
    # AI 影响
    ("AI短剧 when:30d", ZH), ("AI漫剧 when:30d", ZH), ("AIGC 短剧 when:30d", ZH),
    ("AI 短剧 演员 OR 编剧 OR 从业者 when:30d", ZH), ("AI 短剧 成本 OR 降本 OR 效率 when:30d", ZH),
    ("AI 短剧 版权 OR 侵权 OR 换脸 when:30d", ZH), ("AI 短剧 冲击 OR 取代 OR 失业 when:30d", ZH),
    ("AI microdrama OR \"AI-generated\" vertical drama when:30d", EN),
    ("generative AI microdrama actors OR jobs OR cost when:30d", EN),
]

# ── 词表 ────────────────────────────────────────────────
DRAMA_KW = ["短剧", "微短剧", "漫剧", "竖屏剧", "小程序剧", "红果", "reelshort", "dramabox", "shortmax",
            "goodshort", "flextv", "microdrama", "micro-drama", "micro drama", "vertical drama",
            "short drama", "short-form drama", "vertical series", "minidrama", "mini-drama"]
AI_KW = ["ai", "aigc", "人工智能", "大模型", "生成式", "数字人", "虚拟人", "sora", "可灵", "即梦", "seedance",
         "veo", "换脸", "deepfake", "generative", "智能体", "agent", "算法生成", "ai生成", "ai-generated"]
IMPACT_KW = ["冲击", "影响", "取代", "替代", "代替", "失业", "饭碗", "岗位", "从业者", "演员", "编剧", "剪辑",
             "降本", "成本", "效率", "提效", "产能", "工业化", "门槛", "版权", "侵权", "授权", "换脸", "肖像",
             "监管", "规范", "整治", "下架", "同质化", "泡沫", "亏损", "赚钱", "盈利", "红利", "机遇", "挑战",
             "风险", "争议", "困境", "隐忧", "焦虑", "变革", "颠覆", "重塑", "洗牌", "变局", "抢人", "转型",
             "出海", "翻译", "配音", "彩票", "真香", "保护", "值得", "灾", "未来",
             "jobs", "job", "replace", "actor", "actors", "writer", "writers", "cost", "cheap", "copyright",
             "impact", "disrupt", "reshap", "transform", "upend", "layoff", "threat", "union", "sag-aftra", "lawsuit", "backlash", "future"]
POS_KW = ["降本", "增效", "提效", "效率", "产能", "机遇", "红利", "赋能", "助力", "突破", "新岗位", "降低门槛",
          "门槛降低", "门槛低", "翻译", "配音", "增长", "繁荣", "新机会", "新业态", "点亮", "多快好省", "真香",
          "爆火", "爆款", "破圈", "蓝海", "普惠", "创新", "释放", "加速", "开辟", "扶持", "有奔头", "拥抱",
          "扩容", "规模化", "盈利", "成本降至", "成本砍", "砍掉", "压到", "降至", "省钱",
          "boost", "opportunity", "cheaper", "growth", "faster", "democratiz", "unlock", "boom"]
NEG_KW = ["冲击", "取代", "替代", "代替", "失业", "饭碗", "侵权", "之争", "争议", "换脸", "泡沫", "亏损",
          "不再赚钱", "同质化", "粗制滥造", "劣质", "低质", "整治", "下架", "风险", "隐忧", "焦虑", "困境",
          "危机", "灾", "抵制", "压价", "裁员", "降薪", "失守", "乱象", "滥用", "保护", "警惕", "割韭菜",
          "烧心", "牛马", "截胡", "难赚钱", "困局", "盗脸", "搬运", "转行", "没戏拍", "跑量", "零收入", "内卷",
          "deepfake", "threat", "replace", "layoff", "lawsuit", "backlash", "slop", "job losses", "strike",
          "concern", "fear", "worry"]

# 行业新闻细分标签
TOPICS = [
    ("policy", ["监管", "广电", "总局", "政策", "规范", "备案", "整治", "下架", "审核", "标准", "regulat"]),
    ("overseas", ["出海", "海外", "reelshort", "dramabox", "shortmax", "goodshort", "tiktok", "美国", "东南亚",
                  "overseas", "global", "us market", "hollywood"]),
    ("data", ["财报", "营收", "收入", "用户", "日活", "月活", "规模", "数据", "报告", "榜", "周报", "播放量",
              "亿元", "revenue", "downloads", "billion", "million", "report"]),
    ("capital", ["融资", "投资", "收购", "上市", "ipo", "股价", "并购", "funding", "raises", "acquir", "valuation"]),
    ("platform", ["红果", "抖音", "快手", "腾讯", "爱奇艺", "优酷", "芒果", "番茄", "字节", "平台", "app"]),
]


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def clean(text, n=220):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n] + ("…" if len(text) > n else "")


def has(text, words):
    t = text.lower()
    hits = []
    for w in words:
        # 英文短词按词边界匹配，避免 "ai" 命中 "said"
        if re.fullmatch(r"[a-z\-]{1,4}", w):
            if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t):
                hits.append(w)
        elif w in t:
            hits.append(w)
    return hits


# ── Google News RSS ─────────────────────────────────────
def google_news(query, region):
    params = dict(q=query, **region)
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    root = ET.fromstring(fetch(url))
    items = []
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
        except Exception:
            continue
        items.append({
            "title": html.unescape(title).strip(),
            "url": it.findtext("link") or "",
            "source": source,
            "source_url": src_el.get("url", "") if src_el is not None else "",
            "time": ts.isoformat(),
            "lang": "zh" if region is ZH else "en",
        })
    return items


# 英文 SEO 内容农场标题（剧集测评/剧情/在哪看）
JUNK_RE = re.compile(r"\b(reviews?|plot|cast|recap|ending|explained|full episodes?|watch|free|worth|"
                     r"cost per episode|how much|where to|coins?|season \d|episode \d)\b", re.I)

JUNK_SOURCES_EN = {"白鲸出海"}  # 其英文站是剧集 SEO 页
# 英文条目必须带行业语义，过滤只有剧名的标题
EN_NEWS_KW = ["industry", "market", "app", "apps", "platform", "studio", "studios", "startup", "company",
              "hollywood", "investor", "investors", "revenue", "billion", "million", "users", "downloads",
              "deal", "launch", "launches", "boom", "rise", "growth", "streaming", "streamer", "netflix",
              "tiktok", "youtube", "china", "chinese", "format", "audience", "business", "funding", "raises",
              "acquire", "acquires", "trend", "craze", "genre", "producers", "creators", "series", "bet"]


def classify(item):
    text = item["title"]
    if not has(text, DRAMA_KW):
        return None
    if item.get("lang") == "en" and (item.get("source") in JUNK_SOURCES_EN or JUNK_RE.search(text)
                                     or not has(text, EN_NEWS_KW + AI_KW)):
        return None
    ai_hits = has(text, AI_KW)
    impact_hits = has(text, IMPACT_KW)
    if ai_hits and impact_hits:
        pos, neg = has(text, POS_KW), has(text, NEG_KW)
        item["section"] = "ai"
        item["sentiment"] = "positive" if len(pos) > len(neg) else "negative" if len(neg) > len(pos) else "neutral"
        item["signals"] = sorted(set(pos + neg))[:4]
    else:
        item["section"] = "industry"
        item["topic"] = next((k for k, kws in TOPICS if has(text, kws)), "general")
        item["ai_related"] = bool(ai_hits)
    return item


# ── 去重 ────────────────────────────────────────────────
def norm(t):
    return re.sub(r"[\s\W_]+", "", t.lower())


def bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similar(a, b):
    a, b = bigrams(norm(a)), bigrams(norm(b))
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) > 0.72


def dedupe(items):
    out = []
    for it in sorted(items, key=lambda x: x["time"], reverse=True):
        dup = next((o for o in out if similar(o["title"], it["title"])), None)
        if dup:
            dup.setdefault("also", [])
            if it["source"] and it["source"] != dup["source"] and it["source"] not in dup["also"]:
                dup["also"].append(it["source"])
            continue
        out.append(it)
    return out


# ── ReelShort 海外热播 ──────────────────────────────────
def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def reelshort(limit=12):
    page = fetch("https://www.reelshort.com/")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    info = json.loads(m.group(1))["props"]["pageProps"]["fallback"]["/api/ms/hall/webInfo"]
    shelves = {s.get("bookshelf_name", ""): s.get("books", []) for s in info["bookShelfList"]}
    out = []
    for shelf in ("TOP", "New Release"):
        for b in shelves.get(shelf, [])[:limit]:
            out.append({
                "title": b["book_title"],
                "cover": b.get("book_pic", ""),
                "synopsis": clean(b.get("special_desc", ""), 200),
                "episodes": b.get("chapter_count"),
                "views": b.get("read_count", 0),
                "likes": b.get("collect_count", 0),
                "tags": [t["tag_name"] for t in b.get("theme_list", [])][:4],
                "url": f"https://www.reelshort.com/episodes/episode-1-{slugify(b['book_title'])}-"
                       f"{b['book_id']}-{b.get('chapter_id', '')}?play_time=1",
                "shelf": "top" if shelf == "TOP" else "new",
            })
    return out


def main():
    old = {}
    if DATA_FILE.exists():
        try:
            old = json.loads(DATA_FILE.read_text("utf-8"))
        except Exception:
            old = {}

    status = []
    raw = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [(q, ex.submit(google_news, q, r)) for q, r in QUERIES]
        rs_future = ex.submit(reelshort)
        for q, f in futures:
            try:
                got = f.result()
                raw.extend(got)
                status.append({"name": q, "ok": True, "count": len(got)})
            except Exception as e:
                status.append({"name": q, "ok": False, "error": str(e)[:120]})
        try:
            overseas = rs_future.result()
            status.append({"name": "ReelShort", "ok": True, "count": len(overseas)})
        except Exception as e:
            overseas = old.get("overseas", [])
            status.append({"name": "ReelShort", "ok": False, "error": str(e)[:120], "stale": True})

    # 与历史合并，避免新闻随搜索窗口滑动而消失
    history = old.get("industry", []) + old.get("ai", [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    merged = [it for it in (classify(x) for x in raw) if it] + history
    merged = [it for it in merged if datetime.fromisoformat(it["time"]) >= cutoff]
    # 同一条新闻以本次分类结果为准（词表可能更新），按 URL 去重
    seen, uniq = set(), []
    for it in merged:
        it = classify({k: v for k, v in it.items() if k not in ("section", "sentiment", "signals", "topic", "ai_related", "also")})
        if it and it["url"] not in seen:
            seen.add(it["url"])
            uniq.append(it)
    items = dedupe(uniq)

    data = {
        "updated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "industry": [i for i in items if i["section"] == "industry"][:MAX_PER_SECTION],
        "ai": [i for i in items if i["section"] == "ai"][:MAX_PER_SECTION],
        "overseas": overseas,
        "status": status,
    }
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    s = {k: len(data[k]) for k in ("industry", "ai", "overseas")}
    senti = {k: sum(1 for i in data["ai"] if i["sentiment"] == k) for k in ("positive", "negative", "neutral")}
    print(f"done {s} sentiment={senti} failed={[x['name'] for x in status if not x['ok']]}")


if __name__ == "__main__":
    main()
