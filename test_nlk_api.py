"""국립중앙도서관 ISBN 서지정보 API 테스트 스크립트

사용 방법:
1. .env에 NLK_CERT_KEY=발급받은_키 를 넣습니다.
2. 아래 TEST_ISBN 값을 테스트할 ISBN으로 바꿉니다.
3. python test_nlk_api.py 를 실행합니다.
4. 연결 지연 방지를 위해 timeout은 5초로 제한합니다.
"""

from __future__ import annotations

import json
import os
import re
from pprint import pprint

import requests
from dotenv import load_dotenv

load_dotenv()

# 테스트할 ISBN을 여기에 입력하세요. 하이픈/공백이 있어도 자동 정리됩니다.
TEST_ISBN = "978-8954677158"

API_URL = "https://www.nl.go.kr/seoji/SearchApi.do"


def normalize_isbn(isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", str(isbn or "")).upper()


def extract_pages_from_text(text: str) -> int | None:
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
            pages = int(match.group(1))
            if 1 <= pages <= 3000:
                return pages
    return None


def extract_pages_from_payload(payload) -> int | None:
    preferred_key_terms = ["page", "pages", "쪽", "페이지", "형태", "form", "extent", "physical", "description"]

    def walk(obj):
        if isinstance(obj, dict):
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


def collect_possible_page_fields(payload, limit: int = 30) -> list[tuple[str, str]]:
    terms = ["page", "pages", "쪽", "페이지", "형태", "form", "extent", "physical", "description", "vol", "size"]
    found: list[tuple[str, str]] = []

    def walk(obj, path: str = "root"):
        if len(found) >= limit:
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                child_path = f"{path}.{key}"
                key_text = str(key).lower()
                value_text = str(value)
                if any(term in key_text for term in terms) or re.search(r"\d{1,4}\s*(쪽|페이지|p\.|pages?)", value_text, re.I):
                    found.append((child_path, value_text[:300]))
                walk(value, child_path)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                walk(item, f"{path}[{idx}]")

    walk(payload)
    return found


def main() -> None:
    cert_key = os.getenv("NLK_CERT_KEY", "").strip()
    clean_isbn = normalize_isbn(TEST_ISBN)

    if not cert_key:
        print("[오류] .env에서 NLK_CERT_KEY를 찾지 못했습니다.")
        return
    if not clean_isbn:
        print("[오류] TEST_ISBN 값이 비어 있습니다.")
        return

    params = {
        "cert_key": cert_key,
        "result_style": "json",
        "page_no": 1,
        "page_size": 1,
        "isbn": clean_isbn,
    }
    safe_params = dict(params)
    safe_params["cert_key"] = "***"

    print("요청 URL:", API_URL)
    print("요청 파라미터:")
    pprint(safe_params)

    try:
        response = requests.get(API_URL, params=params, timeout=5)
    except requests.Timeout:
        print("[오류] 연결 시간 초과: 국립중앙도서관 API 서버 또는 현재 PC 네트워크 환경에서 응답이 지연되었습니다.")
        return
    except requests.RequestException as e:
        print(f"[오류] API 호출 실패: {e.__class__.__name__}")
        return

    print("status_code:", response.status_code)
    print("응답 텍스트 앞부분:")
    print(response.text[:1500])

    try:
        payload = response.json()
    except ValueError:
        print("JSON 파싱 실패: 응답이 JSON 형식이 아닙니다.")
        return

    pages = extract_pages_from_payload(payload)
    print("\n페이지 수 추출 결과:", pages if pages else "추출 실패")

    if not pages:
        print("\n페이지 수 후보 필드/값:")
        candidates = collect_possible_page_fields(payload)
        if candidates:
            for path, value in candidates:
                print(f"- {path}: {value}")
        else:
            print("페이지 수 후보 필드를 찾지 못했습니다. 원본 JSON 일부를 확인하세요.")
            print(json.dumps(payload, ensure_ascii=False, indent=2)[:2500])


if __name__ == "__main__":
    main()
