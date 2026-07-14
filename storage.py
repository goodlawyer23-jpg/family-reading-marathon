"""CSV/Supabase 선택형 데이터 저장소.

1차 전환 범위
- CSV: 기존 읽기/쓰기 유지
- Supabase: 읽기 지원
- Supabase 행 단위 CRUD 지원: insert/update/delete/upsert
- 전체 테이블 replace는 데이터 보호를 위해 금지
- Supabase replace_table은 데이터 보호를 위해 금지
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from dotenv import load_dotenv

try:
    import streamlit as st
except Exception:  # test_storage.py 등 비-Streamlit 실행
    st = None


load_dotenv()

TABLE_COLUMNS: dict[str, list[str]] = {
    "settings": [
        "marathon_id", "marathon_name", "start_date", "end_date",
        "family_target_pages", "unit_name", "is_active", "created_at",
    ],
    "family_members": [
        "member_id", "name", "role", "age_group", "weight", "avatar", "created_at",
    ],
    "books": [
        "book_id", "marathon_id", "reader_member_id", "title", "author", "publisher",
        "isbn", "image_url", "description", "pubdate", "total_pages", "source_api", "created_at",
    ],
    "reading_logs": [
        "log_id", "marathon_id", "member_id", "book_id", "reading_date", "pages_read",
        "weighted_pages", "start_page", "end_page", "memo", "created_at",
    ],
    "quotes": [
        "quote_id", "marathon_id", "member_id", "book_id", "page_number",
        "quote_text", "comment", "created_at",
    ],
    "reviews": [
        "review_id", "marathon_id", "member_id", "book_id", "rating",
        "one_line_review", "full_review", "finished_date", "created_at",
    ],
}

CSV_FILE_MAP = {
    "settings": "settings.csv",
    "family_members": "family_members.csv",
    "books": "books.csv",
    "reading_logs": "reading_logs.csv",
    "quotes": "quotes.csv",
    "reviews": "reviews.csv",
}

SUPABASE_TABLE_MAP = {
    "settings": "marathons",
    "family_members": "family_members",
    "books": "books",
    "reading_logs": "reading_logs",
    "quotes": "quotes",
    "reviews": "reviews",
}

PRIMARY_KEYS = {
    "settings": "marathon_id",
    "family_members": "member_id",
    "books": "book_id",
    "reading_logs": "log_id",
    "quotes": "quote_id",
    "reviews": "review_id",
}

ORDER_COLUMNS = {
    "settings": ("start_date", True),
    "family_members": ("created_at", False),
    "books": ("created_at", False),
    "reading_logs": ("reading_date", True),
    "quotes": ("created_at", True),
    "reviews": ("created_at", True),
}


class StorageError(RuntimeError):
    """저장소 연결·조회·쓰기 오류."""


class StorageWriteDisabledError(StorageError):
    """1차 읽기 검증 단계에서 Supabase 쓰기가 호출된 경우."""


def _secret_or_env(name: str, default: str = "") -> str:
    value = str(os.getenv(name, "") or "").strip()
    if value:
        return value
    if st is not None:
        try:
            return str(st.secrets.get(name, default) or "").strip()
        except Exception:
            pass
    return default


def get_backend_name() -> str:
    backend = _secret_or_env("STORAGE_BACKEND", "csv").lower().strip() or "csv"
    if backend not in {"csv", "supabase"}:
        raise StorageError(
            f"지원하지 않는 STORAGE_BACKEND 값입니다: {backend!r}. csv 또는 supabase를 사용해주세요."
        )
    return backend


def normalize_table_key(table_name: str) -> str:
    key = str(table_name or "").strip()
    # 실제 Supabase 테이블명을 내부 key로 전달한 경우도 허용합니다.
    if key == "marathons":
        key = "settings"
    if key not in TABLE_COLUMNS:
        raise StorageError(f"지원하지 않는 테이블입니다: {table_name!r}")
    return key


def normalize_dataframe(table_name: str, df: pd.DataFrame | None) -> pd.DataFrame:
    key = normalize_table_key(table_name)
    result = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    for column in TABLE_COLUMNS[key]:
        if column not in result.columns:
            result[column] = ""
    return result[TABLE_COLUMNS[key]].copy()


class Storage(ABC):
    backend_name: str
    supports_replace_table: bool = False
    app_writes_enabled: bool = False

    @abstractmethod
    def load_table(self, table_name: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def insert_row(self, table_name: str, row: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def update_rows(
        self, table_name: str, filters: dict[str, Any], values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def delete_rows(self, table_name: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def upsert_rows(
        self,
        table_name: str,
        rows: Iterable[dict[str, Any]],
        conflict_column: str,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def replace_table(self, table_name: str, dataframe: pd.DataFrame) -> None:
        raise NotImplementedError


class CsvStorage(Storage):
    backend_name = "csv"
    supports_replace_table = True
    app_writes_enabled = True

    def __init__(self, data_dir: Path | str, default_settings: dict[str, Any] | None = None):
        self.data_dir = Path(data_dir)
        self.default_settings = dict(default_settings or {})
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ensure_files()

    def _path(self, table_name: str) -> Path:
        key = normalize_table_key(table_name)
        return self.data_dir / CSV_FILE_MAP[key]

    def ensure_files(self) -> None:
        for key in TABLE_COLUMNS:
            path = self._path(key)
            if path.exists():
                continue
            if key == "settings" and self.default_settings:
                df = pd.DataFrame([self.default_settings])
            else:
                df = pd.DataFrame(columns=TABLE_COLUMNS[key])
            normalize_dataframe(key, df).to_csv(path, index=False, encoding="utf-8-sig")

    def load_table(self, table_name: str) -> pd.DataFrame:
        key = normalize_table_key(table_name)
        path = self._path(key)
        if not path.exists():
            self.ensure_files()
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="utf-8")
        except pd.errors.EmptyDataError:
            df = pd.DataFrame(columns=TABLE_COLUMNS[key])
        return normalize_dataframe(key, df)

    def replace_table(self, table_name: str, dataframe: pd.DataFrame) -> None:
        key = normalize_table_key(table_name)
        normalize_dataframe(key, dataframe).to_csv(
            self._path(key), index=False, encoding="utf-8-sig"
        )

    def insert_row(self, table_name: str, row: dict[str, Any]) -> list[dict[str, Any]]:
        key = normalize_table_key(table_name)
        df = self.load_table(key)
        updated = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        self.replace_table(key, updated)
        return [dict(row)]

    @staticmethod
    def _mask(df: pd.DataFrame, filters: dict[str, Any]) -> pd.Series:
        mask = pd.Series(True, index=df.index)
        for column, value in filters.items():
            if column not in df.columns:
                raise StorageError(f"CSV에 필터 컬럼이 없습니다: {column}")
            mask &= df[column].astype(str) == str(value)
        return mask

    def update_rows(
        self, table_name: str, filters: dict[str, Any], values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        key = normalize_table_key(table_name)
        df = self.load_table(key)
        mask = self._mask(df, filters)
        for column, value in values.items():
            if column not in df.columns:
                raise StorageError(f"CSV에 수정 컬럼이 없습니다: {column}")
            df.loc[mask, column] = value
        result = df.loc[mask].to_dict("records")
        self.replace_table(key, df)
        return result

    def delete_rows(self, table_name: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        key = normalize_table_key(table_name)
        df = self.load_table(key)
        mask = self._mask(df, filters)
        deleted = df.loc[mask].to_dict("records")
        self.replace_table(key, df.loc[~mask].copy())
        return deleted

    def upsert_rows(
        self,
        table_name: str,
        rows: Iterable[dict[str, Any]],
        conflict_column: str,
    ) -> list[dict[str, Any]]:
        key = normalize_table_key(table_name)
        incoming = list(rows)
        df = self.load_table(key)
        for row in incoming:
            if conflict_column not in row:
                raise StorageError(f"upsert 행에 충돌 컬럼이 없습니다: {conflict_column}")
            mask = df[conflict_column].astype(str) == str(row[conflict_column])
            if mask.any():
                for column, value in row.items():
                    if column in df.columns:
                        df.loc[mask, column] = value
            else:
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        self.replace_table(key, df)
        return incoming


class SupabaseStorage(Storage):
    backend_name = "supabase"
    supports_replace_table = False
    # app.py는 행 단위 CRUD만 사용하며 replace_table은 계속 금지합니다.
    app_writes_enabled = True

    def __init__(self, url: str | None = None, key: str | None = None):
        url = str(url or _secret_or_env("SUPABASE_URL", "")).strip()
        key = str(key or _secret_or_env("SUPABASE_KEY", "")).strip()
        if not url:
            raise StorageError("SUPABASE_URL이 설정되어 있지 않습니다.")
        if not key:
            raise StorageError("SUPABASE_KEY가 설정되어 있지 않습니다.")
        try:
            from supabase import create_client
            self.client = create_client(url, key)
        except Exception as exc:
            raise StorageError(
                f"Supabase 클라이언트를 만들지 못했습니다 ({exc.__class__.__name__})."
            ) from exc

    def _physical_table(self, table_name: str) -> str:
        return SUPABASE_TABLE_MAP[normalize_table_key(table_name)]

    def _execute(self, operation: str, callable_obj):
        try:
            return callable_obj()
        except Exception as exc:
            raise StorageError(
                f"Supabase {operation} 실패 ({exc.__class__.__name__})."
            ) from exc

    def load_table(self, table_name: str) -> pd.DataFrame:
        key = normalize_table_key(table_name)
        physical = self._physical_table(key)
        rows: list[dict[str, Any]] = []
        page_size = 1000
        offset = 0
        while True:
            def request():
                query = self.client.table(physical).select("*")
                order_column, descending = ORDER_COLUMNS[key]
                query = query.order(order_column, desc=descending)
                return query.range(offset, offset + page_size - 1).execute()

            response = self._execute(f"SELECT {physical}", request)
            batch = getattr(response, "data", None) or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return normalize_dataframe(key, pd.DataFrame(rows))

    @staticmethod
    def _apply_filters(query, filters: dict[str, Any]):
        for column, value in filters.items():
            query = query.eq(column, value)
        return query

    def insert_row(self, table_name: str, row: dict[str, Any]) -> list[dict[str, Any]]:
        physical = self._physical_table(table_name)
        response = self._execute(
            f"INSERT {physical}",
            lambda: self.client.table(physical).insert(row).execute(),
        )
        return list(getattr(response, "data", None) or [])

    def update_rows(
        self, table_name: str, filters: dict[str, Any], values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        physical = self._physical_table(table_name)
        def request():
            query = self.client.table(physical).update(values)
            return self._apply_filters(query, filters).execute()
        response = self._execute(f"UPDATE {physical}", request)
        return list(getattr(response, "data", None) or [])

    def delete_rows(self, table_name: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        physical = self._physical_table(table_name)
        def request():
            query = self.client.table(physical).delete()
            return self._apply_filters(query, filters).execute()
        response = self._execute(f"DELETE {physical}", request)
        return list(getattr(response, "data", None) or [])

    def upsert_rows(
        self,
        table_name: str,
        rows: Iterable[dict[str, Any]],
        conflict_column: str,
    ) -> list[dict[str, Any]]:
        physical = self._physical_table(table_name)
        payload = list(rows)
        response = self._execute(
            f"UPSERT {physical}",
            lambda: self.client.table(physical)
                .upsert(payload, on_conflict=conflict_column)
                .execute(),
        )
        return list(getattr(response, "data", None) or [])

    def replace_table(self, table_name: str, dataframe: pd.DataFrame) -> None:
        raise StorageWriteDisabledError(
            "Supabase에서는 전체 테이블 교체를 지원하지 않습니다. "
            "insert_row, update_rows, delete_rows 또는 upsert_rows를 사용해주세요."
        )


def create_storage(
    backend: str | None = None,
    data_dir: Path | str | None = None,
    default_settings: dict[str, Any] | None = None,
) -> Storage:
    selected = (backend or get_backend_name()).lower().strip()
    if selected == "csv":
        if data_dir is None:
            data_dir = Path(__file__).resolve().parent / "data"
        return CsvStorage(data_dir, default_settings=default_settings)
    if selected == "supabase":
        return SupabaseStorage()
    raise StorageError(f"지원하지 않는 저장소입니다: {selected!r}")


@lru_cache(maxsize=4)
def _cached_storage(backend: str, data_dir: str, default_items: tuple) -> Storage:
    defaults = dict(default_items)
    return create_storage(backend, Path(data_dir), defaults)


def get_storage(
    data_dir: Path | str | None = None,
    default_settings: dict[str, Any] | None = None,
) -> Storage:
    backend = get_backend_name()
    resolved_data_dir = str(Path(data_dir or (Path(__file__).resolve().parent / "data")).resolve())
    default_items = tuple(sorted((default_settings or {}).items()))
    return _cached_storage(backend, resolved_data_dir, default_items)


def clear_storage_cache() -> None:
    _cached_storage.cache_clear()
