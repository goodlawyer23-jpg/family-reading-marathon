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
# 국립중앙도서관 API는 일부 PC/네트워크 환경에서 연결 지연을 일으킬 수 있어 기본 자동 조회를 끕니다.
NLK_AUTO_LOOKUP_ENABLED = False
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SAMPLE_DIR = BASE_DIR / "sample_data"

CSV_COLUMNS = {
    "books": [
        "book_id", "marathon_id", "reader_member_id", "title", "author", "publisher", "isbn", "image_url",
        "description", "pubdate", "total_pages", "source_api", "created_at",
    ],
    "family_members": [
        "member_id", "name", "role", "age_group", "weight", "avatar", "created_at",
    ],
    "reading_logs": [
        "log_id", "marathon_id", "member_id", "book_id", "reading_date", "pages_read", "weighted_pages",
        "start_page", "end_page", "memo", "created_at",
    ],
    "quotes": [
        "quote_id", "marathon_id", "member_id", "book_id", "page_number", "quote_text", "comment", "created_at",
    ],
    "reviews": [
        "review_id", "marathon_id", "member_id", "book_id", "rating", "one_line_review", "full_review",
        "finished_date", "created_at",
    ],
    "settings": [
        "marathon_id", "marathon_name", "start_date", "end_date", "family_target_pages",
        "unit_name", "is_active", "created_at",
    ],
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
    "marathon_id": "2026-07",
    "marathon_name": "2026년 7월 우리가족 독서마라톤",
    "start_date": "2026-07-01",
    "end_date": "2026-07-31",
    "family_target_pages": 2000,
    "unit_name": "페이지",
    "is_active": True,
    "created_at": "",
}

PLACEHOLDER_COVER = "https://placehold.co/160x220?text=BOOK"
EMOJI_OPTIONS = ["👨", "👩", "👧", "🧒", "👦", "👶", "🐰", "🐻", "🦊", "🐯", "🐥", "🌟"]
AGE_GROUP_OPTIONS = ["성인", "청소년", "어린이", "유아"]
DEFAULT_WEIGHT_BY_AGE = {"성인": 1.0, "청소년": 1.1, "어린이": 1.4, "유아": 2.0}


def recommended_weight(age_group: str) -> float:
    return DEFAULT_WEIGHT_BY_AGE.get(str(age_group).strip(), 1.0)


def normalize_age_group(age_group: str) -> str:
    value = str(age_group or "").strip()
    aliases = {"초등": "어린이", "초등학생": "어린이", "초등 어린이": "어린이", "기타": "성인", "": "성인"}
    return aliases.get(value, value if value in AGE_GROUP_OPTIONS else "성인")


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


def normalize_bool(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "활성", "active"}


def make_marathon_id(start_date_value) -> str:
    try:
        dt = pd.to_datetime(start_date_value).date()
        return dt.strftime("%Y-%m")
    except Exception:
        return f"marathon_{uuid.uuid4().hex[:8]}"


def migrate_data_schema() -> None:
    """기존 단일 마라톤 CSV를 여러 마라톤 구조로 자동 보정합니다."""
    ensure_directories()

    settings_df = read_csv("settings")
    if settings_df.empty:
        default = DEFAULT_SETTINGS.copy()
        default["created_at"] = now_str()
        settings_df = pd.DataFrame([default])

    for col in CSV_COLUMNS["settings"]:
        if col not in settings_df.columns:
            settings_df[col] = ""

    if settings_df["marathon_id"].astype(str).str.strip().eq("").all():
        first_start = settings_df.iloc[0].get("start_date", DEFAULT_SETTINGS["start_date"])
        settings_df.loc[settings_df.index[0], "marathon_id"] = make_marathon_id(first_start)

    for idx in settings_df.index:
        if not str(settings_df.loc[idx, "marathon_id"]).strip():
            settings_df.loc[idx, "marathon_id"] = make_marathon_id(settings_df.loc[idx, "start_date"])
        if not str(settings_df.loc[idx, "created_at"]).strip():
            settings_df.loc[idx, "created_at"] = now_str()

    active_mask = settings_df["is_active"].apply(normalize_bool)
    if not active_mask.any():
        settings_df["is_active"] = False
        settings_df.loc[settings_df.index[0], "is_active"] = True
    else:
        # active는 하나만 유지합니다.
        first_active_idx = settings_df[active_mask].index[0]
        settings_df["is_active"] = False
        settings_df.loc[first_active_idx, "is_active"] = True

    write_csv("settings", settings_df)
    active_id = get_active_marathon_id(settings_df)

    members_df = read_csv("family_members")
    if not members_df.empty and "age_group" in members_df.columns:
        normalized_age = members_df["age_group"].apply(normalize_age_group)
        if not normalized_age.astype(str).equals(members_df["age_group"].astype(str)):
            members_df["age_group"] = normalized_age
            write_csv("family_members", members_df)

    for key in ["books", "reading_logs", "quotes", "reviews"]:
        df = read_csv(key)
        if df.empty:
            continue
        if "marathon_id" not in df.columns:
            df["marathon_id"] = active_id
        blank_mask = df["marathon_id"].astype(str).str.strip().eq("")
        if blank_mask.any():
            df.loc[blank_mask, "marathon_id"] = active_id
        write_csv(key, df)


def get_active_marathon(settings_df: pd.DataFrame | None = None) -> dict:
    if settings_df is None:
        settings_df = read_csv("settings")
    if settings_df.empty:
        return DEFAULT_SETTINGS.copy()
    df = settings_df.copy()
    if "is_active" not in df.columns:
        df["is_active"] = False
    active = df[df["is_active"].apply(normalize_bool)]
    row = active.iloc[0].to_dict() if not active.empty else df.iloc[0].to_dict()
    result = {**DEFAULT_SETTINGS, **row}
    if not str(result.get("marathon_id", "")).strip():
        result["marathon_id"] = make_marathon_id(result.get("start_date", DEFAULT_SETTINGS["start_date"]))
    result["family_target_pages"] = safe_int(result.get("family_target_pages"), DEFAULT_SETTINGS["family_target_pages"])
    return result


def get_active_marathon_id(settings_df: pd.DataFrame | None = None) -> str:
    return str(get_active_marathon(settings_df).get("marathon_id", DEFAULT_SETTINGS["marathon_id"])).strip()


def get_marathon_options(settings_df: pd.DataFrame) -> dict:
    if settings_df.empty:
        return {DEFAULT_SETTINGS["marathon_name"]: DEFAULT_SETTINGS["marathon_id"]}
    options = {}
    for _, row in settings_df.iterrows():
        mid = str(row.get("marathon_id", "")).strip() or make_marathon_id(row.get("start_date", ""))
        name = str(row.get("marathon_name", "독서마라톤")).strip() or mid
        date_label = f"{row.get('start_date', '')} ~ {row.get('end_date', '')}"
        active_mark = " · active" if normalize_bool(row.get("is_active", False)) else ""
        label = f"{name} ({date_label}){active_mark}"
        base_label = label
        n = 2
        while label in options:
            label = f"{base_label} #{n}"
            n += 1
        options[label] = mid
    return options


def get_marathon_by_id(settings_df: pd.DataFrame, marathon_id: str) -> dict:
    if settings_df.empty:
        return DEFAULT_SETTINGS.copy()
    matched = settings_df[settings_df["marathon_id"].astype(str) == str(marathon_id)]
    row = matched.iloc[0].to_dict() if not matched.empty else get_active_marathon(settings_df)
    result = {**DEFAULT_SETTINGS, **row}
    result["family_target_pages"] = safe_int(result.get("family_target_pages"), DEFAULT_SETTINGS["family_target_pages"])
    return result


def filter_by_marathon(df: pd.DataFrame, marathon_id: str) -> pd.DataFrame:
    if df.empty or "marathon_id" not in df.columns:
        return df.copy()
    return df[df["marathon_id"].astype(str).str.strip() == str(marathon_id).strip()].copy()


def scoped_data_for_marathon(data: dict, marathon_id: str) -> dict:
    scoped = data.copy()
    for key in ["books", "reading_logs", "quotes", "reviews"]:
        scoped[key] = filter_by_marathon(data[key], marathon_id)
    return scoped


def set_active_marathon(marathon_id: str) -> None:
    settings_df = read_csv("settings")
    if settings_df.empty:
        return
    settings_df["is_active"] = settings_df["marathon_id"].astype(str) == str(marathon_id)
    write_csv("settings", settings_df)


def start_new_marathon(marathon_name: str, start_date_value, end_date_value, family_target_pages: int, unit_name: str) -> str:
    settings_df = read_csv("settings")
    new_id = make_marathon_id(start_date_value)
    existing_ids = set(settings_df["marathon_id"].astype(str)) if not settings_df.empty else set()
    base_id = new_id
    suffix = 2
    while new_id in existing_ids:
        new_id = f"{base_id}-{suffix}"
        suffix += 1
    if not settings_df.empty:
        settings_df["is_active"] = False
    new_row = {
        "marathon_id": new_id,
        "marathon_name": str(marathon_name).strip() or f"{new_id} 우리가족 독서마라톤",
        "start_date": start_date_value.isoformat() if hasattr(start_date_value, "isoformat") else str(start_date_value),
        "end_date": end_date_value.isoformat() if hasattr(end_date_value, "isoformat") else str(end_date_value),
        "family_target_pages": safe_int(family_target_pages, 2000),
        "unit_name": str(unit_name).strip() or "페이지",
        "is_active": True,
        "created_at": now_str(),
    }
    settings_df = pd.concat([settings_df, pd.DataFrame([new_row])], ignore_index=True)
    write_csv("settings", settings_df)
    return new_id


def get_next_marathon_defaults(settings_df: pd.DataFrame) -> dict:
    active = get_active_marathon(settings_df)
    try:
        base_start = (pd.to_datetime(active.get("end_date", date.today())).date() + timedelta(days=1))
    except Exception:
        today = date.today()
        base_start = (pd.Timestamp(today.replace(day=1)) + pd.offsets.MonthBegin(1)).date()
    start_value = base_start.replace(day=1) if base_start.day != 1 else base_start
    end_value = (pd.Timestamp(start_value) + pd.offsets.MonthEnd(0)).date()
    name = f"{start_value.year}년 {start_value.month}월 우리가족 독서마라톤"
    return {
        "name": name,
        "start_date": start_value,
        "end_date": end_value,
        "target": 2000,
        "unit": "페이지",
    }


def delete_marathon_and_related_data(marathon_id: str) -> dict:
    """선택한 독서마라톤과 해당 마라톤에 속한 책장/기록을 삭제합니다. 러너는 삭제하지 않습니다."""
    marathon_id = str(marathon_id).strip()
    result = {"settings": 0, "books": 0, "logs": 0, "quotes": 0, "reviews": 0, "new_active_id": ""}
    settings_df = read_csv("settings")
    if settings_df.empty or "marathon_id" not in settings_df.columns:
        result["error"] = "삭제할 독서마라톤을 찾지 못했습니다."
        return result

    target_mask = settings_df["marathon_id"].astype(str) == marathon_id
    result["settings"] = int(target_mask.sum())
    if result["settings"] == 0:
        result["error"] = "삭제할 독서마라톤을 찾지 못했습니다."
        return result
    if len(settings_df) <= 1:
        result["error"] = "독서마라톤은 최소 1개가 필요합니다. 마지막 마라톤은 삭제할 수 없습니다."
        return result

    was_active = bool(settings_df.loc[target_mask, "is_active"].apply(normalize_bool).any())
    settings_df = settings_df.loc[~target_mask].copy()
    if was_active:
        settings_df["is_active"] = False
        try:
            order = pd.to_datetime(settings_df["start_date"], errors="coerce")
            new_active_idx = order.sort_values(ascending=False).index[0]
        except Exception:
            new_active_idx = settings_df.index[-1]
        settings_df.loc[new_active_idx, "is_active"] = True
        result["new_active_id"] = str(settings_df.loc[new_active_idx, "marathon_id"])
    elif not settings_df["is_active"].apply(normalize_bool).any():
        settings_df.loc[settings_df.index[0], "is_active"] = True
        result["new_active_id"] = str(settings_df.loc[settings_df.index[0], "marathon_id"])
    write_csv("settings", settings_df)

    for key, result_key in [("books", "books"), ("reading_logs", "logs"), ("quotes", "quotes"), ("reviews", "reviews")]:
        df = read_csv(key)
        if df.empty or "marathon_id" not in df.columns:
            continue
        mask = df["marathon_id"].astype(str) == marathon_id
        result[result_key] = int(mask.sum())
        if mask.any():
            write_csv(key, df.loc[~mask].copy())
    return result


def load_all_data() -> dict:
    ensure_csv_files()
    return {key: read_csv(key) for key in CSV_COLUMNS.keys()}


def delete_runner_and_related_data(member_id: str) -> dict:
    """러너와 해당 러너에게 연결된 책장/기록을 함께 삭제합니다."""
    member_id = str(member_id)
    result = {"members": 0, "books": 0, "logs": 0, "quotes": 0, "reviews": 0}

    members_df = read_csv("family_members")
    if members_df.empty or "member_id" not in members_df.columns:
        return result

    member_mask = members_df["member_id"].astype(str) == member_id
    result["members"] = int(member_mask.sum())
    if result["members"] == 0:
        return result

    books_df = read_csv("books")
    if not books_df.empty and "reader_member_id" in books_df.columns:
        runner_book_ids = books_df.loc[books_df["reader_member_id"].astype(str) == member_id, "book_id"].astype(str).tolist()
    else:
        runner_book_ids = []

    logs_df = read_csv("reading_logs")
    quotes_df = read_csv("quotes")
    reviews_df = read_csv("reviews")

    # 책장은 reader_member_id 기준으로 삭제합니다.
    if not books_df.empty:
        book_mask = books_df["reader_member_id"].astype(str) == member_id
        result["books"] = int(book_mask.sum())
        books_df = books_df.loc[~book_mask].copy()

    # 기록은 member_id 기준으로 삭제하되, 혹시 남아 있는 책 연결 기록도 함께 정리합니다.
    if not logs_df.empty:
        log_mask = logs_df["member_id"].astype(str) == member_id
        if runner_book_ids and "book_id" in logs_df.columns:
            log_mask = log_mask | logs_df["book_id"].astype(str).isin(runner_book_ids)
        result["logs"] = int(log_mask.sum())
        logs_df = logs_df.loc[~log_mask].copy()

    if not quotes_df.empty:
        quote_mask = quotes_df["member_id"].astype(str) == member_id
        if runner_book_ids and "book_id" in quotes_df.columns:
            quote_mask = quote_mask | quotes_df["book_id"].astype(str).isin(runner_book_ids)
        result["quotes"] = int(quote_mask.sum())
        quotes_df = quotes_df.loc[~quote_mask].copy()

    if not reviews_df.empty:
        review_mask = reviews_df["member_id"].astype(str) == member_id
        if runner_book_ids and "book_id" in reviews_df.columns:
            review_mask = review_mask | reviews_df["book_id"].astype(str).isin(runner_book_ids)
        result["reviews"] = int(review_mask.sum())
        reviews_df = reviews_df.loc[~review_mask].copy()

    members_df = members_df.loc[~member_mask].copy()

    write_csv("family_members", members_df)
    write_csv("books", books_df)
    write_csv("reading_logs", logs_df)
    write_csv("quotes", quotes_df)
    write_csv("reviews", reviews_df)
    return result


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
    return get_active_marathon(settings_df)


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


def emoji_options_with_current(current: str = "") -> list[str]:
    current = str(current or "").strip()
    if current and current not in EMOJI_OPTIONS:
        return [current] + EMOJI_OPTIONS
    return EMOJI_OPTIONS.copy()


def book_options(books_df: pd.DataFrame) -> dict:
    return {f"{row.title} - {row.author}": row.book_id for row in books_df.itertuples()}


def is_book_finished_for_member(reviews_df: pd.DataFrame, member_id: str, book_id: str) -> bool:
    """구성원+책 조합의 완독 감상 여부를 확인합니다."""
    if reviews_df.empty:
        return False
    required = {"member_id", "book_id", "finished_date"}
    if not required.issubset(set(reviews_df.columns)):
        return False
    matched = reviews_df[
        (reviews_df["member_id"].astype(str).str.strip() == str(member_id).strip())
        & (reviews_df["book_id"].astype(str).str.strip() == str(book_id).strip())
        & (reviews_df["finished_date"].astype(str).str.strip().str.len() > 0)
    ]
    return not matched.empty


def book_options_for_member(
    books_df: pd.DataFrame,
    member_id: str,
    reviews_df: pd.DataFrame | None = None,
    include_finished: bool = True,
) -> dict:
    """선택한 구성원의 책장에 등록된 책만 독서 기록 입력 후보로 반환합니다."""
    if books_df.empty or "reader_member_id" not in books_df.columns:
        return {}

    member_books = books_df[books_df["reader_member_id"].astype(str).str.strip() == str(member_id).strip()].copy()
    if member_books.empty:
        return {}

    if not include_finished and reviews_df is not None:
        member_books = member_books[
            ~member_books["book_id"].astype(str).apply(lambda bid: is_book_finished_for_member(reviews_df, member_id, bid))
        ].copy()
        if member_books.empty:
            return {}

    options = {}
    duplicated_titles = member_books["title"].astype(str).duplicated(keep=False)
    for idx, row in member_books.reset_index(drop=True).iterrows():
        title = str(row.get("title", "제목 없음") or "제목 없음").strip()
        author = str(row.get("author", "") or "").strip()
        publisher = str(row.get("publisher", "") or "").strip()
        base_label = f"{title} ({author})" if author else title
        if bool(duplicated_titles.iloc[idx]):
            detail = publisher or str(row.get("isbn", "") or "").strip() or str(row.get("book_id", ""))[-6:]
            base_label = f"{base_label} - {detail}" if detail else base_label
        if reviews_df is not None and is_book_finished_for_member(reviews_df, member_id, row.get("book_id", "")):
            base_label = f"{base_label} · 완독"
        label = base_label
        suffix = 2
        while label in options:
            label = f"{base_label} #{suffix}"
            suffix += 1
        options[label] = row.get("book_id", "")
    return options


def clear_today_form_state(member_id: str, book_id: str) -> None:
    """저장 완료 후 같은 입력값이 다시 제출되지 않도록 오늘 기록 입력 위젯 상태를 정리합니다."""
    exact_keys = [
        f"today_book_select_{member_id}",
        f"today_date_{member_id}_{book_id}",
        f"today_record_method_{member_id}_{book_id}",
        f"today_start_{member_id}_{book_id}",
        f"today_end_{member_id}_{book_id}",
        f"today_pages_direct_{member_id}_{book_id}",
        f"today_start_direct_{member_id}_{book_id}",
        f"today_end_direct_{member_id}_{book_id}",
        f"today_memo_{member_id}_{book_id}",
        f"today_add_quote_{member_id}_{book_id}",
        f"today_quote_page_{member_id}_{book_id}",
        f"today_quote_text_{member_id}_{book_id}",
        f"today_quote_comment_{member_id}_{book_id}",
        f"today_finished_{member_id}_{book_id}",
        f"today_rating_stars_{member_id}_{book_id}",
        f"today_one_line_{member_id}_{book_id}",
        f"today_full_review_{member_id}_{book_id}",
        f"today_finished_date_{member_id}_{book_id}",
    ]
    for key in exact_keys:
        st.session_state.pop(key, None)


def create_sample_data() -> None:
    today = date(2026, 7, 6)
    sample_marathon_id = "2026-07"
    members = pd.DataFrame([
        {"member_id": "member_dad", "name": "아빠", "role": "기록왕", "age_group": "성인", "weight": 1.0, "avatar": "👨", "created_at": now_str()},
        {"member_id": "member_mom", "name": "엄마", "role": "응원단장", "age_group": "성인", "weight": 1.0, "avatar": "👩", "created_at": now_str()},
        {"member_id": "member_child1", "name": "첫째", "role": "모험가", "age_group": "어린이", "weight": 1.4, "avatar": "🧒", "created_at": now_str()},
        {"member_id": "member_child2", "name": "둘째", "role": "그림책 러너", "age_group": "유아", "weight": 2.0, "avatar": "👧", "created_at": now_str()},
    ], columns=CSV_COLUMNS["family_members"])

    books = pd.DataFrame([
        {"book_id": "book_001", "marathon_id": sample_marathon_id, "reader_member_id": "member_mom", "title": "긴긴밤", "author": "루리", "publisher": "문학동네", "isbn": "9788954677158", "image_url": PLACEHOLDER_COVER, "description": "서로 다른 존재들이 함께 길을 걷는 이야기", "pubdate": "2021-02-03", "total_pages": 144, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_002", "marathon_id": sample_marathon_id, "reader_member_id": "member_dad", "title": "불편한 편의점", "author": "김호연", "publisher": "나무옆의자", "isbn": "9791161571188", "image_url": PLACEHOLDER_COVER, "description": "동네 편의점에서 만나는 따뜻한 사람들의 이야기", "pubdate": "2021-04-20", "total_pages": 268, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_003", "marathon_id": sample_marathon_id, "reader_member_id": "member_dad", "title": "아몬드", "author": "손원평", "publisher": "창비", "isbn": "9788936434267", "image_url": PLACEHOLDER_COVER, "description": "감정을 느끼기 어려운 소년의 성장 이야기", "pubdate": "2017-03-31", "total_pages": 264, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_004", "marathon_id": sample_marathon_id, "reader_member_id": "member_child2", "title": "수박 수영장", "author": "안녕달", "publisher": "창비", "isbn": "9788936446819", "image_url": PLACEHOLDER_COVER, "description": "여름날 수박 속에서 펼쳐지는 상상 그림책", "pubdate": "2015-07-30", "total_pages": 52, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_005", "marathon_id": sample_marathon_id, "reader_member_id": "member_child2", "title": "강아지똥", "author": "권정생", "publisher": "길벗어린이", "isbn": "9788986621135", "image_url": PLACEHOLDER_COVER, "description": "작고 낮은 존재의 소중함을 알려주는 그림책", "pubdate": "1996-04-01", "total_pages": 36, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_006", "marathon_id": sample_marathon_id, "reader_member_id": "member_child1", "title": "해리 포터와 마법사의 돌", "author": "J.K. 롤링", "publisher": "문학수첩", "isbn": "9788983927620", "image_url": PLACEHOLDER_COVER, "description": "마법 학교에서 시작되는 모험", "pubdate": "2019-11-19", "total_pages": 268, "source_api": "sample", "created_at": now_str()},
        {"book_id": "book_007", "marathon_id": sample_marathon_id, "reader_member_id": "member_child2", "title": "채소 학교와 쌍둥이 딸기", "author": "나카야 미와", "publisher": "웅진주니어", "isbn": "9788901253541", "image_url": PLACEHOLDER_COVER, "description": "채소 친구들이 등장하는 귀여운 그림책", "pubdate": "2021-06-30", "total_pages": 40, "source_api": "sample", "created_at": now_str()},
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
            "marathon_id": sample_marathon_id,
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
        {"quote_id": "quote_001", "marathon_id": sample_marathon_id, "member_id": "member_mom", "book_id": "book_001", "page_number": 42, "quote_text": "함께 걸으면 멀리 갈 수 있어.", "comment": "우리 가족 마라톤이랑 닮았다.", "created_at": now_str()},
        {"quote_id": "quote_002", "marathon_id": sample_marathon_id, "member_id": "member_child1", "book_id": "book_006", "page_number": 31, "quote_text": "새로운 문이 열리는 느낌이야.", "comment": "나도 마법 학교에 가고 싶다.", "created_at": now_str()},
        {"quote_id": "quote_003", "marathon_id": sample_marathon_id, "member_id": "member_dad", "book_id": "book_003", "page_number": 68, "quote_text": "마음을 이해하는 일은 천천히 배워도 된다.", "comment": "아이들과 이야기해 보고 싶은 문장.", "created_at": now_str()},
    ], columns=CSV_COLUMNS["quotes"])

    reviews = pd.DataFrame([
        {"review_id": "review_001", "marathon_id": sample_marathon_id, "member_id": "member_child2", "book_id": "book_004", "rating": 5, "one_line_review": "수박 속에서 수영하는 상상이 제일 재미있다.", "full_review": "그림이 시원해서 여름에 또 보고 싶다.", "finished_date": "2026-07-06", "created_at": now_str()},
        {"review_id": "review_002", "marathon_id": sample_marathon_id, "member_id": "member_mom", "book_id": "book_001", "rating": 5, "one_line_review": "천천히 오래 남는 이야기.", "full_review": "가족이 함께 읽고 이야기하기 좋다.", "finished_date": "", "created_at": now_str()},
        {"review_id": "review_003", "marathon_id": sample_marathon_id, "member_id": "member_dad", "book_id": "book_002", "rating": 4, "one_line_review": "사람 냄새 나는 따뜻한 소설.", "full_review": "짧게 읽기 좋아서 독서마라톤 첫 책으로 좋다.", "finished_date": "", "created_at": now_str()},
    ], columns=CSV_COLUMNS["reviews"])

    settings = pd.DataFrame([{**DEFAULT_SETTINGS, "marathon_id": sample_marathon_id, "is_active": True, "created_at": now_str()}], columns=CSV_COLUMNS["settings"])

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


def get_nlk_cert_key() -> str:
    """국립중앙도서관 ISBN 서지정보 API 인증키를 가져옵니다."""
    cert_key = os.getenv("NLK_CERT_KEY", "")
    try:
        cert_key = cert_key or st.secrets.get("NLK_CERT_KEY", "")
    except Exception:
        pass
    return str(cert_key).strip()


def extract_pages_from_text(text: str) -> int | None:
    """형태사항 문자열 등에서 페이지 수를 추출합니다."""
    value = str(text or "").strip()
    if not value:
        return None

    patterns = [
        r"(\d{1,4})\s*(?:쪽|페이지|page|pages|p\.|p\b|면)",
        r"^(\d{1,4})\s*(?:[,;:/]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            pages = safe_int(match.group(1), 0)
            if 1 <= pages <= 3000:
                return pages
    return None


def extract_pages_from_nlk_payload(payload) -> int | None:
    """국립중앙도서관 ISBN API 응답에서 페이지 수 후보를 폭넓게 탐색합니다."""
    preferred_key_terms = ["page", "pages", "쪽", "페이지", "형태", "form", "extent", "physical", "description"]

    def walk(obj):
        if isinstance(obj, dict):
            # 페이지 수가 들어갈 가능성이 높은 필드를 먼저 확인합니다.
            for key, value in obj.items():
                key_text = str(key).lower()
                if any(term in key_text for term in preferred_key_terms):
                    pages = extract_pages_from_text(value)
                    if pages:
                        return pages
            for value in obj.values():
                pages = walk(value)
                if pages:
                    return pages
        elif isinstance(obj, list):
            for item in obj:
                pages = walk(item)
                if pages:
                    return pages
        return None

    return walk(payload)


def fetch_book_pages_by_isbn_nlk(isbn: str) -> dict:
    """ISBN으로 국립중앙도서관 ISBN 서지정보 API에서 전체 페이지 수를 조회합니다.

    반환값은 앱 화면과 test_nlk_api.py에서 함께 쓰기 쉽도록 상태 정보를 담은 dict입니다.
    """
    cert_key = get_nlk_cert_key()
    clean_isbn = normalize_isbn_for_search(isbn)
    result = {
        "source": "국립중앙도서관",
        "status": "not_called",
        "pages": None,
        "message": "",
        "debug": {},
    }

    if not clean_isbn:
        result.update({"status": "no_isbn", "message": "ISBN이 없어 국립중앙도서관 API를 조회하지 않았습니다."})
        return result
    if not cert_key:
        result.update({"status": "no_key", "message": "국립중앙도서관 API 키가 없어 페이지 수 자동 조회를 건너뛰었습니다."})
        return result

    url = "https://www.nl.go.kr/seoji/SearchApi.do"
    params = {
        "cert_key": cert_key,
        "result_style": "json",
        "page_no": 1,
        "page_size": 1,
        "isbn": clean_isbn,
    }
    safe_params = dict(params)
    safe_params["cert_key"] = "***"
    result["debug"] = {"url": url, "params": safe_params}

    try:
        response = requests.get(url, params=params, timeout=5)
        result["debug"]["status_code"] = response.status_code
        result["debug"]["response_preview"] = response.text.replace(cert_key, "***")[:800]
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            result.update({
                "status": "parse_error",
                "message": "국립중앙도서관 API 응답을 JSON으로 해석하지 못했습니다.",
            })
            return result

        pages = extract_pages_from_nlk_payload(payload)
        result["debug"]["payload_preview"] = str(payload).replace(cert_key, "***")[:1200]
        if pages:
            result.update({
                "status": "success",
                "pages": int(pages),
                "message": f"국립중앙도서관 API 조회 성공 / 페이지 수 {int(pages)}쪽 반영",
            })
        else:
            result.update({
                "status": "no_pages",
                "message": "국립중앙도서관 API 조회는 성공했지만 페이지 수를 추출하지 못했습니다.",
            })
        return result
    except requests.Timeout:
        result.update({
            "status": "timeout",
            "message": "국립중앙도서관 API 연결 시간 초과",
        })
        result["debug"]["error"] = "timeout"
        return result
    except requests.RequestException as e:
        result.update({
            "status": "request_failed",
            "message": "국립중앙도서관 API 호출 실패",
        })
        result["debug"]["error"] = e.__class__.__name__
        return result
    except Exception as e:
        result.update({
            "status": "request_failed",
            "message": "국립중앙도서관 API 처리 중 오류",
        })
        result["debug"]["error"] = e.__class__.__name__
        return result


def fetch_book_pages_by_isbn_aladin(isbn: str) -> dict:
    """향후 알라딘 Open API로 페이지 수를 보강할 때 사용할 자리입니다."""
    return {
        "source": "알라딘",
        "status": "not_implemented",
        "pages": None,
        "message": "알라딘 페이지 수 조회는 아직 연결하지 않았습니다.",
        "debug": {},
    }


def fetch_book_pages_by_isbn(isbn: str) -> dict:
    """ISBN 기반 페이지 수 보강 통합 함수입니다."""
    nlk_result = fetch_book_pages_by_isbn_nlk(isbn)
    if nlk_result.get("pages"):
        return nlk_result

    # 향후 알라딘 API를 실제 연결하면 여기에서 fallback으로 호출할 수 있습니다.
    aladin_result = fetch_book_pages_by_isbn_aladin(isbn)
    nlk_result["fallback"] = aladin_result
    return nlk_result


def build_page_lookup_message(total_pages: int, lookup_result: dict | None) -> tuple[str, str]:
    """사용자용 메시지와 개발 확인용 메시지를 나눠 반환합니다."""
    lookup_result = lookup_result or {}
    status = lookup_result.get("status", "not_called")
    detail = lookup_result.get("message", "")

    if total_pages > 0 and status == "success":
        return f"전체 페이지 수 {total_pages}쪽을 자동으로 반영했습니다.", detail
    if total_pages > 0:
        return f"전체 페이지 수 {total_pages}쪽을 반영했습니다.", detail or "네이버/샘플/직접 입력값의 페이지 수를 저장했습니다."
    if status == "auto_off":
        return "전체 페이지 수는 나중에 입력할 수 있습니다.", detail
    if status == "no_key":
        return "전체 페이지 수는 나중에 입력할 수 있습니다.", "국립중앙도서관 API 키 없음"
    if status == "no_pages":
        return "전체 페이지 수는 나중에 입력할 수 있습니다.", detail
    if status in {"request_failed", "parse_error", "timeout"}:
        return "전체 페이지 수는 나중에 입력할 수 있습니다.", detail
    if status == "no_isbn":
        return "ISBN이 없어 전체 페이지 수는 나중에 입력할 수 있습니다.", detail
    return "전체 페이지 수는 나중에 입력할 수 있습니다.", detail


def add_book_to_library(book_data: dict, reader_member_id: str = "") -> tuple[bool, str, str]:
    """책장에 책을 추가합니다. 같은 마라톤 안에서 같은 책+같은 러너 조합은 중복 등록하지 않습니다."""
    books_df = read_csv("books")
    active_marathon_id = get_active_marathon_id(read_csv("settings"))
    title = clean_html(book_data.get("title", "")).strip()
    reader_member_id = str(reader_member_id or "").strip()
    isbn = str(book_data.get("isbn", "") or "").strip()
    total_pages = safe_int(book_data.get("total_pages"), 0)
    lookup_result = {"status": "not_called", "message": ""}

    # 안정적인 책 등록 UX를 위해 국립중앙도서관 API는 책장 추가 시 자동 호출하지 않습니다.
    # 네이버/샘플/직접등록 값에 total_pages가 있으면 그대로 저장하고, 없으면 0으로 저장합니다.
    if total_pages <= 0:
        lookup_result = {
            "status": "auto_off",
            "message": "국립중앙도서관 페이지 수 자동 조회는 기본값 OFF입니다. 필요하면 설정 화면의 수동 테스트를 사용하세요.",
        }

    page_message, detail_message = build_page_lookup_message(total_pages, lookup_result)

    scoped_books_df = filter_by_marathon(books_df, active_marathon_id)
    duplicate_book_mask = same_book_mask(scoped_books_df, book_data)
    if len(duplicate_book_mask) == len(scoped_books_df) and duplicate_book_mask.any():
        same_reader_mask = scoped_books_df.get("reader_member_id", pd.Series([""] * len(scoped_books_df))).astype(str).str.strip() == reader_member_id
        same_book_same_reader = scoped_books_df[duplicate_book_mask & same_reader_mask]
        if not same_book_same_reader.empty:
            return False, f"이미 이 러너의 책장에 《{title or '이 책'}》이 있습니다.", "중복 책장 추가 방지"

        no_reader_mask = scoped_books_df.get("reader_member_id", pd.Series([""] * len(scoped_books_df))).astype(str).str.strip() == ""
        no_reader_rows = scoped_books_df[duplicate_book_mask & no_reader_mask]
        if reader_member_id and not no_reader_rows.empty:
            idx = no_reader_rows.index[0]
            books_df.loc[idx, "reader_member_id"] = reader_member_id
            if safe_int(books_df.loc[idx, "total_pages"], 0) <= 0 and total_pages > 0:
                books_df.loc[idx, "total_pages"] = total_pages
            write_csv("books", books_df)
            # 저장 직후 다음 렌더링에서 반드시 최신 CSV를 읽도록 표시합니다.
            st.session_state["books_csv_updated_at"] = now_str()
            return True, f"기존 책장 항목에 읽는 러너를 연결했습니다. {page_message}", detail_message

    row = {col: book_data.get(col, "") for col in CSV_COLUMNS["books"]}
    row["book_id"] = make_id("book")
    row["marathon_id"] = active_marathon_id
    row["reader_member_id"] = reader_member_id or row.get("reader_member_id", "")
    row["title"] = title
    row["author"] = clean_html(row.get("author", ""))
    row["publisher"] = clean_html(row.get("publisher", ""))
    row["description"] = clean_html(row.get("description", ""))
    row["pubdate"] = normalize_pubdate(row.get("pubdate", ""))
    row["image_url"] = row.get("image_url") or PLACEHOLDER_COVER
    row["total_pages"] = total_pages
    row["source_api"] = row.get("source_api") or "manual"
    row["created_at"] = now_str()
    books_df = pd.concat([books_df, pd.DataFrame([row])], ignore_index=True)
    write_csv("books", books_df)
    # 저장 직후 다음 렌더링에서 반드시 최신 CSV를 읽도록 표시합니다.
    st.session_state["books_csv_updated_at"] = now_str()
    return True, page_message, detail_message


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
        return pd.DataFrame(columns=["member_id", "name", "avatar", "member_name", "pages_read", "weighted_pages", "record_days"])
    members = members_df.copy()
    members["name"] = members["name"].astype(str)
    members["avatar"] = members["avatar"].astype(str)
    members["member_name"] = (members["avatar"].str.strip() + " " + members["name"].str.strip()).str.strip()
    if logs_df.empty:
        stats = members[["member_id", "name", "avatar", "member_name"]].copy()
        stats["pages_read"] = 0
        stats["weighted_pages"] = 0.0
        stats["record_days"] = 0
        return stats[["member_id", "name", "avatar", "member_name", "pages_read", "weighted_pages", "record_days"]]
    grouped = logs_df.groupby("member_id").agg(
        pages_read=("pages_read", "sum"),
        weighted_pages=("weighted_pages", "sum"),
        record_days=("reading_date", pd.Series.nunique),
    ).reset_index()
    stats = members[["member_id", "name", "avatar", "member_name"]].merge(grouped, on="member_id", how="left").fillna(0)
    stats["pages_read"] = stats["pages_read"].astype(int)
    stats["weighted_pages"] = stats["weighted_pages"].astype(float).round(1)
    stats["record_days"] = stats["record_days"].astype(int)
    return stats.sort_values("weighted_pages", ascending=False)


def make_emoji_track(progress_percent: float, length: int = 18, runner: str = "🏃‍➡️") -> str:
    """진행률을 오른쪽 방향 마라톤 트랙으로 변환합니다."""
    progress_percent = max(0.0, min(float(progress_percent or 0), 100.0))
    if length <= 1:
        return runner
    position = int(round((progress_percent / 100) * (length - 1)))
    return "━" * position + runner + "━" * (length - position - 1)


def get_badge_for_member(row, leader_id: str, steady_id: str, finished_member_ids: set[str], quote_member_ids: set[str]) -> str:
    member_id = str(row.get("member_id", "")) if isinstance(row, dict) else str(row.member_id)
    weighted_pages = safe_float(row.get("weighted_pages", 0) if isinstance(row, dict) else row.weighted_pages, 0)
    record_days = safe_int(row.get("record_days", 0) if isinstance(row, dict) else row.record_days, 0)
    if member_id == leader_id and weighted_pages > 0:
        return "🌟 앞장서 달리는 러너"
    if member_id == steady_id and record_days > 0:
        return "🔥 꾸준히 함께 달리는 러너"
    if member_id in finished_member_ids:
        return "🏁 완주 경험자"
    if member_id in quote_member_ids:
        return "💬 문장 수집가"
    if weighted_pages > 0:
        return "👟 함께 달리는 중"
    return "🌱 출발 준비"


def get_dashboard_encouragement(summary: dict, member_stats_df: pd.DataFrame) -> str:
    progress = safe_float(summary.get("progress", 0), 0)
    remain = safe_float(summary.get("remain", 0), 0)
    unit_name = summary.get("settings", {}).get("unit_name", "페이지")
    if progress >= 100:
        return "🎉 우리 가족이 함께 결승선에 도착했어요! 완주 기록을 함께 돌아볼 시간입니다."
    if not member_stats_df.empty and safe_float(member_stats_df.iloc[0].get("weighted_pages", 0), 0) > 0:
        leader = str(member_stats_df.iloc[0].get("name", member_stats_df.iloc[0].get("member_name", "가족")))
        return f"🤝 {leader}님이 오늘의 앞장 러너예요. 하지만 이 마라톤은 모두가 함께 결승선을 향해 가는 협동 미션입니다."
    if progress > 0:
        return f"📚 우리 가족은 이미 목표의 {progress:.1f}%를 함께 달성했어요. 남은 거리는 {remain:,.0f}{unit_name}입니다."
    return "🌱 오늘 10쪽만 읽어도 우리 가족 결승선에 한 걸음 더 가까워져요!"


def display_unit(unit_name: str) -> str:
    """좁은 화면에서 잘리지 않도록 표시용 단위를 짧게 변환합니다."""
    unit_name = str(unit_name or "페이지").strip()
    if unit_name == "페이지":
        return "쪽"
    return unit_name


def render_family_marathon_track(summary: dict) -> None:
    settings = summary["settings"]
    progress = safe_float(summary.get("progress", 0), 0)
    track = make_emoji_track(progress, length=24, runner="🏃‍➡️")
    unit = display_unit(settings.get("unit_name", "페이지"))
    target_pages = safe_int(settings.get("family_target_pages", 0), 0)
    total_pages = safe_int(round(safe_float(summary.get("total_weighted", 0), 0)), 0)
    remain_pages = safe_int(round(max(safe_float(summary.get("remain", 0), 0), 0)), 0)
    st.markdown("### 🏁 가족 독서마라톤 트랙")
    st.markdown(f"#### 우리 가족은 결승선까지 **{progress:.1f}%** 왔어요!")
    st.progress(min(progress / 100, 1.0), text=f"가족 전체 진행률 {progress:.1f}%")
    st.markdown(
        f"""
        <div style="padding: 1rem; border-radius: 1rem; border: 1px solid rgba(120,120,120,.25); background: rgba(250,250,250,.55); margin: .5rem 0 1rem 0;">
            <div style="font-size: 1.05rem; margin-bottom: .35rem;"><b>START</b> {track} <b>GOAL</b></div>
            <div style="font-size: .95rem;">🎯 목표 {target_pages:,}{unit} · 📚 누적 {total_pages:,}{unit} · 🚩 남은 거리 {remain_pages:,}{unit}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_family_contribution_cards(member_stats_df: pd.DataFrame) -> None:
    st.markdown("### 🤝 함께 만든 독서 거리")
    st.caption("이 마라톤은 순위 경쟁이 아니라, 우리 가족이 함께 결승선을 향해 가는 협동 미션입니다.")
    if member_stats_df.empty:
        st.info("러너를 등록하면 우리 가족 기여도가 표시됩니다.")
        return

    total_weighted = safe_float(member_stats_df["weighted_pages"].sum(), 0) if "weighted_pages" in member_stats_df.columns else 0
    card_count = min(max(len(member_stats_df), 1), 4)
    cols = st.columns(card_count)
    for idx, (_, row) in enumerate(member_stats_df.iterrows()):
        contribution = (safe_float(row.get("weighted_pages", 0), 0) / total_weighted * 100) if total_weighted > 0 else 0
        with cols[idx % card_count]:
            st.markdown(
                f"""
                <div style="padding: 1rem; border-radius: 1rem; border: 1px solid rgba(120,120,120,.25); background: rgba(255,255,255,.72); text-align: center; margin-bottom: .75rem; min-height: 120px;">
                    <div style="font-size: 1.6rem;">{row.get('avatar', '🏃')}</div>
                    <div style="font-weight: 700; margin-top: .15rem;">{html.escape(str(row.get('name', '러너')))}</div>
                    <div style="font-size: 2rem; font-weight: 800; margin-top: .35rem;">{contribution:.0f}%</div>
                    <div style="font-size: .85rem; opacity: .75;">함께 보탠 거리</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_runner_cards(member_stats_df: pd.DataFrame, reviews_df: pd.DataFrame, quotes_df: pd.DataFrame) -> None:
    st.markdown("### 🪪 우리 가족 러너 카드")
    if member_stats_df.empty:
        st.info("러너를 등록하면 러너 카드가 표시됩니다.")
        return

    leader_id = str(member_stats_df.iloc[0].get("member_id", "")) if safe_float(member_stats_df.iloc[0].get("weighted_pages", 0), 0) > 0 else ""
    steady_df = member_stats_df.sort_values(["record_days", "weighted_pages"], ascending=False)
    steady_id = str(steady_df.iloc[0].get("member_id", "")) if not steady_df.empty and safe_int(steady_df.iloc[0].get("record_days", 0), 0) > 0 else ""
    finished_member_ids = set()
    if not reviews_df.empty and "finished_date" in reviews_df.columns:
        finished_rows = reviews_df[reviews_df["finished_date"].astype(str).str.strip().str.len() > 0]
        finished_member_ids = set(finished_rows["member_id"].astype(str))
    quote_member_ids = set(quotes_df["member_id"].astype(str)) if not quotes_df.empty and "member_id" in quotes_df.columns else set()

    cols = st.columns(2)
    for idx, (_, row) in enumerate(member_stats_df.iterrows()):
        badge = get_badge_for_member(row.to_dict(), leader_id, steady_id, finished_member_ids, quote_member_ids)
        with cols[idx % 2]:
            st.markdown(
                f"""
                <div style="padding: 1rem; border-radius: 1rem; border: 1px solid rgba(120,120,120,.25); background: rgba(255,255,255,.65); margin-bottom: .75rem;">
                    <div style="font-size: 1.35rem; font-weight: 700;">{row.get('avatar', '🏃')} {html.escape(str(row.get('name', '')))}</div>
                    <div style="margin-top: .4rem;">{badge}</div>
                    <div style="margin-top: .55rem; font-size: .95rem; line-height: 1.7;">
                        📖 실제 읽은 페이지: <b>{safe_int(row.get('pages_read', 0)):,}쪽</b><br>
                        🤝 기여 반영 거리: <b>{safe_float(row.get('weighted_pages', 0)):,.1f}쪽</b><br>
                        📅 기록일 수: <b>{safe_int(row.get('record_days', 0))}일</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def get_last_end_page(logs_df: pd.DataFrame, member_id: str, book_id: str) -> int:
    """선택한 구성원+책 조합의 마지막 끝 페이지를 반환합니다."""
    if logs_df.empty:
        return 0
    target_logs = logs_df[
        (logs_df["member_id"].astype(str) == str(member_id))
        & (logs_df["book_id"].astype(str) == str(book_id))
    ].copy()
    if target_logs.empty or "end_page" not in target_logs.columns:
        return 0
    target_logs["end_page_num"] = target_logs["end_page"].apply(safe_int)
    return safe_int(target_logs["end_page_num"].max(), 0)


def get_book_progress(book_id: str, books_df: pd.DataFrame, logs_df: pd.DataFrame) -> tuple[int, int, float]:
    """책장 카드용 진행률을 계산합니다.

    누적 페이지 표시는 pages_read 합계를 유지하되, 진행률은 가능하면
    해당 책의 가장 큰 end_page 기준으로 계산합니다. 직접 입력처럼 end_page가
    없는 기록만 있는 경우에는 pages_read 합계 기준으로 fallback합니다.
    """
    book = books_df[books_df["book_id"] == book_id]
    total_pages = safe_int(book.iloc[0]["total_pages"], 0) if not book.empty else 0
    book_logs = logs_df[logs_df["book_id"] == book_id].copy() if not logs_df.empty else pd.DataFrame()
    pages_sum = safe_int(book_logs["pages_read"].sum(), 0) if not book_logs.empty else 0
    if not book_logs.empty and "end_page" in book_logs.columns:
        book_logs["end_page_num"] = book_logs["end_page"].apply(safe_int)
        progress_pages = safe_int(book_logs["end_page_num"].max(), 0)
    else:
        progress_pages = 0
    if progress_pages <= 0:
        progress_pages = pages_sum
    progress = min(progress_pages / total_pages * 100, 100) if total_pages > 0 else 0
    return pages_sum, total_pages, progress


def count_book_related_records(book_id: str, marathon_id: str | None = None) -> dict:
    """책장 항목에 연결된 기록 수를 확인합니다.

    book_id는 기본적으로 고유하지만, 마라톤별 책장 구조를 안전하게 유지하기 위해
    marathon_id가 주어지면 해당 마라톤 범위 안에서만 확인합니다.
    """
    book_id = str(book_id).strip()
    marathon_id = str(marathon_id or "").strip()
    counts = {"logs": 0, "quotes": 0, "reviews": 0, "total": 0}
    for csv_key, count_key in [("reading_logs", "logs"), ("quotes", "quotes"), ("reviews", "reviews")]:
        df = read_csv(csv_key)
        if df.empty or "book_id" not in df.columns:
            continue
        target = df["book_id"].astype(str).str.strip() == book_id
        if marathon_id and "marathon_id" in df.columns:
            target = target & (df["marathon_id"].astype(str).str.strip() == marathon_id)
        counts[count_key] = int(target.sum())
    counts["total"] = counts["logs"] + counts["quotes"] + counts["reviews"]
    return counts


def remove_book_from_library(book_id: str, marathon_id: str | None = None) -> tuple[bool, str]:
    """기록이 없는 책장 항목만 제거합니다."""
    book_id = str(book_id).strip()
    marathon_id = str(marathon_id or "").strip()
    counts = count_book_related_records(book_id, marathon_id)
    if counts["total"] > 0:
        return False, "이 책에는 독서 기록이 있어 바로 제거할 수 없습니다. 먼저 기록 모아보기에서 관련 기록을 삭제해주세요."

    books_df = read_csv("books")
    if books_df.empty or "book_id" not in books_df.columns:
        return False, "제거할 책을 찾지 못했습니다."
    mask = books_df["book_id"].astype(str).str.strip() == book_id
    if marathon_id and "marathon_id" in books_df.columns:
        mask = mask & (books_df["marathon_id"].astype(str).str.strip() == marathon_id)
    if not mask.any():
        return False, "제거할 책을 찾지 못했습니다."
    books_df = books_df.loc[~mask].copy()
    write_csv("books", books_df)
    st.session_state["books_csv_updated_at"] = now_str()
    return True, "책장에서 제거했습니다."


def update_book_reader(book_id: str, new_reader_member_id: str, marathon_id: str | None = None) -> tuple[bool, str]:
    """기록이 없는 책장 항목의 읽는 러너를 변경합니다."""
    book_id = str(book_id).strip()
    new_reader_member_id = str(new_reader_member_id or "").strip()
    marathon_id = str(marathon_id or "").strip()
    if not new_reader_member_id:
        return False, "변경할 러너를 선택해주세요."

    counts = count_book_related_records(book_id, marathon_id)
    if counts["total"] > 0:
        return False, "이미 독서 기록이 있는 책은 러너를 변경할 수 없습니다."

    books_df = read_csv("books")
    if books_df.empty or "book_id" not in books_df.columns:
        return False, "변경할 책을 찾지 못했습니다."
    current_mask = books_df["book_id"].astype(str).str.strip() == book_id
    if marathon_id and "marathon_id" in books_df.columns:
        current_mask = current_mask & (books_df["marathon_id"].astype(str).str.strip() == marathon_id)
    if not current_mask.any():
        return False, "변경할 책을 찾지 못했습니다."

    current_row = books_df.loc[current_mask].iloc[0].to_dict()
    current_reader_id = str(current_row.get("reader_member_id", "") or "").strip()
    if current_reader_id == new_reader_member_id:
        return False, "이미 선택한 러너의 책장에 등록되어 있습니다."

    scoped_books_df = filter_by_marathon(books_df, marathon_id) if marathon_id else books_df.copy()
    duplicate_mask = same_book_mask(scoped_books_df, current_row)
    if len(duplicate_mask) == len(scoped_books_df) and duplicate_mask.any():
        same_reader_mask = scoped_books_df.get("reader_member_id", pd.Series([""] * len(scoped_books_df))).astype(str).str.strip() == new_reader_member_id
        same_book_same_reader = scoped_books_df[duplicate_mask & same_reader_mask & (scoped_books_df["book_id"].astype(str).str.strip() != book_id)]
        if not same_book_same_reader.empty:
            return False, "변경하려는 러너의 책장에 이미 같은 책이 있습니다."

    books_df.loc[current_mask, "reader_member_id"] = new_reader_member_id
    write_csv("books", books_df)
    st.session_state["books_csv_updated_at"] = now_str()
    return True, "읽는 러너를 변경했습니다."


def render_metric_cards(summary: dict) -> None:
    settings = summary["settings"]
    unit = display_unit(settings.get("unit_name", "페이지"))
    metrics = [
        ("가족 목표", f"{safe_int(settings.get('family_target_pages', 0)):,}{unit}"),
        ("누적 기록", f"{safe_int(round(safe_float(summary.get('total_weighted', 0), 0))):,}{unit}"),
        ("진행률", f"{safe_float(summary.get('progress', 0), 0):.1f}%"),
        ("남은 거리", f"{safe_int(round(max(safe_float(summary.get('remain', 0), 0), 0))):,}{unit}"),
    ]
    cols = st.columns(4)
    for col, (label, value) in zip(cols, metrics):
        with col:
            st.markdown(
                f"""
                <div style="padding: .8rem .75rem; border-radius: .9rem; border: 1px solid rgba(120,120,120,.18); background: rgba(255,255,255,.72); min-height: 95px;">
                    <div style="font-size: .92rem; opacity: .78; margin-bottom: .35rem; white-space: nowrap;">{label}</div>
                    <div style="font-size: clamp(1.45rem, 3.3vw, 2.1rem); font-weight: 750; line-height: 1.15; white-space: nowrap; letter-spacing: -0.04em;">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.progress(min(summary["progress"] / 100, 1.0), text=f"가족 독서마라톤 진행률 {summary['progress']:.1f}%")


def page_dashboard(data: dict) -> None:
    st.title("🏃‍➡️ 우리가족 독서마라톤")
    st.caption("책을 읽은 만큼 가족 마라톤 트랙이 앞으로 나아갑니다.")

    active_marathon = get_active_marathon(data["settings"])
    active_marathon_id = active_marathon["marathon_id"]
    scoped_data = scoped_data_for_marathon(data, active_marathon_id)
    summary = calculate_summary(scoped_data)
    settings = active_marathon
    summary["settings"] = settings
    st.info(f"{settings['marathon_name']} · {settings['start_date']} ~ {settings['end_date']}")

    member_stats_df = get_member_stats(summary["logs"], data["family_members"])

    render_family_marathon_track(summary)
    st.info(get_dashboard_encouragement(summary, member_stats_df))
    render_metric_cards(summary)


    if member_stats_df.empty:
        st.warning("아직 러너가 없습니다. 샘플 데이터를 생성하거나 러너를 추가해주세요.")
    else:
        render_family_contribution_cards(member_stats_df)
        render_runner_cards(member_stats_df, scoped_data["reviews"], scoped_data["quotes"])

        with st.expander("📊 기여 현황 자세히 보기", expanded=False):
            chart_df = member_stats_df.rename(columns={"member_name": "러너", "weighted_pages": "가중치 반영 페이지"})
            fig = px.bar(chart_df, x="러너", y="가중치 반영 페이지", text="가중치 반영 페이지")
            fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, use_container_width=True)

            rank_df = member_stats_df.copy()
            rank_df.insert(0, "기여 순서", range(1, len(rank_df) + 1))
            st.dataframe(
                rank_df.rename(columns={
                    "member_name": "러너", "pages_read": "실제 읽은 페이지", "weighted_pages": "가중치 반영 페이지", "record_days": "기록일 수",
                })[["기여 순서", "러너", "실제 읽은 페이지", "가중치 반영 페이지", "기록일 수"]],
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
        st.warning("책을 책장에 추가하려면 함께 달릴 러너가 필요합니다. 먼저 샘플 데이터를 생성하거나 러너를 추가해주세요.")
        return

    m_options = member_options(members_df)
    client_id, client_secret = get_naver_credentials()
    api_ready = bool(client_id and client_secret)
    st.info("네이버 책 검색 API: 사용 가능" if api_ready else "네이버 API 키가 없어 샘플 책 검색으로 작동합니다.")
    feedback = st.session_state.pop("book_add_feedback", None)
    if feedback:
        level = feedback[0]
        text = feedback[1] if len(feedback) > 1 else ""
        detail = feedback[2] if len(feedback) > 2 else ""
        if level == "success":
            st.success(text)
        else:
            st.warning(text)
        if detail:
            with st.expander("페이지 수 조회 상태", expanded=False):
                st.caption(detail)

    # Streamlit의 st.tabs는 모든 탭 내용을 동시에 렌더링하므로, 검색 결과와 직접등록 폼이 섞여 보이는 환경을 막기 위해
    # 탭처럼 보이는 라디오 선택으로 현재 선택한 등록 방식만 렌더링합니다.
    registration_view = st.radio(
        "등록 방식",
        ["네이버/샘플 검색", "직접 등록"],
        horizontal=True,
        label_visibility="collapsed",
        key="book_registration_view",
    )

    if registration_view == "네이버/샘플 검색":
        st.markdown("#### 1단계. 검색 방식을 선택하세요")
        search_mode_label = st.radio("검색 방식", ["책 제목 검색", "ISBN 검색"], horizontal=True)
        display_count = 50
        st.caption("검색 결과는 최대 50개까지 가져오고, 화면에는 10개씩 나누어 보여줍니다.")

        search_mode = "isbn" if search_mode_label == "ISBN 검색" else "title"
        placeholder = "예: 978-8954677158" if search_mode == "isbn" else "예: 긴긴밤, 해리 포터"
        label = "ISBN 입력" if search_mode == "isbn" else "책 제목 또는 저자 검색"
        with st.form(key=f"book_search_form_{search_mode}", clear_on_submit=False):
            query = st.text_input(label, placeholder=placeholder)
            search_submitted = st.form_submit_button("검색하기", type="primary")

        st.markdown("#### 2단계. 이 책을 읽을 러너를 선택하세요")
        st.caption("검색 결과에서 책장에 추가하면, 아래에서 선택한 러너의 책장에 바로 연결됩니다.")
        selected_reader_label = st.selectbox("읽을 러너", list(m_options.keys()), key="search_reader")
        selected_reader_id = m_options[selected_reader_label]

        if search_submitted:
            normalized_query = normalize_isbn_for_search(query) if search_mode == "isbn" else str(query or "").strip()
            if not str(normalized_query).strip():
                st.warning("검색어를 입력한 뒤 Enter를 누르거나 검색하기 버튼을 눌러주세요.")
                st.session_state["book_search_results"] = []
                st.session_state["book_search_message"] = "검색어가 비어 있어 검색하지 않았습니다."
                st.session_state["book_search_page"] = 1
            else:
                naver_results = []
                search_source = "sample"

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
                st.session_state["scroll_to_book_results"] = True

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
            st.caption(f"현재 선택된 러너: **{selected_reader_label}**")

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
                        original_total_pages = safe_int(book.get('total_pages'), 0)
                        total_pages_input = st.number_input(
                            "전체 페이지 수",
                            min_value=0,
                            step=1,
                            value=max(0, original_total_pages),
                            key=f"search_total_pages_{global_idx}_{selected_reader_id}",
                            help="페이지 수를 알고 있으면 책장에 추가하기 전에 입력해주세요. 0이면 나중에 가족 책장에서 수정할 수 있습니다.",
                        )
                        if description:
                            with st.expander("책 소개 보기", expanded=False):
                                st.write(description)
                        else:
                            st.caption("책 소개 없음")
                        if st.button(f"{selected_reader_label}의 책장에 추가", key=f"add_search_{global_idx}_{selected_reader_id}"):
                            book_to_add = dict(book)
                            book_to_add.update({
                                "title": title,
                                "author": author,
                                "publisher": publisher,
                                "description": description,
                                "pubdate": pubdate,
                                "total_pages": safe_int(total_pages_input, 0),
                            })
                            success, msg, detail = add_book_to_library(book_to_add, selected_reader_id)
                            if success:
                                st.session_state["book_add_feedback"] = ("success", f"《{title}》을 {selected_reader_label}의 책장에 추가했습니다. {msg}", detail)
                            else:
                                st.session_state["book_add_feedback"] = ("warning", msg, detail)
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

    else:
        st.markdown("#### 직접 등록")
        st.caption("직접 등록할 때도 이 책을 읽을 러너를 함께 선택합니다. 저장 즉시 가족 책장에 읽는 러너가 표시됩니다.")
        with st.form("manual_book_form"):
            reader_label = st.selectbox("이 책을 읽을 러너", list(m_options.keys()), key="manual_reader")
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
                success, msg, detail = add_book_to_library({
                    "book_id": make_id("book"), "title": title, "author": author, "publisher": publisher,
                    "isbn": isbn, "image_url": image_url, "description": description, "pubdate": pubdate,
                    "total_pages": total_pages, "source_api": "manual", "created_at": now_str(),
                }, m_options[reader_label])
                if success:
                    st.session_state["book_add_feedback"] = ("success", f"《{clean_html(title)}》을 {reader_label}의 책장에 추가했습니다. {msg}", detail)
                    st.rerun()
                else:
                    st.warning(msg)
                    if detail:
                        st.caption(f"개발 확인: {detail}")

def page_library(data: dict) -> None:
    st.title("📚 가족 책장")
    st.caption("책을 추가할 때 선택한 러너가 바로 표시됩니다. 독서 기록을 아직 입력하지 않아도 러너별 책장을 확인할 수 있습니다.")
    # 책장 화면은 저장 직후 갱신 UX가 중요하므로, 전달받은 data 대신 CSV를 한 번 더 읽어 최신 상태를 보장합니다.
    all_books_df = read_csv("books")
    members_df = read_csv("family_members")
    all_reading_logs_df = read_csv("reading_logs")
    all_reviews_df = read_csv("reviews")
    settings_df = read_csv("settings")

    marathon_options = get_marathon_options(settings_df)
    active_mid = get_active_marathon_id(settings_df)
    option_values = list(marathon_options.values())
    default_index = option_values.index(active_mid) if active_mid in option_values else 0
    selected_marathon_label = st.selectbox("보기 기준", list(marathon_options.keys()), index=default_index, key="library_marathon_select")
    selected_marathon_id = marathon_options[selected_marathon_label]

    books_df = filter_by_marathon(all_books_df, selected_marathon_id)
    reading_logs_df = filter_by_marathon(all_reading_logs_df, selected_marathon_id)
    reviews_df = filter_by_marathon(all_reviews_df, selected_marathon_id)
    logs_df = enrich_logs(reading_logs_df, members_df, books_df)

    library_feedback = st.session_state.pop("library_manage_feedback", None)
    if library_feedback:
        level, message = library_feedback
        if level == "success":
            st.success(message)
        elif level == "warning":
            st.warning(message)
        else:
            st.info(message)

    if books_df.empty:
        st.warning("선택한 독서마라톤의 책장이 비어 있습니다. 현재 active 마라톤이라면 책 검색 / 책 등록 화면에서 책을 추가해주세요.")
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
                        finished = not reviews_df[(reviews_df["book_id"].astype(str) == str(book["book_id"])) & (reviews_df["member_id"].astype(str) == str(reader_id)) & (reviews_df["finished_date"].astype(str).str.len() > 0)].empty if (not reviews_df.empty and reader_id) else False

                        st.markdown(f"**읽는 러너**  \n{', '.join(readers) if readers else '아직 없음'}")
                        st.markdown(f"**상태**  \n{'✅ 완독' if finished else '📖 읽는 중'}")
                        isbn = str(book.get("isbn", "") or "").strip()
                        if isbn:
                            st.caption(f"ISBN: {isbn}")

                    if total_pages > 0:
                        st.progress(min(progress / 100, 1.0), text=f"{pages_sum}/{total_pages}쪽 · {progress:.1f}%")
                    else:
                        st.progress(0, text=f"{pages_sum}쪽 기록 · 전체 페이지 미입력")

                    with st.expander("전체 페이지 수 수정", expanded=False):
                        edited_total_pages = st.number_input(
                            "새 전체 페이지 수",
                            min_value=0,
                            step=1,
                            value=max(0, safe_int(total_pages, 0)),
                            key=f"library_total_pages_{book['book_id']}",
                        )
                        if st.button("전체 페이지 수 저장", key=f"save_total_pages_{book['book_id']}"):
                            latest_books_df = read_csv("books")
                            mask = latest_books_df["book_id"].astype(str) == str(book["book_id"])
                            if "marathon_id" in latest_books_df.columns:
                                mask = mask & (latest_books_df["marathon_id"].astype(str) == str(selected_marathon_id))
                            if mask.any():
                                latest_books_df.loc[mask, "total_pages"] = safe_int(edited_total_pages, 0)
                                write_csv("books", latest_books_df)
                                st.session_state["library_manage_feedback"] = ("success", "전체 페이지 수를 저장했습니다. 진행률을 다시 계산합니다.")
                                st.rerun()
                            else:
                                st.warning("수정할 책을 찾지 못했습니다.")

                    book_id = str(book.get("book_id", "")).strip()
                    manage_expander_label = f"책장 관리 · {title[:14]} · {registered_reader or '러너 미지정'}" if title else "책장 관리"
                    with st.expander(manage_expander_label, expanded=False):
                        related_counts = count_book_related_records(book_id, selected_marathon_id)
                        has_related_records = related_counts["total"] > 0

                        if has_related_records:
                            st.info(
                                "이 책에는 독서 기록이 있어 바로 제거하거나 러너를 변경할 수 없습니다. "
                                "먼저 기록 모아보기에서 관련 기록을 삭제해주세요."
                            )
                            st.caption(
                                f"연결된 기록: 독서 기록 {related_counts['logs']}개 · "
                                f"좋았던 문장 {related_counts['quotes']}개 · 완독 감상 {related_counts['reviews']}개"
                            )
                        else:
                            st.caption("아직 연결된 기록이 없는 책입니다. 책장에서 제거하거나 읽는 러너를 변경할 수 있습니다.")

                        st.markdown("##### 읽는 러너 변경")
                        if has_related_records:
                            st.caption("이미 독서 기록이 있는 책은 러너를 변경할 수 없습니다.")
                        else:
                            runner_options = member_options(members_df)
                            runner_labels = list(runner_options.keys())
                            current_reader_id = str(book.get("reader_member_id", "") or "").strip()
                            current_index = 0
                            for idx, label in enumerate(runner_labels):
                                if str(runner_options[label]) == current_reader_id:
                                    current_index = idx
                                    break
                            if runner_labels:
                                selected_runner_label = st.selectbox(
                                    "새 읽는 러너",
                                    runner_labels,
                                    index=current_index,
                                    key=f"change_reader_{book_id}",
                                )
                                if st.button("러너 변경 저장", key=f"save_reader_{book_id}"):
                                    ok, message = update_book_reader(book_id, runner_options[selected_runner_label], selected_marathon_id)
                                    st.session_state["library_manage_feedback"] = ("success" if ok else "warning", message)
                                    st.rerun()
                            else:
                                st.warning("등록된 러너가 없습니다.")

                        st.markdown("##### 책장에서 제거")
                        if has_related_records:
                            st.caption("기록이 있는 책은 데이터 꼬임을 막기 위해 책장에서 바로 제거할 수 없습니다.")
                        else:
                            pending_remove_id = st.session_state.get("pending_remove_book_id")
                            if pending_remove_id == book_id:
                                st.warning("정말 이 책을 책장에서 제거할까요?")
                                confirm_col, cancel_col = st.columns(2)
                                with confirm_col:
                                    if st.button("제거 확인", key=f"confirm_remove_book_{book_id}", type="primary"):
                                        ok, message = remove_book_from_library(book_id, selected_marathon_id)
                                        st.session_state.pop("pending_remove_book_id", None)
                                        if ok:
                                            st.session_state["library_manage_feedback"] = ("success", f"《{title}》을 책장에서 제거했습니다.")
                                        else:
                                            st.session_state["library_manage_feedback"] = ("warning", message)
                                        st.rerun()
                                with cancel_col:
                                    if st.button("취소", key=f"cancel_remove_book_{book_id}"):
                                        st.session_state.pop("pending_remove_book_id", None)
                                        st.rerun()
                            else:
                                if st.button("책장에서 제거", key=f"request_remove_book_{book_id}"):
                                    st.session_state["pending_remove_book_id"] = book_id
                                    st.rerun()


def page_today_reading(data: dict) -> None:
    st.title("✍️ 오늘의 독서 기록")
    st.caption("읽은 페이지는 필수로 기록하고, 좋았던 문장은 선택으로 남깁니다. 별점과 감상은 책을 완독했을 때 기록합니다.")

    feedback = st.session_state.pop("today_save_feedback", None)
    if feedback:
        for idx, message in enumerate(feedback):
            if idx == 0:
                st.success(message)
            else:
                st.info(message)

    members_df = read_csv("family_members")
    active_mid = get_active_marathon_id(read_csv("settings"))
    books_df = filter_by_marathon(read_csv("books"), active_mid)
    logs_df = filter_by_marathon(read_csv("reading_logs"), active_mid)
    quotes_df = filter_by_marathon(read_csv("quotes"), active_mid)
    reviews_df = filter_by_marathon(read_csv("reviews"), active_mid)

    if members_df.empty:
        st.warning("러너가 필요합니다. 먼저 샘플 데이터를 생성하거나 러너를 추가해주세요.")
        return
    if books_df.empty:
        st.warning("등록된 책이 없습니다. 먼저 책 검색 / 책 등록 화면에서 책을 추가해주세요.")
        return

    st.markdown("### 1단계. 누가 읽었나요?")
    m_options = member_options(members_df)
    member_label = st.selectbox("러너 선택", list(m_options.keys()), key="today_member_select")
    member_id = m_options[member_label]

    st.markdown("### 2단계. 어떤 책을 읽었나요?")
    all_member_books_options = book_options_for_member(books_df, member_id, reviews_df=reviews_df, include_finished=True)
    if not all_member_books_options:
        st.info("이 러너의 책장에 등록된 책이 없습니다. 먼저 책 검색 / 책 등록 화면에서 책을 추가해주세요.")
        return

    show_finished_books = st.checkbox("완독한 책도 보기", value=False, key=f"today_show_finished_{member_id}")
    member_books_options = book_options_for_member(
        books_df,
        member_id,
        reviews_df=reviews_df,
        include_finished=show_finished_books,
    )
    if not member_books_options:
        st.info("기록할 수 있는 읽는 중인 책이 없습니다. 완독한 책도 보려면 ‘완독한 책도 보기’를 선택해주세요.")
        return

    placeholder_label = "책을 선택하세요"
    book_labels = [placeholder_label] + list(member_books_options.keys())
    book_label = st.selectbox("책", book_labels, key=f"today_book_select_{member_id}")
    if book_label == placeholder_label:
        st.info("기록할 책을 먼저 선택해주세요. 책을 선택하면 페이지 입력과 선택 기록 입력칸이 표시됩니다.")
        return

    book_id = member_books_options[book_label]
    book_title = get_book_title(book_id, books_df)

    last_end_page = get_last_end_page(logs_df, member_id, book_id)
    suggested_start = last_end_page + 1 if last_end_page > 0 else 1
    if last_end_page > 0:
        st.info(f"지난번에 {last_end_page}쪽까지 읽었습니다. 오늘은 {suggested_start}쪽부터 시작할까요?")
    else:
        st.caption("이 책의 첫 기록입니다. 시작 페이지 기본값은 1쪽입니다.")

    st.markdown("### 3단계. 오늘 어디서부터 어디까지 읽었나요?")
    reading_date = st.date_input("날짜", value=date.today(), key=f"today_date_{member_id}_{book_id}")
    record_method = st.radio(
        "기록 방식",
        ["시작/끝 페이지로 계산", "읽은 페이지 수 직접 입력"],
        horizontal=True,
        key=f"today_record_method_{member_id}_{book_id}",
    )

    start_page = 0
    end_page = 0
    pages_read = 0

    if record_method == "시작/끝 페이지로 계산":
        col1, col2, col3 = st.columns(3)
        start_page = col1.number_input(
            "시작 페이지",
            min_value=1,
            step=1,
            value=max(1, suggested_start),
            key=f"today_start_{member_id}_{book_id}",
        )
        default_end = max(int(start_page), int(start_page) + 9)
        end_page = col2.number_input(
            "끝 페이지",
            min_value=1,
            step=1,
            value=default_end,
            key=f"today_end_{member_id}_{book_id}",
        )
        if int(end_page) >= int(start_page):
            pages_read = int(end_page) - int(start_page) + 1
            col3.metric("자동 계산", f"{pages_read}쪽")
        else:
            col3.metric("자동 계산", "확인 필요")
            st.error("끝 페이지는 시작 페이지보다 크거나 같아야 합니다.")
    else:
        pages_read = st.number_input(
            "읽은 페이지 수",
            min_value=1,
            step=1,
            value=10,
            key=f"today_pages_direct_{member_id}_{book_id}",
        )
        col1, col2 = st.columns(2)
        start_page = col1.number_input(
            "시작 페이지 선택 입력",
            min_value=0,
            step=1,
            value=0,
            key=f"today_start_direct_{member_id}_{book_id}",
        )
        end_page = col2.number_input(
            "끝 페이지 선택 입력",
            min_value=0,
            step=1,
            value=0,
            key=f"today_end_direct_{member_id}_{book_id}",
        )
        st.caption("페이지 번호가 없거나 건너뛰어 읽은 경우에는 읽은 페이지 수만 직접 입력해도 됩니다.")

    memo = st.text_area("메모", placeholder="예: 자기 전에 20분 읽음", key=f"today_memo_{member_id}_{book_id}")

    st.markdown("### 4단계. 좋았던 문장이 있나요?")
    add_quote = st.checkbox("좋았던 문장도 남기기", key=f"today_add_quote_{member_id}_{book_id}")
    quote_page = 0
    quote_text = ""
    quote_comment = ""
    if add_quote:
        quote_page = st.number_input("문장 페이지 번호", min_value=0, step=1, value=safe_int(end_page, 0), key=f"today_quote_page_{member_id}_{book_id}")
        quote_text = st.text_area("좋았던 문장", key=f"today_quote_text_{member_id}_{book_id}")
        quote_comment = st.text_area("내 생각", key=f"today_quote_comment_{member_id}_{book_id}")

    st.markdown("### 5단계. 오늘 이 책을 완독했나요?")
    finished = st.checkbox("오늘 이 책을 완독했나요?", key=f"today_finished_{member_id}_{book_id}")
    rating = 5
    one_line_review = ""
    full_review = ""
    finished_date_value = reading_date
    rating_options = {
        "⭐": 1,
        "⭐⭐": 2,
        "⭐⭐⭐": 3,
        "⭐⭐⭐⭐": 4,
        "⭐⭐⭐⭐⭐": 5,
    }
    if finished:
        rating_label = st.radio(
            "별점",
            list(rating_options.keys()),
            index=4,
            horizontal=True,
            key=f"today_rating_stars_{member_id}_{book_id}",
        )
        rating = rating_options[rating_label]
        one_line_review = st.text_input("한 줄 감상", placeholder="이 책을 다 읽고 남기고 싶은 한 문장", key=f"today_one_line_{member_id}_{book_id}")
        full_review = st.text_area("자세한 감상", placeholder="선택 입력", key=f"today_full_review_{member_id}_{book_id}")
        finished_date_value = st.date_input("완독일", value=reading_date, key=f"today_finished_date_{member_id}_{book_id}")
    else:
        st.caption("완독했을 때만 별점과 한 줄 감상을 저장합니다.")

    st.markdown("### 6단계. 저장")
    if st.button("오늘의 기록 저장", type="primary", use_container_width=True, key=f"save_today_{member_id}_{book_id}"):
        if record_method == "시작/끝 페이지로 계산" and int(end_page) < int(start_page):
            st.error("끝 페이지는 시작 페이지보다 크거나 같아야 합니다.")
            return
        if safe_int(pages_read, 0) <= 0:
            st.error("읽은 페이지 수는 1쪽 이상이어야 합니다.")
            return
        if add_quote and not str(quote_text).strip():
            st.error("좋았던 문장을 입력하거나, '좋았던 문장도 남기기' 체크를 해제해주세요.")
            return
        if finished and not str(one_line_review).strip():
            st.error("완독 감상을 저장하려면 한 줄 감상을 입력하거나, '오늘 이 책을 완독했나요?' 체크를 해제해주세요.")
            return

        member_row = members_df[members_df["member_id"] == member_id].iloc[0]
        weight = safe_float(member_row["weight"], 1.0)
        log_row = {
            "log_id": make_id("log"),
            "marathon_id": active_mid,
            "member_id": member_id,
            "book_id": book_id,
            "reading_date": reading_date.isoformat(),
            "pages_read": safe_int(pages_read, 0),
            "weighted_pages": round(safe_int(pages_read, 0) * weight, 1),
            "start_page": safe_int(start_page, 0),
            "end_page": safe_int(end_page, 0),
            "memo": memo,
            "created_at": now_str(),
        }
        original_logs_df = read_csv("reading_logs")
        original_logs_df = pd.concat([original_logs_df, pd.DataFrame([log_row])], ignore_index=True)
        write_csv("reading_logs", original_logs_df)

        saved_quote = False
        if add_quote:
            quote_row = {
                "quote_id": make_id("quote"),
                "marathon_id": active_mid,
                "member_id": member_id,
                "book_id": book_id,
                "page_number": safe_int(quote_page, 0),
                "quote_text": str(quote_text).strip(),
                "comment": quote_comment,
                "created_at": now_str(),
            }
            original_quotes_df = read_csv("quotes")
            original_quotes_df = pd.concat([original_quotes_df, pd.DataFrame([quote_row])], ignore_index=True)
            write_csv("quotes", original_quotes_df)
            saved_quote = True

        saved_review = False
        if finished:
            review_row = {
                "review_id": make_id("review"),
                "marathon_id": active_mid,
                "member_id": member_id,
                "book_id": book_id,
                "rating": safe_int(rating, 5),
                "one_line_review": str(one_line_review).strip(),
                "full_review": full_review,
                "finished_date": finished_date_value.isoformat(),
                "created_at": now_str(),
            }
            original_reviews_df = read_csv("reviews")
            original_reviews_df = pd.concat([original_reviews_df, pd.DataFrame([review_row])], ignore_index=True)
            write_csv("reviews", original_reviews_df)
            saved_review = True

        messages = [
            "오늘의 독서 기록을 저장했습니다.",
            f"읽은 페이지 {safe_int(pages_read, 0)}쪽이 반영되었습니다.",
        ]
        if saved_quote:
            messages.append("좋았던 문장도 함께 저장했습니다.")
        if saved_review:
            messages.append("완독 감상과 별점을 저장했습니다.")
        st.session_state["today_save_feedback"] = messages
        clear_today_form_state(member_id, book_id)
        st.rerun()


def render_reading_logs_tab(members_df: pd.DataFrame, books_df: pd.DataFrame, marathon_id: str | None = None) -> None:
    delete_feedback = st.session_state.pop("reading_log_delete_feedback", None)
    if delete_feedback:
        st.success(delete_feedback)

    raw_logs_df = read_csv("reading_logs")
    if marathon_id:
        raw_logs_df = filter_by_marathon(raw_logs_df, marathon_id)
    logs_df = enrich_logs(raw_logs_df, members_df, books_df)
    if logs_df.empty:
        st.write("아직 입력된 독서 기록이 없습니다.")
        return

    view = logs_df.sort_values("created_at", ascending=False)
    for row in view.itertuples():
        with st.container(border=True):
            cols = st.columns([1.2, 1.5, 2.2, 1.3, 1.2, 2.2, 1.3])
            with cols[0]:
                st.markdown(f"**{row.reading_date}**")
            with cols[1]:
                st.write(row.member_name)
            with cols[2]:
                st.markdown(f"**{row.book_title}**")
            with cols[3]:
                st.write(f"{safe_int(row.pages_read)}쪽")
                st.caption(f"가중 {safe_float(row.weighted_pages):.1f}쪽")
            with cols[4]:
                start_page = safe_int(row.start_page, 0)
                end_page = safe_int(row.end_page, 0)
                if start_page or end_page:
                    st.write(f"{start_page}~{end_page}쪽")
                else:
                    st.caption("범위 없음")
            with cols[5]:
                memo_text = str(row.memo or "").strip()
                st.write(memo_text if memo_text else "메모 없음")
            with cols[6]:
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
                    if st.button("이 기록 삭제", key=f"delete_log_{row.log_id}"):
                        st.session_state["pending_delete_log_id"] = str(row.log_id)
                        st.rerun()


def render_quotes_tab(members_df: pd.DataFrame, books_df: pd.DataFrame, marathon_id: str | None = None) -> None:
    delete_feedback = st.session_state.pop("quote_delete_feedback", None)
    if delete_feedback:
        st.success(delete_feedback)

    quotes_df = read_csv("quotes")
    if marathon_id:
        quotes_df = filter_by_marathon(quotes_df, marathon_id)
    if quotes_df.empty:
        st.write("아직 저장된 문장이 없습니다.")
        return

    st.caption("잘못 남긴 문장은 삭제할 수 있습니다. 문장을 삭제하면 가족 책장의 책장 관리 상태도 다시 계산됩니다.")
    for row in quotes_df.sort_values("created_at", ascending=False).itertuples():
        with st.container(border=True):
            content_col, action_col = st.columns([5, 1.4])
            with content_col:
                st.markdown(f"> {row.quote_text}")
                st.caption(
                    f"작성자: {get_member_name(row.member_id, members_df)} · "
                    f"책: 《{get_book_title(row.book_id, books_df)}》 · "
                    f"p.{safe_int(row.page_number, 0)} · 작성일 {row.created_at}"
                )
                comment = str(row.comment or "").strip()
                if comment:
                    st.write(comment)
            with action_col:
                pending_delete_id = st.session_state.get("pending_delete_quote_id")
                if pending_delete_id == str(row.quote_id):
                    st.warning("정말 이 문장을 삭제할까요?")
                    if st.button("삭제 확인", key=f"confirm_delete_quote_{row.quote_id}"):
                        original_quotes = read_csv("quotes")
                        updated_quotes = original_quotes[original_quotes["quote_id"].astype(str) != str(row.quote_id)].copy()
                        write_csv("quotes", updated_quotes)
                        st.session_state.pop("pending_delete_quote_id", None)
                        st.session_state["quote_delete_feedback"] = "좋았던 문장을 삭제했습니다. 가족 책장 관리 상태가 다시 계산됩니다."
                        st.rerun()
                    if st.button("취소", key=f"cancel_delete_quote_{row.quote_id}"):
                        st.session_state.pop("pending_delete_quote_id", None)
                        st.rerun()
                else:
                    if st.button("문장 삭제", key=f"delete_quote_{row.quote_id}"):
                        st.session_state["pending_delete_quote_id"] = str(row.quote_id)
                        st.rerun()


def render_reviews_tab(members_df: pd.DataFrame, books_df: pd.DataFrame, marathon_id: str | None = None) -> None:
    delete_feedback = st.session_state.pop("review_delete_feedback", None)
    if delete_feedback:
        st.success(delete_feedback)

    reviews_df = read_csv("reviews")
    if marathon_id:
        reviews_df = filter_by_marathon(reviews_df, marathon_id)
    if reviews_df.empty:
        st.write("아직 저장된 감상이 없습니다.")
        return

    st.caption("잘못 남긴 완독 감상은 삭제할 수 있습니다. 감상을 삭제하면 가족 책장의 완독 상태와 책장 관리 상태도 다시 계산됩니다.")
    for row in reviews_df.sort_values("created_at", ascending=False).itertuples():
        with st.container(border=True):
            content_col, action_col = st.columns([5, 1.4])
            with content_col:
                st.markdown(f"#### {'⭐' * safe_int(row.rating, 0)} 《{get_book_title(row.book_id, books_df)}》")
                st.write(row.one_line_review)
                full_review = str(row.full_review or "").strip()
                if full_review:
                    st.caption(full_review)
                finished_date = str(row.finished_date or "").strip()
                finished_text = f"완독일 {finished_date}" if finished_date else "완독일 미입력"
                st.caption(f"작성자: {get_member_name(row.member_id, members_df)} · {finished_text} · 작성일 {row.created_at}")
            with action_col:
                pending_delete_id = st.session_state.get("pending_delete_review_id")
                if pending_delete_id == str(row.review_id):
                    st.warning("정말 이 감상을 삭제할까요?")
                    if st.button("삭제 확인", key=f"confirm_delete_review_{row.review_id}"):
                        original_reviews = read_csv("reviews")
                        updated_reviews = original_reviews[original_reviews["review_id"].astype(str) != str(row.review_id)].copy()
                        write_csv("reviews", updated_reviews)
                        st.session_state.pop("pending_delete_review_id", None)
                        st.session_state["review_delete_feedback"] = "완독 감상을 삭제했습니다. 가족 책장 상태와 리포트가 다시 계산됩니다."
                        st.rerun()
                    if st.button("취소", key=f"cancel_delete_review_{row.review_id}"):
                        st.session_state.pop("pending_delete_review_id", None)
                        st.rerun()
                else:
                    if st.button("감상 삭제", key=f"delete_review_{row.review_id}"):
                        st.session_state["pending_delete_review_id"] = str(row.review_id)
                        st.rerun()


def page_records(data: dict) -> None:
    st.title("🗂️ 기록 모아보기")
    st.caption("선택한 독서마라톤의 독서 기록, 좋았던 문장, 한 줄 감상을 한곳에서 확인합니다.")

    settings_df = read_csv("settings")
    marathon_options = get_marathon_options(settings_df)
    active_mid = get_active_marathon_id(settings_df)
    option_values = list(marathon_options.values())
    default_index = option_values.index(active_mid) if active_mid in option_values else 0
    selected_label = st.selectbox("보기 기준", list(marathon_options.keys()), index=default_index, key="records_marathon_select")
    selected_mid = marathon_options[selected_label]

    members_df = read_csv("family_members")
    books_df = filter_by_marathon(read_csv("books"), selected_mid)
    tab_logs, tab_quotes, tab_reviews = st.tabs(["독서 기록", "좋았던 문장", "한 줄 감상"])
    with tab_logs:
        render_reading_logs_tab(members_df, books_df, selected_mid)
    with tab_quotes:
        render_quotes_tab(members_df, books_df, selected_mid)
    with tab_reviews:
        render_reviews_tab(members_df, books_df, selected_mid)


def page_monthly_report(data: dict) -> None:
    st.title("📊 월간 리포트")
    st.caption("선택한 독서마라톤 기준으로 가족 독서 기록을 정리합니다.")

    settings_df = read_csv("settings")
    marathon_options = get_marathon_options(settings_df)
    active_mid = get_active_marathon_id(settings_df)
    option_values = list(marathon_options.values())
    default_index = option_values.index(active_mid) if active_mid in option_values else 0
    selected_label = st.selectbox("리포트 기준", list(marathon_options.keys()), index=default_index, key="report_marathon_select")
    selected_mid = marathon_options[selected_label]
    selected_settings = get_marathon_by_id(settings_df, selected_mid)

    scoped_data = scoped_data_for_marathon(load_all_data(), selected_mid)
    summary = calculate_summary(scoped_data)
    summary["settings"] = selected_settings
    logs_df = summary["logs"]
    members_df = scoped_data["family_members"]
    books_df = scoped_data["books"]
    reviews_df = scoped_data["reviews"]
    quotes_df = scoped_data["quotes"]

    month_total = float(logs_df["weighted_pages"].sum()) if not logs_df.empty else 0.0
    target = safe_int(selected_settings.get("family_target_pages"), 0)
    rate = month_total / target * 100 if target > 0 else 0
    stats = get_member_stats(logs_df, members_df)

    top_reader = stats.iloc[0]["member_name"] if not stats.empty and stats.iloc[0]["weighted_pages"] > 0 else "아직 없음"
    steady = stats.sort_values(["record_days", "weighted_pages"], ascending=False).iloc[0]["member_name"] if not stats.empty and stats["record_days"].max() > 0 else "아직 없음"

    finished_reviews = reviews_df[reviews_df["finished_date"].astype(str).str.strip().str.len() > 0] if not reviews_df.empty else reviews_df
    finished_books = [get_book_title(book_id, books_df) for book_id in finished_reviews["book_id"].dropna().unique()] if not finished_reviews.empty else []

    quote_text = "아직 선정된 문장이 없습니다."
    if not quotes_df.empty:
        quote_text = str(quotes_df.sort_values("created_at", ascending=False).iloc[0]["quote_text"])

    st.info(f"{selected_settings['marathon_name']} · {selected_settings['start_date']} ~ {selected_settings['end_date']}")
    col1, col2, col3 = st.columns(3)
    col1.metric("마라톤 총 페이지", f"{month_total:,.1f}")
    col2.metric("목표 달성률", f"{rate:.1f}%")
    col3.metric("완독한 책", f"{len(finished_books)}권")

    st.subheader("러너별 누적 페이지")
    if stats.empty:
        st.write("데이터가 없습니다.")
    else:
        st.dataframe(stats.rename(columns={"member_name": "러너", "pages_read": "실제 페이지", "weighted_pages": "가중치 페이지", "record_days": "기록일 수"})[["러너", "실제 페이지", "가중치 페이지", "기록일 수"]], use_container_width=True, hide_index=True)

    st.subheader("마라톤 요약")
    finished_text = ", ".join(finished_books) if finished_books else "아직 완독 기록은 없습니다"
    auto_summary = (
        f"이번 독서마라톤에서 우리 가족은 총 {month_total:,.1f}페이지를 읽었습니다. "
        f"목표 {target:,}페이지 중 {rate:.1f}%를 달성했습니다. "
        f"가장 많이 보탠 러너는 {top_reader}이고, 가장 꾸준히 기록한 러너는 {steady}입니다. "
        f"완독한 책은 {finished_text}. 이 마라톤의 문장은 ‘{quote_text}’입니다."
    )
    st.success(auto_summary)

    with st.container(border=True):
        st.markdown("#### 🏅 리포트 상세")
        st.write(f"- 가장 많이 보탠 러너: **{top_reader}**")
        st.write(f"- 가장 꾸준히 기록한 러너: **{steady}**")
        st.write(f"- 완독한 책: **{finished_text}**")
        st.write(f"- 이 마라톤의 문장: “{quote_text}”")

def page_settings(data: dict) -> None:
    st.title("⚙️ 마라톤 설정 / 러너 관리")
    st.caption("가족 구성원을 러너로 등록해 독서마라톤에 함께 참여할 수 있습니다.")
    settings_df = read_csv("settings")
    settings = get_active_marathon(settings_df)

    with st.expander("🛠️ 개발/시연용 도구", expanded=False):
        st.caption("발표 시연이나 초기 테스트가 필요할 때만 사용하세요. 기존 CSV 데이터가 샘플 데이터로 초기화됩니다.")
        st.warning("샘플 데이터 생성 / 전체 초기화는 기존 기록을 덮어쓰는 개발·시연용 기능입니다. 실제 사용 중 새 달을 시작할 때는 아래의 '새 독서마라톤 시작' 기능을 사용해주세요.")
        if st.button("🎁 샘플 데이터 생성 / 전체 초기화", type="primary", key="settings_create_sample_data"):
            create_sample_data()
            st.success("샘플 데이터가 생성되었습니다. 왼쪽 메뉴나 새로고침으로 화면을 확인해주세요.")
            st.rerun()

    st.subheader("🏁 현재 진행 중인 독서마라톤")
    st.info(f"{settings['marathon_name']} · {settings['start_date']} ~ {settings['end_date']}")
    with st.form("settings_form"):
        marathon_name = st.text_input("마라톤 이름", value=settings["marathon_name"])
        start_date = st.date_input("시작일", value=pd.to_datetime(settings["start_date"]).date())
        end_date = st.date_input("종료일", value=pd.to_datetime(settings["end_date"]).date())
        family_target_pages = st.number_input("가족 목표 페이지", min_value=1, step=100, value=safe_int(settings["family_target_pages"], 2000))
        unit_name = st.text_input("단위명", value=settings["unit_name"])
        submitted = st.form_submit_button("현재 마라톤 설정 저장")
    if submitted:
        latest_settings = read_csv("settings")
        active_id = settings["marathon_id"]
        mask = latest_settings["marathon_id"].astype(str) == str(active_id)
        if not mask.any():
            st.warning("수정할 active 마라톤을 찾지 못했습니다.")
        else:
            latest_settings.loc[mask, "marathon_name"] = marathon_name
            latest_settings.loc[mask, "start_date"] = start_date.isoformat()
            latest_settings.loc[mask, "end_date"] = end_date.isoformat()
            latest_settings.loc[mask, "family_target_pages"] = family_target_pages
            latest_settings.loc[mask, "unit_name"] = unit_name
            write_csv("settings", latest_settings)
            st.success("현재 독서마라톤 설정을 저장했습니다.")
            st.rerun()

    st.subheader("🆕 새 독서마라톤 시작")
    st.caption("기존 기록은 보존하고, 새 목표와 새 책장으로 다음 독서마라톤을 시작합니다. 러너 정보는 그대로 유지됩니다.")
    st.info("기본값은 가족 월간 목표 2,000쪽입니다. 성인은 월 2권을 기본 페이스, 월 4권은 주 1권 챌린지로 생각하면 좋습니다.")
    marathon_defaults = get_next_marathon_defaults(settings_df)
    with st.form("new_marathon_form"):
        new_name = st.text_input("새 마라톤 이름", value=marathon_defaults["name"])
        c1, c2 = st.columns(2)
        new_start = c1.date_input("시작일", value=marathon_defaults["start_date"], key="new_marathon_start")
        new_end_default = (pd.Timestamp(new_start) + pd.offsets.MonthEnd(0)).date()
        new_end = c2.date_input("종료일", value=new_end_default, key="new_marathon_end")
        new_target = st.number_input("가족 목표 페이지", min_value=1, step=100, value=marathon_defaults["target"], key="new_marathon_target")
        new_unit = st.text_input("단위명", value=marathon_defaults["unit"], key="new_marathon_unit")
        new_submitted = st.form_submit_button("새 마라톤 시작하기", type="primary")
    if new_submitted:
        if new_end < new_start:
            st.error("종료일은 시작일보다 빠를 수 없습니다.")
        else:
            new_id = start_new_marathon(new_name, new_start, new_end, new_target, new_unit)
            st.success(f"새 독서마라톤을 시작했습니다. 새 마라톤 ID: {new_id}")
            st.rerun()

    with st.expander("📚 보존된 독서마라톤 목록 / 선택 / 삭제", expanded=False):
        marathon_list = read_csv("settings")
        if marathon_list.empty:
            st.write("아직 저장된 마라톤이 없습니다.")
        else:
            display_df = marathon_list.copy()
            display_df["상태"] = display_df["is_active"].apply(lambda x: "진행 중" if normalize_bool(x) else "보관")
            st.dataframe(
                display_df.rename(columns={
                    "marathon_name": "마라톤 이름",
                    "start_date": "시작일",
                    "end_date": "종료일",
                    "family_target_pages": "목표 페이지",
                    "unit_name": "단위",
                })[["상태", "마라톤 이름", "시작일", "종료일", "목표 페이지", "단위"]],
                use_container_width=True,
                hide_index=True,
            )
            marathon_options = get_marathon_options(marathon_list)
            active_mid = get_active_marathon_id(marathon_list)
            labels = list(marathon_options.keys())
            values = list(marathon_options.values())
            default_idx = values.index(active_mid) if active_mid in values else 0
            selected_label = st.selectbox("관리할 독서마라톤 선택", labels, index=default_idx, key="manage_marathon_select")
            selected_mid = marathon_options[selected_label]
            selected_is_active = selected_mid == active_mid
            c1, c2 = st.columns(2)
            if c1.button("이 마라톤을 진행 중으로 선택", disabled=selected_is_active, key="set_active_marathon_button"):
                set_active_marathon(selected_mid)
                st.success("선택한 독서마라톤을 현재 진행 중으로 변경했습니다.")
                st.rerun()

            delete_key = "pending_delete_marathon_id"
            pending_delete_mid = st.session_state.get(delete_key)
            if pending_delete_mid == selected_mid:
                st.warning("정말 이 독서마라톤을 삭제할까요? 러너는 유지되지만, 이 마라톤의 책장·독서 기록·문장·완독 감상은 함께 삭제됩니다.")
                d1, d2 = st.columns(2)
                if d1.button("삭제 확인", key="confirm_delete_marathon", type="primary"):
                    result = delete_marathon_and_related_data(selected_mid)
                    st.session_state.pop(delete_key, None)
                    if result.get("error"):
                        st.error(result["error"])
                    else:
                        st.success(
                            f"독서마라톤을 삭제했습니다. 함께 정리된 항목: "
                            f"책장 {result['books']}개, 독서 기록 {result['logs']}개, "
                            f"좋았던 문장 {result['quotes']}개, 완독 감상 {result['reviews']}개"
                        )
                    st.rerun()
                if d2.button("취소", key="cancel_delete_marathon"):
                    st.session_state.pop(delete_key, None)
                    st.info("독서마라톤 삭제를 취소했습니다.")
                    st.rerun()
            else:
                if c2.button("이 마라톤 삭제", key="request_delete_marathon"):
                    st.session_state[delete_key] = selected_mid
                    st.rerun()

    st.subheader("🏃 새 러너 추가")
    st.caption("러너 유형에 따라 기본 가중치가 제안됩니다. 가중치는 필요하면 직접 수정할 수 있습니다.")
    new_runner_age = st.selectbox("러너 유형", AGE_GROUP_OPTIONS, index=0, key="new_runner_age_group_select")
    with st.form("member_form"):
        col1, col2 = st.columns(2)
        name = col1.text_input("러너 이름")
        avatar = col2.selectbox("이모지/avatar", EMOJI_OPTIONS, index=0)
        role = st.text_input("역할", placeholder="예: 기록왕, 그림책 러너")
        age_group = new_runner_age
        weight = st.number_input(
            "가중치",
            min_value=0.1,
            max_value=5.0,
            step=0.1,
            value=float(recommended_weight(age_group)),
            key=f"new_runner_weight_{age_group}",
            help="기본값: 성인 1.0, 청소년 1.1, 어린이 1.4, 유아 2.0",
        )
        member_submit = st.form_submit_button("새 러너 추가")
    if member_submit:
        if not name.strip():
            st.error("러너 이름을 입력해주세요.")
        else:
            row = {
                "member_id": make_id("member"),
                "name": name.strip(),
                "role": role.strip(),
                "age_group": age_group,
                "weight": weight,
                "avatar": avatar,
                "created_at": now_str(),
            }
            members_df = pd.concat([read_csv("family_members"), pd.DataFrame([row])], ignore_index=True)
            write_csv("family_members", members_df)
            st.success("새 러너를 추가했습니다.")
            st.rerun()

    st.subheader("🏃 현재 함께 달리는 러너")
    members_df = read_csv("family_members")
    if members_df.empty:
        st.write("아직 등록된 러너가 없습니다.")
    else:
        st.dataframe(members_df[["avatar", "name", "role", "age_group", "weight"]], use_container_width=True, hide_index=True)
        st.caption("러너 정보를 수정하면 홈 대시보드, 책장, 오늘의 독서 기록 화면에 바로 반영됩니다.")
        for _, member in members_df.iterrows():
            member_id = str(member.get("member_id", ""))
            current_avatar = str(member.get("avatar", "") or "👨").strip()
            avatar_options = emoji_options_with_current(current_avatar)
            current_index = avatar_options.index(current_avatar) if current_avatar in avatar_options else 0
            with st.expander(f"{current_avatar} {member.get('name', '러너')} 러너 정보 수정", expanded=False):
                with st.form(f"edit_member_form_{member_id}"):
                    col1, col2 = st.columns(2)
                    edited_name = col1.text_input("이름", value=str(member.get("name", "")), key=f"edit_name_{member_id}")
                    edited_avatar = col2.selectbox("이모지/avatar", avatar_options, index=current_index, key=f"edit_avatar_{member_id}")
                    edited_role = st.text_input("역할", value=str(member.get("role", "")), key=f"edit_role_{member_id}")
                    age_options = AGE_GROUP_OPTIONS
                    current_age = normalize_age_group(member.get("age_group", "성인"))
                    edited_age_group = st.selectbox(
                        "러너 유형",
                        age_options,
                        index=age_options.index(current_age) if current_age in age_options else 0,
                        key=f"edit_age_group_{member_id}",
                    )
                    edited_weight = st.number_input(
                        "가중치",
                        min_value=0.1,
                        max_value=5.0,
                        step=0.1,
                        value=safe_float(member.get("weight", 1.0), 1.0),
                        key=f"edit_weight_{member_id}",
                    )
                    edit_submitted = st.form_submit_button("러너 정보 저장")
                if edit_submitted:
                    if not edited_name.strip():
                        st.error("러너 이름을 입력해주세요.")
                    else:
                        latest_members = read_csv("family_members")
                        mask = latest_members["member_id"].astype(str) == member_id
                        if not mask.any():
                            st.warning("수정할 러너를 찾지 못했습니다.")
                        else:
                            latest_members.loc[mask, "name"] = edited_name.strip()
                            latest_members.loc[mask, "avatar"] = edited_avatar
                            latest_members.loc[mask, "role"] = edited_role.strip()
                            latest_members.loc[mask, "age_group"] = edited_age_group
                            latest_members.loc[mask, "weight"] = edited_weight
                            write_csv("family_members", latest_members)
                            st.success("러너 정보를 저장했습니다.")
                            st.rerun()

                st.divider()
                st.markdown("**러너 삭제**")
                st.caption("테스트로 추가한 러너를 정리할 수 있습니다. 삭제하면 해당 러너의 책장, 독서 기록, 좋았던 문장, 완독 감상도 함께 삭제됩니다.")
                delete_state_key = "pending_delete_runner_id"
                pending_delete_id = st.session_state.get(delete_state_key)

                if pending_delete_id == member_id:
                    st.warning(f"정말 {current_avatar} {member.get('name', '러너')} 러너를 삭제할까요? 이 작업은 되돌릴 수 없습니다.")
                    c1, c2 = st.columns(2)
                    if c1.button("삭제 확인", key=f"confirm_delete_member_{member_id}", type="primary"):
                        result = delete_runner_and_related_data(member_id)
                        st.session_state.pop(delete_state_key, None)
                        st.success(
                            f"러너를 삭제했습니다. "
                            f"함께 정리된 항목: 책장 {result['books']}개, 독서 기록 {result['logs']}개, "
                            f"좋았던 문장 {result['quotes']}개, 완독 감상 {result['reviews']}개"
                        )
                        st.rerun()
                    if c2.button("취소", key=f"cancel_delete_member_{member_id}"):
                        st.session_state.pop(delete_state_key, None)
                        st.info("러너 삭제를 취소했습니다.")
                        st.rerun()
                else:
                    if st.button("이 러너 삭제", key=f"request_delete_member_{member_id}"):
                        st.session_state[delete_state_key] = member_id
                        st.rerun()

    st.subheader("국립중앙도서관 페이지 수 조회 테스트")
    st.caption("선택 기능입니다. 책장 추가 시에는 자동 호출하지 않으며, 이 테스트 버튼을 눌렀을 때만 5초 이내 timeout으로 수동 조회합니다.")
    with st.expander("개발자용 수동 테스트", expanded=False):
        test_isbn = st.text_input("테스트 ISBN", placeholder="예: 978-8954677158", key="nlk_manual_test_isbn")
        if st.button("국립중앙도서관 페이지 수 조회 테스트", key="nlk_manual_test_button"):
            result = fetch_book_pages_by_isbn_nlk(test_isbn)
            status = result.get("status", "unknown")
            pages = result.get("pages")
            message = result.get("message", "")
            if status == "success" and pages:
                st.success(f"조회 성공: 전체 페이지 수 {int(pages)}쪽")
            elif status == "no_key":
                st.warning("NLK_CERT_KEY가 없어 조회하지 못했습니다.")
            elif status == "timeout":
                st.warning("연결 시간 초과: 현재 네트워크에서는 국립중앙도서관 API 응답을 받지 못했습니다.")
                st.caption("책 등록 기능에는 영향이 없습니다.")
            else:
                st.warning(message or "페이지 수를 확인하지 못했습니다.")
                st.caption("책 등록 기능에는 영향이 없습니다.")
            debug = result.get("debug", {}) or {}
            safe_debug = {k: v for k, v in debug.items() if k != "response_preview"}
            if safe_debug or debug.get("response_preview"):
                with st.expander("개발 확인", expanded=False):
                    if safe_debug:
                        st.caption(str(safe_debug))
                    if debug.get("response_preview"):
                        st.text_area("응답 미리보기", value=str(debug.get("response_preview"))[:1000], height=160, disabled=True)


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="📚", layout="wide")
    ensure_csv_files()
    migrate_data_schema()
    data = load_all_data()

    with st.sidebar:
        st.title("📚 독서마라톤")
        page = st.radio(
            "메뉴",
            ["홈 / 대시보드", "책 검색 / 책 등록", "가족 책장", "오늘의 독서 기록", "기록 모아보기", "월간 리포트", "설정 / 러너 관리"],
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
    elif page == "오늘의 독서 기록":
        page_today_reading(data)
    elif page == "기록 모아보기":
        page_records(data)
    elif page == "월간 리포트":
        page_monthly_report(data)
    elif page == "설정 / 러너 관리":
        page_settings(data)


if __name__ == "__main__":
    main()
