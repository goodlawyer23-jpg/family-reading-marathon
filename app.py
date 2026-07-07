import os
import re
import html
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import streamlit.components.v1 as components

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def scroll_to_anchor(anchor_id: str) -> None:
    components.html(
        f"""
        <script>
        const target = window.parent.document.getElementById("{anchor_id}");
        if (target) {{
            target.scrollIntoView({{behavior: "smooth", block: "start"}});
        }}
        </script>
        """,
        height=0,
    )

APP_TITLE = "우리가족 독서마라톤"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SAMPLE_DIR = BASE_DIR / "sample_data"

CSV_COLUMNS = {
    "books": [
        "book_id", "reader_member_id", "title", "author", "publisher", "isbn", "image_url",
        "description", "pubdate", "total_pages", "source_api", "created_at",
    ],
    "family_members": [
        "member_id", "name", "role", "age_group", "weight", "avatar", "created_at",
    ],
    "reading_logs": [
        "log_id", "member_id", "book_id", "reading_date", "pages_read", "weighted_pages",
        "start_page", "end_page", "memo", "created_at",
    ],
    "quotes": [
        "quote_id", "member_id", "book_id", "page_number", "quote_text", "comment", "created_at",
    ],
    "reviews": [
        "review_id", "member_id", "book_id", "rating", "one_line_review", "full_review",
        "finished_date", "created_at",
    ],
    "settings": ["marathon_name", "start_date", "end_date", "family_target_pages", "unit_name"],
}

CSV_PATHS = {
    "books": DATA_DIR / "books.csv",
    "family_members": DATA_DIR / "family_members.csv",
    "reading_logs": DATA_DIR / "reading_logs.csv",
    "quotes": DATA_DIR / "quotes.csv",
    "reviews": DATA_DIR / "reviews.csv",
    "settings": DATA_DIR / "settings.csv",
}

DEFAULT_SETTINGS = {
    "marathon_name": "2026년 7월 우리가족 독서마라톤",
    "start_date": "2026-07-01",
    "end_date": "2026-07-31",
    "family_target_pages": 2000,
    "unit_name": "페이지",
}

PLACEHOLDER_COVER = "https://placehold.co/160x220?text=BOOK"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def ensure_directories() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    SAMPLE_DIR.mkdir(exist_ok=True)


def ensure_csv_files() -> None:
    ensure_directories()
    for key, path in CSV_PATHS.items():
        if not path.exists():
            if key == "settings":
                pd.DataFrame([DEFAULT_SETTINGS], columns=CSV_COLUMNS[key]).to_csv(path, index=False, encoding="utf-8-sig")
            else:
                pd.DataFrame(columns=CSV_COLUMNS[key]).to_csv(path, index=False, encoding="utf-8-sig")


def read_csv(key: str) -> pd.DataFrame:
    path = CSV_PATHS[key]
    if not path.exists():
        ensure_csv_files()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="utf-8")
    except pd.errors.EmptyDataError:
        df = pd.DataFrame(columns=CSV_COLUMNS[key])
    for col in CSV_COLUMNS[key]:
        if col not in df.columns:
            df[col] = ""
    return df[CSV_COLUMNS[key]]


def write_csv(key: str, df: pd.DataFrame) -> None:
    for col in CSV_COLUMNS[key]:
        if col not in df.columns:
            df[col] = ""
    df[CSV_COLUMNS[key]].to_csv(CSV_PATHS[key], index=False, encoding="utf-8-sig")


def load_all_data() -> dict:
    ensure_csv_files()
    return {key: read_csv(key) for key in CSV_COLUMNS.keys()}


def safe_int(value, default: int = 0) -> int:
    try:
        if pd.isna(value) or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value) or value == "":
            return default
        return float(value)
    except Exception:
        return default


def get_settings(settings_df: pd.DataFrame) -> dict:
    if settings_df.empty:
        return DEFAULT_SETTINGS.copy()
    row = settings_df.iloc[0].to_dict()
    row["family_target_pages"] = safe_int(row.get("family_target_pages"), DEFAULT_SETTINGS["family_target_pages"])
    return {**DEFAULT_SETTINGS, **row}


def get_member_name(member_id: str, members_df: pd.DataFrame) -> str:
    found = members_df[members_df["member_id"] == member_id]
    if found.empty:
        return "알 수 없음"
    row = found.iloc[0]
    return f"{row.get('avatar', '')} {row.get('name', '')}".strip()


def get_book_title(book_id: str, books_df: pd.DataFrame) -> str:
    found = books_df[books_df["book_id"] == book_id]
    if found.empty:
        return "알 수 없는 책"
    return str(found.iloc[0].get("title", "알 수 없는 책"))


def enrich_logs(logs_df: pd.DataFrame, members_df: pd.DataFrame, books_df: pd.DataFrame) -> pd.DataFrame:
    if logs_df.empty:
        return logs_df.copy()
    df = logs_df.copy()
    df["pages_read"] = df["pages_read"].apply(safe_int)
    df["weighted_pages"] = df["weighted_pages"].apply(safe_float)
    df["member_name"] = df["member_id"].apply(lambda x: get_member_name(x, members_df))
    df["book_title"] = df["book_id"].apply(lambda x: get_book_title(x, books_df))
    df["reading_date_dt"] = pd.to_datetime(df["reading_date"], errors="coerce")
    return df


def member_options(members_df: pd.DataFrame) -> dict:
    return {f"{row.avatar} {row.name} ({row.role})": row.member_id for row in members_df.itertuples()}


def book_options(books_df: pd.DataFrame) -> dict:
    return {f"{row.title} - {row.author}": row.book_id for row in books_df.itertuples()}


def create_sample_data() -> None:
    today = date(2026, 7, 6)
    members = pd.DataFrame([
        {"member_id": "member_dad", "name": "아빠", "role": "기록왕", "age_group": "성인", "weight": 1.0, "avatar": "👨", "created_at": now_str()},
        {"member_id": "member_mom", "name": "엄마", "role": "응원단장", "age_group": "성인", "weight": 1.0, "avatar": "👩", "created_at": now_str()},
        {"member_id": "member_child1", "name": "첫째", "role": "모험가", "age_group": "초등", "weight": 1.2, "avatar": "🧒", "created_at": now_str()},
        {"member_id": "member_child2", "name": "둘째", "role": "그림책 러너", "age_group": "유아", "weight": 1.5, "avatar": "👧", "created_at": now_str()},
    ], columns=CSV_COLUMNS["family_members"])

    books = pd.DataFrame([
        {"book_id": "book_001", "reader_member_id": "member_mom", "title": "긴긴밤", "author": "루리", "publisher": "문학동네", "isbn": "9788954677158", "image_url": PLACEHOLDER_COVER, "description": "서로 다른 존재들이 함께 길을 걷는 이야기", "pubdate": "2021-02-03", "total_pages": 144, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_002", "reader_member_id": "member_dad", "title": "불편한 편의점", "author": "김호연", "publisher": "나무옆의자", "isbn": "9791161571188", "image_url": PLACEHOLDER_COVER, "description": "동네 편의점에서 만나는 따뜻한 사람들의 이야기", "pubdate": "2021-04-20", "total_pages": 268, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_003", "reader_member_id": "member_dad", "title": "아몬드", "author": "손원평", "publisher": "창비", "isbn": "9788936434267", "image_url": PLACEHOLDER_COVER, "description": "감정을 느끼기 어려운 소년의 성장 이야기", "pubdate": "2017-03-31", "total_pages": 264, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_004", "reader_member_id": "member_child2", "title": "수박 수영장", "author": "안녕달", "publisher": "창비", "isbn": "9788936446819", "image_url": PLACEHOLDER_COVER, "description": "여름날 수박 속에서 펼쳐지는 상상 그림책", "pubdate": "2015-07-30", "total_pages": 52, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_005", "reader_member_id": "member_child2", "title": "강아지똥", "author": "권정생", "publisher": "길벗어린이", "isbn": "9788986621135", "image_url": PLACEHOLDER_COVER, "description": "작고 낮은 존재의 소중함을 알려주는 그림책", "pubdate": "1996-04-01", "total_pages": 36, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_006", "reader_member_id": "member_child1", "title": "해리 포터와 마법사의 돌", "author": "J.K. 롤링", "publisher": "문학수첩", "isbn": "9788983927620", "image_url": PLACEHOLDER_COVER, "description": "마법 학교에서 시작되는 모험", "pubdate": "2019-11-19", "total_pages": 268, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_007", "reader_member_id": "member_child2", "title": "채소 학교와 쌍둥이 딸기", "author": "나카야 미와", "publisher": "웅진주니어", "isbn": "9788901253541", "image_url": PLACEHOLDER_COVER, "description": "채소 친구들이 등장하는 귀여운 그림책", "pubdate": "2021-06-30", "total_pages": 40, "source_api": "sample", "created_at": now_str()},
    ], columns=CSV_COLUMNS["books"])

    logs_raw = [
        ("member_dad", "book_002", 0, 35, 1, 35, "출근길에 읽음"),
        ("member_mom", "book_001", 0, 28, 1, 28, "아이들과 이야기하기 좋은 책"),
        ("member_child1", "book_006", 1, 24, 1, 24, "마법 학교가 재미있다"),
        ("member_child2", "book_004", 1, 18, 1, 18, "수박 수영장 또 읽고 싶음"),
        ("member_dad", "book_003", 2, 30, 1, 30, "인물의 감정이 인상적"),
        ("member_mom", "book_002", 2, 32, 36, 67, "잠들기 전에 읽음"),
        ("member_child1", "book_006", 3, 26, 25, 50, "해그리드 등장"),
        ("member_child2", "book_005", 3, 20, 1, 20, "작은 것도 소중하다"),
        ("member_dad", "book_002", 4, 40, 68, 107, "편의점 사람들이 따뜻하다"),
        ("member_mom", "book_001", 4, 36, 29, 64, "코뿔소 이야기가 좋음"),
        ("member_child1", "book_006", 5, 34, 51, 84, "마법 지팡이 장면"),
        ("member_child2", "book_007", 5, 15, 1, 15, "딸기 친구들이 귀엽다"),
        ("member_dad", "book_003", 6, 45, 31, 75, "주말 독서"),
        ("member_mom", "book_002", 6, 42, 108, 149, "다음 장이 궁금함"),
    ]
    member_weight = {row.member_id: safe_float(row.weight, 1.0) for row in members.itertuples()}
    logs = []
    for idx, (member_id, book_id, days_ago, pages, start_page, end_page, memo) in enumerate(logs_raw, start=1):
        logs.append({
            "log_id": f"log_{idx:03d}",
            "member_id": member_id,
            "book_id": book_id,
            "reading_date": (today - timedelta(days=days_ago)).isoformat(),
            "pages_read": pages,
            "weighted_pages": round(pages * member_weight[member_id], 1),
            "start_page": start_page,
            "end_page": end_page,
            "memo": memo,
            "created_at": now_str(),
        })
    logs_df = pd.DataFrame(logs, columns=CSV_COLUMNS["reading_logs"])

    quotes = pd.DataFrame([
        {"quote_id": "quote_001", "member_id": "member_mom", "book_id": "book_001", "page_number": 42, "quote_text": "함께 걸으면 멀리 갈 수 있어.", "comment": "우리 가족 마라톤이랑 닮았다.", "created_at": now_str()},
        {"quote_id": "quote_002", "member_id": "member_child1", "book_id": "book_006", "page_number": 31, "quote_text": "새로운 문이 열리는 느낌이야.", "comment": "나도 마법 학교에 가고 싶다.", "created_at": now_str()},
        {"quote_id": "quote_003", "member_id": "member_dad", "book_id": "book_003", "page_number": 68, "quote_text": "마음을 이해하는 일은 천천히 배워도 된다.", "comment": "아이들과 이야기해 보고 싶은 문장.", "created_at": now_str()},
    ], columns=CSV_COLUMNS["quotes"])

    reviews = pd.DataFrame([
        {"review_id": "review_001", "member_id": "member_child2", "book_id": "book_004", "rating": 5, "one_line_review": "수박 속에서 수영하는 상상이 제일 재미있다.", "full_review": "그림이 시원해서 여름에 또 보고 싶다.", "finished_date": "2026-07-06", "created_at": now_str()},
        {"review_id": "review_002", "member_id": "member_mom", "book_id": "book_001", "rating": 5, "one_line_review": "천천히 오래 남는 이야기.", "full_review": "가족이 함께 읽고 이야기하기 좋다.", "finished_date": "", "created_at": now_str()},
        {"review_id": "review_003", "member_id": "member_dad", "book_id": "book_002", "rating": 4, "one_line_review": "사람 냄새 나는 따뜻한 소설.", "full_review": "짧게 읽기 좋아서 독서마라톤 첫 책으로 좋다.", "finished_date": "", "created_at": now_str()},
    ], columns=CSV_COLUMNS["reviews"])

    settings = pd.DataFrame([{**DEFAULT_SETTINGS}], columns=CSV_COLUMNS["settings"])

    write_csv("family_members", members)
    write_csv("books", books)
    write_csv("reading_logs", logs_df)
    write_csv("quotes", quotes)
    write_csv("reviews", reviews)
    write_csv("settings", settings)
    books.to_csv(SAMPLE_DIR / "sample_books.csv", index=False, encoding="utf-8-sig")


def search_books_sample(query: str, display: int = 50, search_mode: str = "title") -> list[dict]:
    """API가 없거나 실패했을 때 사용하는 샘플 검색입니다."""
    query = str(query or "").strip().lower()
    display = max(1, min(int(display or 50), 50))
    sample_path = SAMPLE_DIR / "sample_books.csv"
    if sample_path.exists():
        sample_df = pd.read_csv(sample_path, encoding="utf-8-sig")
    else:
        current_books = read_csv("books")
        sample_df = current_books if not current_books.empty else pd.DataFrame(columns=CSV_COLUMNS["books"])

    if sample_df.empty:
        return []

    if not query:
        result_df = sample_df.head(display)
    elif search_mode == "isbn":
        clean_query = normalize_isbn_for_search(query)
        isbn_text = sample_df.get("isbn", "").astype(str).map(normalize_isbn_for_search)
        result_df = sample_df[isbn_text.str.contains(clean_query, na=False)].head(display)
    else:
        text = (
            sample_df.get("title", "").astype(str) + " "
            + sample_df.get("author", "").astype(str) + " "
            + sample_df.get("publisher", "").astype(str) + " "
            + sample_df.get("description", "").astype(str)
        ).str.lower()
        result_df = sample_df[text.str.contains(query, na=False)].head(display)
    return result_df.to_dict("records")


def search_books_naver(
    query: str,
    client_id: str | None = None,
    client_secret: str | None = None,
    display: int = 50,
    search_mode: str = "title",
) -> list[dict]:
    """네이버 책 검색 API를 호출합니다. 실패 시 빈 리스트를 반환해 샘플 검색으로 fallback합니다."""
    client_id = client_id or os.getenv("NAVER_CLIENT_ID")
    client_secret = client_secret or os.getenv("NAVER_CLIENT_SECRET")
    query = str(query or "").strip()
    display = max(1, min(int(display or 50), 50))
    if not query or not client_id or not client_secret:
        return []

    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}

    if search_mode == "isbn":
        # 네이버 상세 검색은 ISBN 조건을 d_isbn 파라미터로 받습니다.
        # 하이픈이 포함되어 있어도 검색되도록 숫자/X만 남깁니다.
        url = "https://openapi.naver.com/v1/search/book_adv.json"
        clean_isbn = normalize_isbn_for_search(query)
        params = {"d_isbn": clean_isbn, "display": display, "sort": "sim"}
    else:
        url = "https://openapi.naver.com/v1/search/book.json"
        params = {"query": query, "display": display, "sort": "sim"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        items = response.json().get("items", [])
        results = []
        for item in items:
            results.append({
                "book_id": make_id("book"),
                "reader_member_id": "",
                "title": clean_html(item.get("title", "")),
                "author": clean_html(item.get("author", "")),
                "publisher": clean_html(item.get("publisher", "")),
                "isbn": item.get("isbn", ""),
                "image_url": item.get("image", "") or PLACEHOLDER_COVER,
                "description": clean_html(item.get("description", "")),
                "pubdate": normalize_pubdate(item.get("pubdate", "")),
                "total_pages": 0,
                "source_api": "naver",
                "created_at": now_str(),
            })
        return results
    except Exception:
        return []


def clean_html(text: str) -> str:
    text = html.unescape(str(text or ""))
    text = re.sub(r"<\/?b>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def normalize_pubdate(pubdate: str) -> str:
    pubdate = str(pubdate or "").strip()
    if len(pubdate) == 8 and pubdate.isdigit():
        return f"{pubdate[:4]}-{pubdate[4:6]}-{pubdate[6:]}"
    return pubdate


def normalize_isbn_for_search(isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", str(isbn or "")).upper()


def isbn_tokens(isbn: str) -> set[str]:
    tokens = set()
    for part in re.split(r"[\s,;/|]+", str(isbn or "")):
        token = normalize_isbn_for_search(part)
        if token:
            tokens.add(token)
    joined = normalize_isbn_for_search(isbn)
    if joined:
        tokens.add(joined)
    return tokens


def same_book_mask(books_df: pd.DataFrame, book_data: dict) -> pd.Series:
    if books_df.empty:
        return pd.Series(dtype=bool)

    new_tokens = isbn_tokens(book_data.get("isbn", ""))
    title = clean_html(book_data.get("title", "")).strip().lower()
    author = clean_html(book_data.get("author", "")).strip().lower()

    matches = []
    for _, row in books_df.iterrows():
        row_tokens = isbn_tokens(row.get("isbn", ""))
        isbn_match = bool(new_tokens and row_tokens and new_tokens.intersection(row_tokens))
        row_title = clean_html(row.get("title", "")).strip().lower()
        row_author = clean_html(row.get("author", "")).strip().lower()
        title_match = bool(title and row_title == title and (not author or not row_author or row_author == author))
        matches.append(isbn_match or title_match)
    return pd.Series(matches, index=books_df.index)


def get_naver_credentials() -> tuple[str, str]:
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    try:
        client_id = client_id or st.secrets.get("NAVER_CLIENT_ID", "")
        client_secret = client_secret or st.secrets.get("NAVER_CLIENT_SECRET", "")
    except Exception:
        pass
    return str(client_id).strip(), str(client_secret).strip()


def fetch_book_pages_by_isbn(isbn: str) -> int:
    # 2차 개발에서 국립중앙도서관 ISBN API 등을 연결할 자리입니다.
    return 0


def add_book_to_library(book_data: dict, reader_member_id: str = "") -> tuple[bool, str]:
    """책장에 책을 추가합니다. 같은 책+같은 구성원 조합은 중복 등록하지 않습니다."""
    books_df = read_csv("books")
    title = clean_html(book_data.get("title", "")).strip()
    reader_member_id = str(reader_member_id or "").strip()

    duplicate_book_mask = same_book_mask(books_df, book_data)
    if len(duplicate_book_mask) == len(books_df) and duplicate_book_mask.any():
        same_reader_mask = books_df.get("reader_member_id", pd.Series([""] * len(books_df))).astype(str).str.strip() == reader_member_id
        same_book_same_reader = books_df[duplicate_book_mask & same_reader_mask]
        if not same_book_same_reader.empty:
            return False, f"이미 이 구성원의 책장에 《{title or '이 책'}》이 있습니다."

        no_reader_mask = books_df.get("reader_member_id", pd.Series([""] * len(books_df))).astype(str).str.strip() == ""
        no_reader_rows = books_df[duplicate_book_mask & no_reader_mask]
        if reader_member_id and not no_reader_rows.empty:
            idx = no_reader_rows.index[0]
            books_df.loc[idx, "reader_member_id"] = reader_member_id
            write_csv("books", books_df)
            return True, f"기존 책장 항목에 읽는 사람을 연결했습니다."

    row = {col: book_data.get(col, "") for col in CSV_COLUMNS["books"]}
    row["book_id"] = make_id("book")
    row["reader_member_id"] = reader_member_id or row.get("reader_member_id", "")
    row["title"] = title
    row["author"] = clean_html(row.get("author", ""))
    row["publisher"] = clean_html(row.get("publisher", ""))
    row["description"] = clean_html(row.get("description", ""))
    row["pubdate"] = normalize_pubdate(row.get("pubdate", ""))
    row["image_url"] = row.get("image_url") or PLACEHOLDER_COVER
    row["total_pages"] = safe_int(row.get("total_pages"), 0)
    row["source_api"] = row.get("source_api") or "manual"
    row["created_at"] = now_str()
    books_df = pd.concat([books_df, pd.DataFrame([row])], ignore_index=True)
    write_csv("books", books_df)
    return True, "가족 책장에 추가했습니다."


def calculate_summary(data: dict) -> dict:
    books_df = data["books"]
    members_df = data["family_members"]
    logs_df = enrich_logs(data["reading_logs"], members_df, books_df)
    settings = get_settings(data["settings"])
    target = safe_int(settings.get("family_target_pages"), 0)
    total_weighted = float(logs_df["weighted_pages"].sum()) if not logs_df.empty else 0.0
    progress = min((total_weighted / target * 100), 100) if target > 0 else 0
    remain = max(target - total_weighted, 0)
    return {
        "settings": settings,
        "logs": logs_df,
        "total_weighted": total_weighted,
        "progress": progress,
        "remain": remain,
    }


def get_member_stats(logs_df: pd.DataFrame, members_df: pd.DataFrame) -> pd.DataFrame:
    if members_df.empty:
        return pd.DataFrame(columns=["member_id", "member_name", "pages_read", "weighted_pages", "record_days"])
    if logs_df.empty:
        stats = members_df[["member_id", "name", "avatar"]].copy()
        stats["member_name"] = stats["avatar"].astype(str) + " " + stats["name"].astype(str)
        stats["pages_read"] = 0
        stats["weighted_pages"] = 0.0
        stats["record_days"] = 0
        return stats[["member_id", "member_name", "pages_read", "weighted_pages", "record_days"]]
    grouped = logs_df.groupby("member_id").agg(
        pages_read=("pages_read", "sum"),
        weighted_pages=("weighted_pages", "sum"),
        record_days=("reading_date", pd.Series.nunique),
    ).reset_index()
    members = members_df.copy()
    members["member_name"] = members["avatar"].astype(str) + " " + members["name"].astype(str)
    stats = members[["member_id", "member_name"]].merge(grouped, on="member_id", how="left").fillna(0)
    stats["pages_read"] = stats["pages_read"].astype(int)
    stats["weighted_pages"] = stats["weighted_pages"].astype(float).round(1)
    stats["record_days"] = stats["record_days"].astype(int)
    return stats.sort_values("weighted_pages", ascending=False)


def get_book_progress(book_id: str, books_df: pd.DataFrame, logs_df: pd.DataFrame) -> tuple[int, int, float]:
    book = books_df[books_df["book_id"] == book_id]
    total_pages = safe_int(book.iloc[0]["total_pages"], 0) if not book.empty else 0
    pages_sum = safe_int(logs_df[logs_df["book_id"] == book_id]["pages_read"].sum(), 0) if not logs_df.empty else 0
    progress = min(pages_sum / total_pages * 100, 100) if total_pages > 0 else 0
    return pages_sum, total_pages, progress


def render_metric_cards(summary: dict) -> None:
    settings = summary["settings"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("가족 목표", f"{safe_int(settings['family_target_pages']):,} {settings['unit_name']}")
    col2.metric("누적 기록", f"{summary['total_weighted']:,.1f} {settings['unit_name']}")
    col3.metric("진행률", f"{summary['progress']:.1f}%")
    col4.metric("남은 거리", f"{summary['remain']:,.1f} {settings['unit_name']}")
    st.progress(min(summary["progress"] / 100, 1.0), text=f"가족 독서마라톤 진행률 {summary['progress']:.1f}%")


def page_dashboard(data: dict) -> None:
    st.title("🏃‍♀️ 우리가족 독서마라톤")
    st.caption("책을 읽은 만큼 가족 마라톤 트랙이 앞으로 나아갑니다.")

    summary = calculate_summary(data)
    settings = summary["settings"]
    st.info(f"{settings['marathon_name']} · {settings['start_date']} ~ {settings['end_date']}")
    render_metric_cards(summary)

    if st.button("🎁 샘플 데이터 생성 / 초기화", type="primary"):
        create_sample_data()
        st.success("샘플 데이터가 생성되었습니다. 왼쪽 메뉴나 새로고침으로 화면을 확인해주세요.")
        st.rerun()

    st.subheader("👟 구성원별 누적 페이지")
    member_stats_df = get_member_stats(summary["logs"], data["family_members"])
    if member_stats_df.empty:
        st.warning("아직 가족 구성원이 없습니다. 샘플 데이터를 생성하거나 구성원을 CSV에 추가해주세요.")
    else:
        chart_df = member_stats_df.rename(columns={"member_name": "구성원", "weighted_pages": "가중치 반영 페이지"})
        fig = px.bar(chart_df, x="구성원", y="가중치 반영 페이지", text="가중치 반영 페이지")
        fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)

        rank_df = member_stats_df.copy()
        rank_df.insert(0, "순위", range(1, len(rank_df) + 1))
        st.dataframe(
            rank_df.rename(columns={
                "member_name": "구성원", "pages_read": "실제 읽은 페이지", "weighted_pages": "가중치 반영 페이지", "record_days": "기록일 수",
            })[["순위", "구성원", "실제 읽은 페이지", "가중치 반영 페이지", "기록일 수"]],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("🕒 최근 기록 피드")
    logs_df = summary["logs"]
    if logs_df.empty:
        st.write("아직 독서 기록이 없습니다.")
    else:
        recent = logs_df.sort_values(["reading_date_dt", "created_at"], ascending=False).head(8)
        for row in recent.itertuples():
            st.markdown(f"- **{row.reading_date}** · {row.member_name}님이 《{row.book_title}》을 **{row.pages_read}쪽** 읽었습니다. _{row.memo}_")


def page_book_search(data: dict) -> None:
    st.title("🔎 책 검색 / 책 등록")
    st.caption(".env 또는 Streamlit Secrets에 네이버 API 키가 있으면 네이버 책 검색을 먼저 사용하고, 실패하면 샘플 검색으로 자동 전환합니다.")

    members_df = data["family_members"]
    if members_df.empty:
        st.warning("책을 책장에 추가하려면 읽을 가족 구성원이 필요합니다. 먼저 샘플 데이터를 생성하거나 가족 구성원을 추가해주세요.")
        return

    m_options = member_options(members_df)
    client_id, client_secret = get_naver_credentials()
    api_ready = bool(client_id and client_secret)
    st.info("네이버 책 검색 API: 사용 가능" if api_ready else "네이버 API 키가 없어 샘플 책 검색으로 작동합니다.")
    feedback = st.session_state.pop("book_add_feedback", None)
    if feedback:
        level, text = feedback
        if level == "success":
            st.success(text)
        else:
            st.warning(text)

    tab1, tab2 = st.tabs(["네이버/샘플 검색", "직접 등록"])
    with tab1:
        st.markdown("#### 1단계. 검색 방식을 선택하세요")
        search_mode_label = st.radio("검색 방식", ["책 제목 검색", "ISBN 검색"], horizontal=True)
        display_count = 50
        st.caption("검색 결과는 최대 50개까지 가져오고, 화면에는 10개씩 나누어 보여줍니다.")

        search_mode = "isbn" if search_mode_label == "ISBN 검색" else "title"
        placeholder = "예: 978-8954677158" if search_mode == "isbn" else "예: 긴긴밤, 해리 포터"
        label = "ISBN 입력" if search_mode == "isbn" else "책 제목 또는 저자 검색"
        query = st.text_input(label, placeholder=placeholder)

        st.markdown("#### 2단계. 이 책을 읽을 가족 구성원을 선택하세요")
        st.caption("검색 결과에서 책장에 추가하면, 아래에서 선택한 가족 구성원의 책장에 바로 연결됩니다.")
        selected_reader_label = st.selectbox("읽을 가족 구성원", list(m_options.keys()), key="search_reader")
        selected_reader_id = m_options[selected_reader_label]

        if st.button("검색하기", type="primary"):
            naver_results = []
            search_source = "sample"
            normalized_query = normalize_isbn_for_search(query) if search_mode == "isbn" else query

            if api_ready:
                naver_results = search_books_naver(
                    normalized_query,
                    client_id,
                    client_secret,
                    display=int(display_count),
                    search_mode=search_mode,
                )
                if naver_results:
                    search_source = "naver"

            if naver_results:
                results = naver_results
                message = f"네이버 책 검색 결과 {len(results)}건을 찾았습니다."
            else:
                results = search_books_sample(normalized_query, display=int(display_count), search_mode=search_mode)
                message = "네이버 검색 결과가 없거나 API 호출에 실패해 샘플 검색 결과를 표시합니다." if api_ready else "샘플 검색 결과를 표시합니다."

            st.session_state["book_search_results"] = results
            st.session_state["book_search_source"] = search_source
            st.session_state["book_search_message"] = message
            st.session_state["book_search_mode"] = search_mode
            st.session_state["book_search_display"] = int(display_count)
            st.session_state["book_search_page"] = 1

        results = st.session_state.get("book_search_results", [])
        if st.session_state.get("book_search_message"):
            st.caption(st.session_state["book_search_message"])

        if not results:
            st.write("검색어를 입력하고 검색해주세요. 샘플 데이터가 없으면 홈에서 샘플 데이터 생성 버튼을 먼저 눌러주세요.")
        else:
            st.markdown('<div id="book-search-results-top"></div>', unsafe_allow_html=True)
            st.markdown("#### 3단계. 원하는 책을 선택해 책장에 추가하세요")
            if st.session_state.pop("scroll_to_book_results", False):
                scroll_to_anchor("book-search-results-top")
            st.caption(f"현재 선택된 읽는 사람: **{selected_reader_label}**")

            page_size = 10
            result_count = len(results)
            search_page_count = max(1, (result_count + page_size - 1) // page_size)
            current_page = int(st.session_state.get("book_search_page", 1))
            current_page = max(1, min(current_page, search_page_count))
            st.session_state["book_search_page"] = current_page

            if search_page_count > 1:
                st.caption(f"현재 {current_page}페이지 / 총 {search_page_count}페이지")

            start_idx = (int(current_page) - 1) * page_size
            end_idx = start_idx + page_size
            visible_results = results[start_idx:end_idx]
            st.caption(f"총 {result_count}건 중 {start_idx + 1}~{min(end_idx, result_count)}번째 결과를 표시합니다.")

            for local_idx, book in enumerate(visible_results):
                global_idx = start_idx + local_idx
                with st.container(border=True):
                    cols = st.columns([1, 4])
                    with cols[0]:
                        cover_url = book.get("image_url") or PLACEHOLDER_COVER
                        st.image(cover_url, width=100)
                    with cols[1]:
                        title = clean_html(book.get("title", "제목 없음"))
                        author = clean_html(book.get("author", ""))
                        publisher = clean_html(book.get("publisher", ""))
                        description = clean_html(book.get("description", ""))
                        pubdate = normalize_pubdate(book.get("pubdate", ""))
                        st.markdown(f"### {title}")
                        st.write(f"저자: {author or '-'} · 출판사: {publisher or '-'}")
                        st.write(f"ISBN: {book.get('isbn', '-') or '-'} · 출간일: {pubdate or '-'}")
                        st.write(f"전체 페이지: {safe_int(book.get('total_pages'), 0) or '미입력'}")
                        if description:
                            st.caption(description)
                        if st.button(f"{selected_reader_label}의 책장에 추가", key=f"add_search_{global_idx}_{selected_reader_id}"):
                            book_to_add = dict(book)
                            book_to_add.update({
                                "title": title,
                                "author": author,
                                "publisher": publisher,
                                "description": description,
                                "pubdate": pubdate,
                            })
                            success, msg = add_book_to_library(book_to_add, selected_reader_id)
                            if success:
                                st.session_state["book_add_feedback"] = ("success", f"《{title}》을 {selected_reader_label}의 책장에 추가했습니다.")
                            else:
                                st.session_state["book_add_feedback"] = ("warning", msg)
                            st.rerun()

            if search_page_count > 1:
                st.divider()
                st.caption(f"다른 검색 결과를 더 보려면 페이지 번호를 눌러주세요. 현재 {current_page}페이지 / 총 {search_page_count}페이지")
                page_cols = st.columns(search_page_count)
                for page_num, page_col in enumerate(page_cols, start=1):
                    with page_col:
                        label = f"✅ {page_num}" if page_num == current_page else str(page_num)
                        if st.button(label, key=f"book_page_btn_{page_num}", use_container_width=True):
                            st.session_state["book_search_page"] = page_num
                            st.session_state["scroll_to_book_results"] = True
                            st.rerun()

    with tab2:
        st.caption("직접 등록할 때도 읽을 가족 구성원을 함께 선택합니다. 저장 즉시 가족 책장에 읽는 사람이 표시됩니다.")
        with st.form("manual_book_form"):
            reader_label = st.selectbox("이 책을 읽을 사람", list(m_options.keys()), key="manual_reader")
            title = st.text_input("제목 *")
            author = st.text_input("저자")
            publisher = st.text_input("출판사")
            isbn = st.text_input("ISBN")
            image_url = st.text_input("표지 URL", value=PLACEHOLDER_COVER)
            description = st.text_area("책 소개")
            pubdate = st.text_input("출간일", placeholder="YYYY-MM-DD 또는 YYYYMMDD")
            total_pages = st.number_input("전체 페이지 수", min_value=0, step=1, value=100)
            submitted = st.form_submit_button("직접 등록")
        if submitted:
            if not title.strip():
                st.error("제목은 필수입니다.")
            else:
                success, msg = add_book_to_library({
                    "book_id": make_id("book"), "title": title, "author": author, "publisher": publisher,
                    "isbn": isbn, "image_url": image_url, "description": description, "pubdate": pubdate,
                    "total_pages": total_pages, "source_api": "manual", "created_at": now_str(),
                }, m_options[reader_label])
                if success:
                    st.session_state["book_add_feedback"] = ("success", f"《{clean_html(title)}》을 {reader_label}의 책장에 추가했습니다.")
                    st.rerun()
                else:
                    st.warning(msg)


def page_library(data: dict) -> None:
    st.title("📚 가족 책장")
    st.caption("책을 추가할 때 선택한 읽는 사람이 바로 표시됩니다. 독서 기록을 아직 입력하지 않아도 가족별 책장을 확인할 수 있습니다.")
    books_df = data["books"]
    logs_df = enrich_logs(data["reading_logs"], data["family_members"], books_df)
    reviews_df = data["reviews"]
    members_df = data["family_members"]

    if books_df.empty:
        st.warning("책장이 비어 있습니다. 샘플 데이터를 생성하거나 책을 등록해주세요.")
        return

    for i in range(0, len(books_df), 2):
        cols = st.columns(2)
        for col, (_, book) in zip(cols, books_df.iloc[i:i+2].iterrows()):
            with col:
                with st.container(border=True):
                    top_cols = st.columns([1, 2.2])
                    with top_cols[0]:
                        cover_url = str(book.get("image_url", "") or PLACEHOLDER_COVER).strip()
                        if not cover_url:
                            cover_url = PLACEHOLDER_COVER
                        st.image(cover_url, use_container_width=True)
                    with top_cols[1]:
                        title = clean_html(book.get("title", "제목 없음")) or "제목 없음"
                        author = clean_html(book.get("author", "")) or "저자 미상"
                        publisher = clean_html(book.get("publisher", "")) or "출판사 미상"
                        st.markdown(f"### {title}")
                        st.caption(f"{author} · {publisher}")

                        pages_sum, total_pages, progress = get_book_progress(book["book_id"], books_df, logs_df)
                        reader_id = str(book.get("reader_member_id", "")).strip()
                        registered_reader = get_member_name(reader_id, members_df) if reader_id else ""
                        log_readers = logs_df[logs_df["book_id"] == book["book_id"]]["member_name"].dropna().unique().tolist() if not logs_df.empty else []
                        readers = [registered_reader] if registered_reader else log_readers
                        finished = not reviews_df[(reviews_df["book_id"] == book["book_id"]) & (reviews_df["finished_date"].astype(str).str.len() > 0)].empty if not reviews_df.empty else False

                        st.markdown(f"**읽는 사람**  \n{', '.join(readers) if readers else '아직 없음'}")
                        st.markdown(f"**상태**  \n{'✅ 완독' if finished else '📖 읽는 중'}")
                        isbn = str(book.get("isbn", "") or "").strip()
                        if isbn:
                            st.caption(f"ISBN: {isbn}")

                    if total_pages > 0:
                        st.progress(min(progress / 100, 1.0), text=f"{pages_sum}/{total_pages}쪽 · {progress:.1f}%")
                    else:
                        st.progress(0, text=f"{pages_sum}쪽 기록 · 전체 페이지 미입력")


def page_reading_log(data: dict) -> None:
    st.title("✍️ 독서 기록 입력")
    members_df = data["family_members"]
    books_df = data["books"]
    if members_df.empty or books_df.empty:
        st.warning("가족 구성원과 책이 필요합니다. 먼저 샘플 데이터를 생성하거나 책을 등록해주세요.")
        return
    m_options = member_options(members_df)
    b_options = book_options(books_df)
    with st.form("reading_log_form"):
        member_label = st.selectbox("가족 구성원", list(m_options.keys()))
        book_label = st.selectbox("책", list(b_options.keys()))
        reading_date = st.date_input("날짜", value=date.today())
        pages_read = st.number_input("읽은 페이지 수", min_value=1, step=1, value=10)
        col1, col2 = st.columns(2)
        start_page = col1.number_input("시작 페이지", min_value=0, step=1, value=0)
        end_page = col2.number_input("끝 페이지", min_value=0, step=1, value=0)
        memo = st.text_area("메모", placeholder="예: 자기 전에 20분 읽음")
        submitted = st.form_submit_button("독서 기록 저장")
    if submitted:
        member_id = m_options[member_label]
        book_id = b_options[book_label]
        member_row = members_df[members_df["member_id"] == member_id].iloc[0]
        weight = safe_float(member_row["weight"], 1.0)
        row = {
            "log_id": make_id("log"), "member_id": member_id, "book_id": book_id,
            "reading_date": reading_date.isoformat(), "pages_read": pages_read,
            "weighted_pages": round(pages_read * weight, 1), "start_page": start_page,
            "end_page": end_page, "memo": memo, "created_at": now_str(),
        }
        logs_df = pd.concat([data["reading_logs"], pd.DataFrame([row])], ignore_index=True)
        write_csv("reading_logs", logs_df)
        st.success(f"저장했습니다. 가중치 반영 페이지는 {row['weighted_pages']}쪽입니다.")
        st.rerun()

    delete_feedback = st.session_state.pop("reading_log_delete_feedback", None)
    if delete_feedback:
        st.success(delete_feedback)

    st.subheader("최근 입력 기록")
    logs_df = enrich_logs(read_csv("reading_logs"), members_df, books_df)
    if logs_df.empty:
        st.write("아직 입력된 독서 기록이 없습니다.")
    else:
        view = logs_df.sort_values("created_at", ascending=False).head(10)
        for row in view.itertuples():
            with st.container(border=True):
                cols = st.columns([2, 2, 3, 1, 1])
                with cols[0]:
                    st.markdown(f"**{row.reading_date}**")
                    st.caption(row.member_name)
                with cols[1]:
                    st.markdown(f"**{row.book_title}**")
                    st.caption(f"{safe_int(row.pages_read)}쪽 · 가중 {safe_float(row.weighted_pages):.1f}쪽")
                with cols[2]:
                    memo_text = str(row.memo or "").strip()
                    st.write(memo_text if memo_text else "메모 없음")
                with cols[3]:
                    if safe_int(row.start_page, 0) or safe_int(row.end_page, 0):
                        st.caption(f"{safe_int(row.start_page, 0)}~{safe_int(row.end_page, 0)}쪽")
                    else:
                        st.caption("페이지 범위 없음")
                with cols[4]:
                    pending_delete_id = st.session_state.get("pending_delete_log_id")
                    if pending_delete_id == str(row.log_id):
                        st.warning("정말 이 독서 기록을 삭제할까요?")
                        confirm_col, cancel_col = st.columns(2)
                        with confirm_col:
                            if st.button("삭제 확인", key=f"confirm_delete_log_{row.log_id}"):
                                original_logs = read_csv("reading_logs")
                                updated_logs = original_logs[original_logs["log_id"].astype(str) != str(row.log_id)].copy()
                                write_csv("reading_logs", updated_logs)
                                st.session_state.pop("pending_delete_log_id", None)
                                st.session_state["reading_log_delete_feedback"] = "독서 기록을 삭제했습니다. 대시보드와 리포트는 삭제된 기록을 기준으로 다시 계산됩니다."
                                st.rerun()
                        with cancel_col:
                            if st.button("취소", key=f"cancel_delete_log_{row.log_id}"):
                                st.session_state.pop("pending_delete_log_id", None)
                                st.rerun()
                    else:
                        if st.button("삭제", key=f"delete_log_{row.log_id}"):
                            st.session_state["pending_delete_log_id"] = str(row.log_id)
                            st.rerun()


def page_quotes(data: dict) -> None:
    st.title("💬 좋았던 문장")
    members_df = data["family_members"]
    books_df = data["books"]
    if members_df.empty or books_df.empty:
        st.warning("가족 구성원과 책이 필요합니다.")
        return
    m_options = member_options(members_df)
    b_options = book_options(books_df)
    with st.form("quote_form"):
        member_label = st.selectbox("가족 구성원", list(m_options.keys()))
        book_label = st.selectbox("책", list(b_options.keys()))
        page_number = st.number_input("페이지 번호", min_value=0, step=1, value=1)
        quote_text = st.text_area("좋았던 문장 *")
        comment = st.text_area("내 생각")
        submitted = st.form_submit_button("문장 저장")
    if submitted:
        if not quote_text.strip():
            st.error("좋았던 문장을 입력해주세요.")
        else:
            row = {
                "quote_id": make_id("quote"), "member_id": m_options[member_label], "book_id": b_options[book_label],
                "page_number": page_number, "quote_text": quote_text, "comment": comment, "created_at": now_str(),
            }
            quotes_df = pd.concat([data["quotes"], pd.DataFrame([row])], ignore_index=True)
            write_csv("quotes", quotes_df)
            st.success("문장을 저장했습니다.")
            st.rerun()

    st.subheader("저장된 문장")
    quotes_df = read_csv("quotes")
    if quotes_df.empty:
        st.write("아직 저장된 문장이 없습니다.")
    else:
        for row in quotes_df.sort_values("created_at", ascending=False).itertuples():
            with st.container(border=True):
                st.markdown(f"> {row.quote_text}")
                st.caption(f"{get_member_name(row.member_id, members_df)} · 《{get_book_title(row.book_id, books_df)}》 · p.{row.page_number}")
                if row.comment:
                    st.write(row.comment)


def page_reviews(data: dict) -> None:
    st.title("⭐ 한 줄 감상")
    members_df = data["family_members"]
    books_df = data["books"]
    if members_df.empty or books_df.empty:
        st.warning("가족 구성원과 책이 필요합니다.")
        return
    m_options = member_options(members_df)
    b_options = book_options(books_df)
    with st.form("review_form"):
        member_label = st.selectbox("가족 구성원", list(m_options.keys()))
        book_label = st.selectbox("책", list(b_options.keys()))
        rating = st.slider("별점", 1, 5, 5)
        one_line_review = st.text_input("한 줄 감상 *")
        full_review = st.text_area("자세한 감상", placeholder="선택 입력")
        finished_date = st.date_input("완독일", value=date.today())
        submitted = st.form_submit_button("감상 저장")
    if submitted:
        if not one_line_review.strip():
            st.error("한 줄 감상을 입력해주세요.")
        else:
            row = {
                "review_id": make_id("review"), "member_id": m_options[member_label], "book_id": b_options[book_label],
                "rating": rating, "one_line_review": one_line_review, "full_review": full_review,
                "finished_date": finished_date.isoformat(), "created_at": now_str(),
            }
            reviews_df = pd.concat([data["reviews"], pd.DataFrame([row])], ignore_index=True)
            write_csv("reviews", reviews_df)
            st.success("감상을 저장했습니다.")
            st.rerun()

    st.subheader("감상 목록")
    reviews_df = read_csv("reviews")
    if reviews_df.empty:
        st.write("아직 저장된 감상이 없습니다.")
    else:
        for row in reviews_df.sort_values("created_at", ascending=False).itertuples():
            with st.container(border=True):
                st.markdown(f"#### {'⭐' * safe_int(row.rating, 0)} 《{get_book_title(row.book_id, books_df)}》")
                st.write(row.one_line_review)
                if row.full_review:
                    st.caption(row.full_review)
                st.caption(f"{get_member_name(row.member_id, members_df)} · 완독일 {row.finished_date}")


def page_monthly_report(data: dict) -> None:
    st.title("📊 월간 리포트")
    summary = calculate_summary(data)
    settings = summary["settings"]
    logs_df = summary["logs"]
    members_df = data["family_members"]
    books_df = data["books"]
    reviews_df = data["reviews"]
    quotes_df = data["quotes"]

    report_month = st.date_input("리포트 기준 월", value=date(2026, 7, 1))
    month_start = pd.Timestamp(report_month.replace(day=1))
    next_month = (month_start + pd.offsets.MonthBegin(1))

    if logs_df.empty:
        month_logs = logs_df
    else:
        month_logs = logs_df[(logs_df["reading_date_dt"] >= month_start) & (logs_df["reading_date_dt"] < next_month)]

    month_total = float(month_logs["weighted_pages"].sum()) if not month_logs.empty else 0.0
    target = safe_int(settings.get("family_target_pages"), 0)
    rate = month_total / target * 100 if target > 0 else 0
    stats = get_member_stats(month_logs, members_df)

    top_reader = stats.iloc[0]["member_name"] if not stats.empty and stats.iloc[0]["weighted_pages"] > 0 else "아직 없음"
    steady = stats.sort_values(["record_days", "weighted_pages"], ascending=False).iloc[0]["member_name"] if not stats.empty and stats["record_days"].max() > 0 else "아직 없음"

    finished_reviews = reviews_df[reviews_df["finished_date"].astype(str).str.startswith(report_month.strftime("%Y-%m"), na=False)] if not reviews_df.empty else reviews_df
    finished_books = [get_book_title(book_id, books_df) for book_id in finished_reviews["book_id"].dropna().unique()] if not finished_reviews.empty else []

    month_quotes = quotes_df.copy()
    quote_text = "아직 선정된 문장이 없습니다."
    if not month_quotes.empty:
        quote_text = str(month_quotes.sort_values("created_at", ascending=False).iloc[0]["quote_text"])

    col1, col2, col3 = st.columns(3)
    col1.metric("이번 달 총 페이지", f"{month_total:,.1f}")
    col2.metric("목표 달성률", f"{rate:.1f}%")
    col3.metric("완독한 책", f"{len(finished_books)}권")

    st.subheader("구성원별 누적 페이지")
    if stats.empty:
        st.write("데이터가 없습니다.")
    else:
        st.dataframe(stats.rename(columns={"member_name": "구성원", "pages_read": "실제 페이지", "weighted_pages": "가중치 페이지", "record_days": "기록일 수"})[["구성원", "실제 페이지", "가중치 페이지", "기록일 수"]], use_container_width=True, hide_index=True)

    st.subheader("이달의 요약")
    finished_text = ", ".join(finished_books) if finished_books else "아직 완독 기록은 없습니다"
    auto_summary = (
        f"이번 달 우리 가족은 총 {month_total:,.1f}페이지를 읽었습니다. "
        f"목표 {target:,}페이지 중 {rate:.1f}%를 달성했습니다. "
        f"가장 많이 읽은 사람은 {top_reader}이고, 가장 꾸준히 기록한 사람은 {steady}입니다. "
        f"완독한 책은 {finished_text}. 이달의 문장은 ‘{quote_text}’입니다."
    )
    st.success(auto_summary)

    with st.container(border=True):
        st.markdown("#### 🏅 리포트 상세")
        st.write(f"- 가장 많이 읽은 사람: **{top_reader}**")
        st.write(f"- 가장 꾸준히 기록한 사람: **{steady}**")
        st.write(f"- 완독한 책: **{finished_text}**")
        st.write(f"- 이달의 문장: “{quote_text}”")


def page_settings(data: dict) -> None:
    st.title("⚙️ 마라톤 설정 / 가족 구성원")
    settings = get_settings(data["settings"])
    with st.form("settings_form"):
        marathon_name = st.text_input("마라톤 이름", value=settings["marathon_name"])
        start_date = st.date_input("시작일", value=pd.to_datetime(settings["start_date"]).date())
        end_date = st.date_input("종료일", value=pd.to_datetime(settings["end_date"]).date())
        family_target_pages = st.number_input("가족 목표 페이지", min_value=1, step=100, value=safe_int(settings["family_target_pages"], 2000))
        unit_name = st.text_input("단위명", value=settings["unit_name"])
        submitted = st.form_submit_button("설정 저장")
    if submitted:
        write_csv("settings", pd.DataFrame([{
            "marathon_name": marathon_name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "family_target_pages": family_target_pages,
            "unit_name": unit_name,
        }], columns=CSV_COLUMNS["settings"]))
        st.success("설정을 저장했습니다.")
        st.rerun()

    st.subheader("가족 구성원 추가")
    with st.form("member_form"):
        col1, col2 = st.columns(2)
        name = col1.text_input("이름")
        avatar = col2.text_input("이모지", value="🙂")
        role = st.text_input("역할", placeholder="예: 기록왕, 그림책 러너")
        age_group = st.selectbox("연령대", ["성인", "초등", "유아", "기타"])
        weight = st.number_input("가중치", min_value=0.1, max_value=5.0, step=0.1, value=1.0)
        member_submit = st.form_submit_button("구성원 추가")
    if member_submit:
        if not name.strip():
            st.error("이름을 입력해주세요.")
        else:
            row = {"member_id": make_id("member"), "name": name, "role": role, "age_group": age_group, "weight": weight, "avatar": avatar, "created_at": now_str()}
            members_df = pd.concat([data["family_members"], pd.DataFrame([row])], ignore_index=True)
            write_csv("family_members", members_df)
            st.success("가족 구성원을 추가했습니다.")
            st.rerun()

    st.subheader("현재 가족 구성원")
    if data["family_members"].empty:
        st.write("아직 구성원이 없습니다.")
    else:
        st.dataframe(data["family_members"][["avatar", "name", "role", "age_group", "weight"]], use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="📚", layout="wide")
    ensure_csv_files()
    data = load_all_data()

    with st.sidebar:
        st.title("📚 독서마라톤")
        page = st.radio(
            "메뉴",
            ["홈 / 대시보드", "책 검색 / 책 등록", "가족 책장", "독서 기록 입력", "좋았던 문장", "한 줄 감상", "월간 리포트", "설정 / 가족 구성원"],
        )
        st.divider()
        st.caption("CSV 저장 방식 MVP")
        st.caption(f"데이터 폴더: {DATA_DIR.name}/")

    if page == "홈 / 대시보드":
        page_dashboard(data)
    elif page == "책 검색 / 책 등록":
        page_book_search(data)
    elif page == "가족 책장":
        page_library(data)
    elif page == "독서 기록 입력":
        page_reading_log(data)
    elif page == "좋았던 문장":
        page_quotes(data)
    elif page == "한 줄 감상":
        page_reviews(data)
    elif page == "월간 리포트":
        page_monthly_report(data)
    elif page == "설정 / 가족 구성원":
        page_settings(data)


if __name__ == "__main__":
    main()
