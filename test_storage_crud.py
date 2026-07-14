"""storage.py의 CSV CRUD와 Supabase 호출 구성을 민감정보 없이 확인합니다.

실제 Supabase 데이터 쓰기는 앱의 관리자 UI에서 테스트하세요.
이 파일은 CSV 임시 폴더 및 SupabaseStorage의 mocked client를 사용합니다.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from storage import CsvStorage, SupabaseStorage


def test_csv_crud():
    with TemporaryDirectory() as tmp:
        storage = CsvStorage(Path(tmp), default_settings={})
        row = {"member_id":"member_test","name":"테스트","role":"","age_group":"성인","weight":1.0,"avatar":"🌟","created_at":"2026-01-01 00:00:00"}
        assert storage.insert_row("family_members", row)
        assert storage.update_rows("family_members", {"member_id":"member_test"}, {"name":"수정"})[0]["name"] == "수정"
        assert storage.delete_rows("family_members", {"member_id":"member_test"})


def test_supabase_methods_mocked():
    storage = object.__new__(SupabaseStorage)
    storage.client = MagicMock()
    response = MagicMock(); response.data = [{"member_id":"member_test"}]
    chain = storage.client.table.return_value
    chain.insert.return_value.execute.return_value = response
    chain.update.return_value.eq.return_value.execute.return_value = response
    chain.delete.return_value.eq.return_value.execute.return_value = response
    assert storage.insert_row("family_members", {"member_id":"member_test"})
    assert storage.update_rows("family_members", {"member_id":"member_test"}, {"name":"수정"})
    assert storage.delete_rows("family_members", {"member_id":"member_test"})


if __name__ == "__main__":
    test_csv_crud(); test_supabase_methods_mocked()
    print("CSV CRUD 및 Supabase CRUD 메서드 mock 테스트 성공")
