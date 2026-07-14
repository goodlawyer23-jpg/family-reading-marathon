"""CSV -> Supabase 1회 마이그레이션 도구 초안.

기본 실행은 dry-run입니다.
실제 반영:
    python migrate_csv_to_supabase.py --apply

주의:
- 실행 전 data/ 폴더를 backup/ 아래에 복사합니다.
- 기본키를 포함한 upsert로 재실행 시 중복 삽입을 방지합니다.
- 테이블 순서는 외래키 관계를 고려합니다.
- 여러 테이블을 완전히 원자적으로 반영하려면 이후 Supabase RPC 트랜잭션
  함수를 추가하는 방식을 권장합니다.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backup"

TABLE_CONFIG = {
    "marathons": {
        "csv": "settings.csv",
        "primary_key": "marathon_id",
        "rename": {},
        "text_defaults": {
            "marathon_name": "독서마라톤",
            "unit_name": "페이지",
        },
        "date_columns": ["start_date", "end_date"],
        "timestamp_columns": ["created_at"],
        "integer_columns": ["family_target_pages"],
        "float_columns": [],
        "boolean_columns": ["is_active"],
    },
    "family_members": {
        "csv": "family_members.csv",
        "primary_key": "member_id",
        "rename": {},
        "text_defaults": {
            "name": "",
            "role": "",
            "age_group": "성인",
            "avatar": "🌟",
        },
        "date_columns": [],
        "timestamp_columns": ["created_at"],
        "integer_columns": [],
        "float_columns": ["weight"],
        "boolean_columns": [],
    },
    "books": {
        "csv": "books.csv",
        "primary_key": "book_id",
        "rename": {},
        "text_defaults": {
            "reader_member_id": "",
            "title": "",
            "author": "",
            "publisher": "",
            "isbn": "",
            "image_url": "",
            "description": "",
            "source_api": "manual",
        },
        "date_columns": ["pubdate"],
        "timestamp_columns": ["created_at"],
        "integer_columns": ["total_pages"],
        "float_columns": [],
        "boolean_columns": [],
    },
    "reading_logs": {
        "csv": "reading_logs.csv",
        "primary_key": "log_id",
        "rename": {},
        "text_defaults": {
            "memo": "",
        },
        "date_columns": ["reading_date"],
        "timestamp_columns": ["created_at"],
        "integer_columns": ["pages_read", "start_page", "end_page"],
        "float_columns": ["weighted_pages"],
        "boolean_columns": [],
    },
    "quotes": {
        "csv": "quotes.csv",
        "primary_key": "quote_id",
        "rename": {},
        "text_defaults": {
            "quote_text": "",
            "comment": "",
        },
        "date_columns": [],
        "timestamp_columns": ["created_at"],
        "integer_columns": ["page_number"],
        "float_columns": [],
        "boolean_columns": [],
    },
    "reviews": {
        "csv": "reviews.csv",
        "primary_key": "review_id",
        "rename": {},
        "text_defaults": {
            "one_line_review": "",
            "full_review": "",
        },
        "date_columns": ["finished_date"],
        "timestamp_columns": ["created_at"],
        "integer_columns": [],
        "float_columns": ["rating"],
        "boolean_columns": [],
    },
}

MIGRATION_ORDER = [
    "marathons",
    "family_members",
    "books",
    "reading_logs",
    "quotes",
    "reviews",
]


def create_client_from_env() -> Client:
    load_dotenv()
    url = str(os.getenv("SUPABASE_URL", "") or "").strip()
    key = str(os.getenv("SUPABASE_KEY", "") or "").strip()
    if not url or not key:
        raise RuntimeError(".env에 SUPABASE_URL과 SUPABASE_KEY를 설정해주세요.")
    return create_client(url, key)


def backup_csv_files() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"csv_before_supabase_{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"data 폴더가 없습니다: {DATA_DIR}")
    for path in DATA_DIR.glob("*.csv"):
        shutil.copy2(path, target / path.name)
    return target


def read_csv_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    path = DATA_DIR / config["csv"]
    if not path.exists():
        raise FileNotFoundError(f"CSV 파일이 없습니다: {path}")

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="utf-8")
    except pd.errors.EmptyDataError:
        return []

    df = df.rename(columns=config.get("rename", {}))
    rows: list[dict[str, Any]] = []

    for raw in df.to_dict("records"):
        row: dict[str, Any] = {}
        text_defaults = config.get("text_defaults", {})
        for key, value in raw.items():
            if pd.isna(value) or value == "":
                if key in text_defaults:
                    row[key] = text_defaults[key]
                else:
                    row[key] = None
            else:
                row[key] = value

        for col in config.get("integer_columns", []):
            if row.get(col) is not None:
                row[col] = int(float(row[col]))

        for col in config.get("float_columns", []):
            if row.get(col) is not None:
                row[col] = float(row[col])

        for col in config.get("boolean_columns", []):
            value = row.get(col)
            if value is not None:
                row[col] = str(value).strip().lower() in {"true", "1", "yes", "y", "active", "활성"}

        for col in config.get("date_columns", []):
            value = row.get(col)
            if value is not None:
                parsed = pd.to_datetime(value, errors="coerce")
                row[col] = None if pd.isna(parsed) else parsed.date().isoformat()

        for col in config.get("timestamp_columns", []):
            value = row.get(col)
            if value is not None:
                parsed = pd.to_datetime(value, errors="coerce")
                row[col] = None if pd.isna(parsed) else parsed.isoformat()

        rows.append(row)

    # NOT NULL 텍스트 컬럼은 빈 CSV 셀을 None이 아니라 지정된 기본 문자열로 유지합니다.
    return rows


def validate_relations(all_rows: dict[str, list[dict[str, Any]]]) -> list[str]:
    errors: list[str] = []

    marathon_ids = {str(r["marathon_id"]) for r in all_rows["marathons"] if r.get("marathon_id")}
    member_ids = {str(r["member_id"]) for r in all_rows["family_members"] if r.get("member_id")}
    book_ids = {str(r["book_id"]) for r in all_rows["books"] if r.get("book_id")}

    for row in all_rows["books"]:
        if str(row.get("marathon_id")) not in marathon_ids:
            errors.append(f"books.{row.get('book_id')}: 존재하지 않는 marathon_id")
        if str(row.get("reader_member_id")) not in member_ids:
            errors.append(f"books.{row.get('book_id')}: 존재하지 않는 reader_member_id")

    for table in ["reading_logs", "quotes", "reviews"]:
        id_field = TABLE_CONFIG[table]["primary_key"]
        for row in all_rows[table]:
            if str(row.get("marathon_id")) not in marathon_ids:
                errors.append(f"{table}.{row.get(id_field)}: 존재하지 않는 marathon_id")
            if str(row.get("member_id")) not in member_ids:
                errors.append(f"{table}.{row.get(id_field)}: 존재하지 않는 member_id")
            if str(row.get("book_id")) not in book_ids:
                errors.append(f"{table}.{row.get(id_field)}: 존재하지 않는 book_id")

    return errors


def print_preview(all_rows: dict[str, list[dict[str, Any]]]) -> None:
    print("CSV -> Supabase 마이그레이션 미리보기")
    for table in MIGRATION_ORDER:
        rows = all_rows[table]
        pk = TABLE_CONFIG[table]["primary_key"]
        sample_ids = [str(r.get(pk)) for r in rows[:3]]
        print(f"- {table}: {len(rows)}행 / 예시 ID: {sample_ids}")


def upsert_in_chunks(
    client: Client,
    table: str,
    rows: list[dict[str, Any]],
    primary_key: str,
    chunk_size: int = 100,
) -> None:
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        if not chunk:
            continue
        client.table(table).upsert(chunk, on_conflict=primary_key).execute()
        print(f"  {table}: {min(start + len(chunk), len(rows))}/{len(rows)}행")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제로 Supabase에 upsert합니다. 생략하면 dry-run입니다.",
    )
    args = parser.parse_args()

    try:
        all_rows = {
            table: read_csv_rows(config)
            for table, config in TABLE_CONFIG.items()
        }
        print_preview(all_rows)

        relation_errors = validate_relations(all_rows)
        if relation_errors:
            print("\n[중단] 외래키 관계 오류:")
            for error in relation_errors[:50]:
                print(f"- {error}")
            return 1

        if not args.apply:
            print("\nDRY-RUN 완료: 데이터베이스에는 아무것도 쓰지 않았습니다.")
            print("실제 반영 명령: python migrate_csv_to_supabase.py --apply")
            return 0

        backup_path = backup_csv_files()
        print(f"\nCSV 백업 완료: {backup_path}")

        client = create_client_from_env()
        print("Supabase 연결 성공. 기본키 기준 upsert를 시작합니다.")

        for table in MIGRATION_ORDER:
            config = TABLE_CONFIG[table]
            upsert_in_chunks(
                client,
                table,
                all_rows[table],
                config["primary_key"],
            )

        print("\n마이그레이션 완료.")
        print("동일 명령을 다시 실행해도 기본키 기준 upsert이므로 중복 행이 생성되지 않습니다.")
        return 0

    except Exception as exc:
        print(f"\n[실패] {exc.__class__.__name__}: {exc}")
        print("CSV 원본은 수정하지 않았습니다.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
