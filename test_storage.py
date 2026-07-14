"""CSV와 Supabase 읽기 결과 비교 테스트.

실행:
    python test_storage.py

필요 환경변수:
    SUPABASE_URL
    SUPABASE_KEY

STORAGE_BACKEND 값과 무관하게 두 저장소를 모두 직접 생성해 비교합니다.
키 값은 출력하지 않습니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from storage import (
    PRIMARY_KEYS,
    TABLE_COLUMNS,
    CsvStorage,
    StorageError,
    SupabaseStorage,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TABLES = ["settings", "family_members", "books", "reading_logs", "quotes", "reviews"]


def check_columns(table: str, df: pd.DataFrame) -> list[str]:
    return [column for column in TABLE_COLUMNS[table] if column not in df.columns]


def check_duplicate_primary_keys(table: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    primary_key = PRIMARY_KEYS[table]
    return int(df[primary_key].astype(str).duplicated().sum())


def validate_relations(tables: dict[str, pd.DataFrame]) -> list[str]:
    errors: list[str] = []
    marathon_ids = set(tables["settings"]["marathon_id"].astype(str))
    member_ids = set(tables["family_members"]["member_id"].astype(str))
    book_ids = set(tables["books"]["book_id"].astype(str))

    books = tables["books"]
    for row in books.to_dict("records"):
        if str(row.get("marathon_id")) not in marathon_ids:
            errors.append(f"books.{row.get('book_id')}: marathon_id 불일치")
        if str(row.get("reader_member_id")) not in member_ids:
            errors.append(f"books.{row.get('book_id')}: reader_member_id 불일치")

    for table in ["reading_logs", "quotes", "reviews"]:
        pk = PRIMARY_KEYS[table]
        for row in tables[table].to_dict("records"):
            if str(row.get("marathon_id")) not in marathon_ids:
                errors.append(f"{table}.{row.get(pk)}: marathon_id 불일치")
            if str(row.get("member_id")) not in member_ids:
                errors.append(f"{table}.{row.get(pk)}: member_id 불일치")
            if str(row.get("book_id")) not in book_ids:
                errors.append(f"{table}.{row.get(pk)}: book_id 불일치")
    return errors


def normalized_ids(df: pd.DataFrame, primary_key: str) -> set[str]:
    return set(df[primary_key].dropna().astype(str))


def main() -> int:
    print("CSV / Supabase 저장소 읽기 비교")
    print("SUPABASE_URL과 SUPABASE_KEY의 실제 값은 출력하지 않습니다.\n")

    try:
        csv_storage = CsvStorage(DATA_DIR)
        supabase_storage = SupabaseStorage()
    except StorageError as exc:
        print(f"[초기화 실패] {exc}")
        return 1

    csv_tables: dict[str, pd.DataFrame] = {}
    supabase_tables: dict[str, pd.DataFrame] = {}
    failed = False

    for table in TABLES:
        try:
            csv_df = csv_storage.load_table(table)
            supabase_df = supabase_storage.load_table(table)
        except StorageError as exc:
            print(f"[조회 실패] {table}: {exc}")
            failed = True
            continue

        csv_tables[table] = csv_df
        supabase_tables[table] = supabase_df
        missing_csv = check_columns(table, csv_df)
        missing_supabase = check_columns(table, supabase_df)
        duplicate_csv = check_duplicate_primary_keys(table, csv_df)
        duplicate_supabase = check_duplicate_primary_keys(table, supabase_df)
        pk = PRIMARY_KEYS[table]
        same_ids = normalized_ids(csv_df, pk) == normalized_ids(supabase_df, pk)

        print(
            f"- {table}: CSV {len(csv_df)}행 / Supabase {len(supabase_df)}행 / "
            f"ID 동일 {'예' if same_ids else '아니오'}"
        )
        if missing_csv or missing_supabase:
            print(f"  필수 컬럼 누락: CSV={missing_csv}, Supabase={missing_supabase}")
            failed = True
        if duplicate_csv or duplicate_supabase:
            print(f"  PK 중복: CSV={duplicate_csv}, Supabase={duplicate_supabase}")
            failed = True
        if len(csv_df) != len(supabase_df) or not same_ids:
            failed = True

    if len(csv_tables) == len(TABLES):
        csv_relation_errors = validate_relations(csv_tables)
        supabase_relation_errors = validate_relations(supabase_tables)
        if csv_relation_errors:
            print("\n[CSV 관계 오류]")
            for error in csv_relation_errors:
                print(f"- {error}")
            failed = True
        if supabase_relation_errors:
            print("\n[Supabase 관계 오류]")
            for error in supabase_relation_errors:
                print(f"- {error}")
            failed = True

    if failed:
        print("\n비교 테스트에 차이가 있습니다. 위 항목을 확인해주세요.")
        return 1

    print("\nCSV와 Supabase의 행 수, 기본키, 필수 컬럼, 관계가 모두 일치합니다.")
    print("쓰기 작업은 수행하지 않았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
