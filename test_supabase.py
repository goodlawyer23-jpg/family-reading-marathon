"""Supabase 연결 및 CRUD 테스트.

사전 조건
1. Supabase SQL Editor에서 supabase_schema.sql 실행
2. .env에 아래 값을 설정
   SUPABASE_URL=https://<project-ref>.supabase.co
   SUPABASE_KEY=<server-side secret key 또는 legacy service_role key>

주의
- 공개 앱의 서버 코드에서만 secret/service_role 키를 사용하세요.
- GitHub, 브라우저 코드, 출력 로그에 키를 노출하지 마세요.
- 테스트 행은 성공/실패 여부와 관계없이 마지막에 제거를 시도합니다.
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client


TEST_TABLE = "connection_tests"


def create_supabase_client() -> Client:
    load_dotenv()
    url = str(os.getenv("SUPABASE_URL", "") or "").strip()
    key = str(os.getenv("SUPABASE_KEY", "") or "").strip()

    if not url:
        raise RuntimeError(".env에 SUPABASE_URL이 없습니다.")
    if not key:
        raise RuntimeError(".env에 SUPABASE_KEY가 없습니다.")

    # 키 자체는 절대로 출력하지 않습니다.
    return create_client(url, key)


def response_data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


def main() -> int:
    test_id = f"connection_test_{uuid.uuid4().hex}"
    client: Client | None = None
    inserted = False

    print("Supabase 연결 및 CRUD 테스트")
    print(f"테스트 테이블: {TEST_TABLE}")
    print("SUPABASE_URL / SUPABASE_KEY: 설정 여부만 확인하며 실제 값은 출력하지 않습니다.")

    try:
        client = create_supabase_client()
        print("[1/5] 클라이언트 생성: 성공")

        insert_payload = {
            "test_id": test_id,
            "payload": {"message": "supabase connection test", "step": "insert"},
        }
        inserted_response = (
            client.table(TEST_TABLE)
            .insert(insert_payload)
            .execute()
        )
        inserted_rows = response_data(inserted_response)
        inserted = True
        print(f"[2/5] INSERT: 성공 ({len(inserted_rows)}행 반환)")

        selected_response = (
            client.table(TEST_TABLE)
            .select("test_id,payload,created_at")
            .eq("test_id", test_id)
            .execute()
        )
        selected_rows = response_data(selected_response)
        if len(selected_rows) != 1:
            raise RuntimeError(f"SELECT 결과가 1행이 아닙니다: {len(selected_rows)}행")
        print("[3/5] SELECT: 성공")

        updated_response = (
            client.table(TEST_TABLE)
            .update({"payload": {"message": "supabase connection test", "step": "update"}})
            .eq("test_id", test_id)
            .execute()
        )
        updated_rows = response_data(updated_response)
        if not updated_rows:
            raise RuntimeError("UPDATE 결과가 비어 있습니다.")
        print("[4/5] UPDATE: 성공")

        deleted_response = (
            client.table(TEST_TABLE)
            .delete()
            .eq("test_id", test_id)
            .execute()
        )
        deleted_rows = response_data(deleted_response)
        inserted = False
        print(f"[5/5] DELETE: 성공 ({len(deleted_rows)}행 반환)")
        print("\n모든 Supabase CRUD 테스트가 성공했습니다.")
        return 0

    except Exception as exc:
        print(f"\n[실패] {exc.__class__.__name__}: {exc}")
        print("키 값은 출력하지 않았습니다.")
        return 1

    finally:
        if client is not None and inserted:
            try:
                client.table(TEST_TABLE).delete().eq("test_id", test_id).execute()
                print("[정리] 남아 있던 테스트 행을 제거했습니다.")
            except Exception as cleanup_exc:
                print(
                    f"[정리 경고] 테스트 행 자동 제거 실패: "
                    f"{cleanup_exc.__class__.__name__}: {cleanup_exc}"
                )


if __name__ == "__main__":
    sys.exit(main())
