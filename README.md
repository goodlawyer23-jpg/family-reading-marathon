# 우리가족 독서마라톤

우리가족 독서마라톤은 가족 구성원이 각자 읽는 책과 페이지 수, 감상, 좋았던 문장을 기록하고, 가족 전체의 독서 목표 달성 과정을 마라톤처럼 시각화하는 Streamlit 웹페이지입니다.

1차 MVP는 거대한 상용 서비스가 아니라, 개인 컴퓨터에서 실행하고 경진대회 발표에서 안정적으로 시연할 수 있는 작은 웹서비스를 목표로 합니다.

## 주요 기능

- 가족 구성원 등록
- CSV 자동 생성 및 CSV 기반 저장
- 샘플 데이터 생성 버튼
- 네이버 책 검색 API 검색
- 검색 결과는 기본 최대 50개로 검색
- 검색 결과는 한 화면에 10개씩 페이지 번호 버튼으로 구분 표시
- 페이지 번호 버튼 클릭 시 검색 결과 선택 구역으로 자동 스크롤
- 책 제목 검색 / ISBN 검색 선택
- API 실패 시 샘플 책 검색 자동 전환
- 책 직접 등록
- 책 등록 시 읽을 가족 구성원 연결
- 가족 책장 카드 보기
- 독서 기록 입력
- 최근 입력 독서 기록 2단계 확인 후 삭제
- 가중치 반영 페이지 자동 계산
- 가족 전체 목표 대비 진행률 표시
- 구성원별 누적 페이지 및 순위 표시
- 좋았던 문장 기록
- 한 줄 감상 및 완독일 기록
- 규칙 기반 월간 독서 리포트 생성

## 폴더 구조

```text
family-reading-marathon/
  app.py
  requirements.txt
  README.md
  .gitignore
  data/
    books.csv
    family_members.csv
    reading_logs.csv
    quotes.csv
    reviews.csv
    settings.csv
  sample_data/
    sample_books.csv
  docs/
    PROJECT_BRIEF.md
    MVP_SPEC.md
    DEV_LOG.md
    PRESENTATION_OUTLINE.md
```

`data/` 폴더와 CSV 파일은 앱 실행 시 자동으로 생성됩니다.

## 로컬 실행 방법

Windows 기준입니다.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Mac 또는 Linux에서는 가상환경 활성화 명령만 아래처럼 바꾸면 됩니다.

```bash
source .venv/bin/activate
```

## 샘플 데이터 사용 방법

앱을 처음 실행한 뒤 홈 화면에서 **샘플 데이터 생성 / 초기화** 버튼을 누르면 다음 데이터가 생성됩니다.

- 가족 구성원 4명
- 샘플 도서 7권
- 최근 7일 독서 기록
- 좋았던 문장 3개
- 한 줄 감상 3개
- 2026년 7월 독서마라톤 목표 2,000페이지

이 버튼만으로 API 키 없이도 전체 화면 시연이 가능합니다.

## API 키 설정 방법

1차 MVP는 API 키가 없어도 작동합니다.

네이버 책 검색 API를 연결하려면 환경변수 또는 `.env` 파일에 아래 값을 설정합니다. 앱 실행 시 `python-dotenv`가 `.env`를 읽고, 값이 있으면 책 검색 화면에서 네이버 API를 먼저 사용합니다.

```bash
NAVER_CLIENT_ID=발급받은_CLIENT_ID
NAVER_CLIENT_SECRET=발급받은_CLIENT_SECRET
```

`.env` 파일은 GitHub에 올리지 않도록 `.gitignore`에 포함되어 있습니다.

Streamlit Community Cloud에 배포할 때는 앱 설정의 Secrets에 아래처럼 입력합니다.

```toml
NAVER_CLIENT_ID = "발급받은_CLIENT_ID"
NAVER_CLIENT_SECRET = "발급받은_CLIENT_SECRET"
```

현재 `app.py`는 로컬 `.env` / 환경변수와 Streamlit Secrets를 모두 확인합니다. API 키가 없거나 API 호출에 실패하면 앱이 멈추지 않고 샘플 책 검색으로 자동 전환됩니다.

책 검색 화면에서는 검색 결과 개수를 따로 고르지 않아도 됩니다. 앱은 기본적으로 네이버 API의 `display=50`을 사용해 최대 50개를 검색하고, 샘플 검색 fallback도 최대 50개 기준으로 작동합니다. 검색 방식은 **책 제목 검색**과 **ISBN 검색** 중 선택할 수 있으며, ISBN 검색은 하이픈이 포함된 값도 처리합니다. 검색 결과가 10건을 초과하면 화면에는 10개씩 나누어 표시되고, 책 목록 아래의 `1 2 3 4 5` 형태 페이지 번호 버튼으로 다음 결과를 볼 수 있습니다. 페이지 번호를 누르면 다음 결과를 바로 확인할 수 있도록 `3단계. 원하는 책을 선택해 책장에 추가하세요` 위치로 자동 스크롤됩니다.

## Streamlit Community Cloud 배포 방법

1. GitHub에 새 저장소를 만듭니다.
2. 이 프로젝트 폴더 전체를 업로드합니다.
3. Streamlit Community Cloud에서 새 앱을 생성합니다.
4. Repository를 선택합니다.
5. Main file path를 `app.py`로 지정합니다.
6. API 키가 필요한 경우 Secrets에 키를 등록합니다.
7. Deploy 버튼을 누릅니다.

주의: Streamlit Community Cloud의 파일 저장은 영구 저장소로 설계되어 있지 않습니다. 발표 시연은 샘플 데이터 버튼으로 초기화 가능한 구조를 유지하는 것이 안전합니다.


## 이번 버전의 책장 연결 방식

책 검색 결과에서 **책장에 추가**를 누르기 전에 읽을 가족 구성원을 선택합니다. 이 값은 `books.csv`의 `reader_member_id` 컬럼에 저장됩니다. 기존 CSV에 이 컬럼이 없어도 앱 실행 시 자동으로 컬럼을 추가하므로 기존 데이터가 바로 깨지지 않습니다.

같은 책을 같은 구성원의 책장에 다시 추가하려고 하면 중복 등록하지 않고 안내 메시지를 표시합니다. 같은 책을 다른 구성원이 읽는 경우에는 별도 책장 카드로 추가할 수 있습니다.

## 독서 기록 삭제

독서 기록 입력 화면의 **최근 입력 기록**에서 각 기록별 **삭제** 버튼을 누르면 바로 삭제하지 않고 “정말 이 독서 기록을 삭제할까요?” 확인 단계가 표시됩니다. **삭제 확인**을 한 번 더 눌렀을 때만 해당 `log_id`의 기록이 `reading_logs.csv`에서 삭제됩니다. 삭제 후 홈 대시보드, 가족 책장 진행률, 월간 리포트는 CSV를 다시 읽어 자동으로 재계산됩니다.

## 데이터 저장 방식

1차 MVP는 CSV 파일을 사용합니다.

- `books.csv`: 책 정보 및 책장에 연결된 읽는 사람
- `family_members.csv`: 가족 구성원
- `reading_logs.csv`: 독서 기록
- `quotes.csv`: 좋았던 문장
- `reviews.csv`: 한 줄 감상 및 완독 기록
- `settings.csv`: 독서마라톤 목표와 기간

나중에 필요하면 Supabase, Google Sheets, Firebase, SQLite 등으로 확장할 수 있습니다.

## 계산 규칙

- 개인 누적 페이지 = `pages_read` 합계
- 가중치 반영 페이지 = `pages_read × member_weight`
- 가족 전체 누적 페이지 = 모든 구성원의 `weighted_pages` 합계
- 가족 진행률 = 가족 전체 누적 페이지 ÷ 가족 목표 페이지 × 100
- 책별 진행률 = 해당 책에서 읽은 페이지 ÷ `total_pages` × 100
- `total_pages`가 없거나 0이면 오류 없이 “전체 페이지 미입력” 상태로 표시합니다.

## 1차 MVP 한계

현재 버전에서는 다음 기능을 제외했습니다.

- 로그인
- 회원가입
- 알림
- OCR
- 바코드 스캔
- 복잡한 권한 관리
- 실제 AI API 연동
- 영구 DB 저장
- 모바일 앱

## 향후 확장 아이디어

- 국립중앙도서관 ISBN API로 전체 페이지 수 보강
- 알라딘 Open API로 베스트셀러·추천 도서 표시
- 가족별 배지와 마라톤 트랙 디자인 강화
- Google Sheets 또는 Supabase 저장소 연결
- 월간 리포트 PDF 저장
- 발표용 데모 시나리오 화면 추가

## 발표 시연 추천 흐름

1. 홈 화면에서 샘플 데이터 생성 버튼을 누릅니다.
2. 대시보드에서 가족 목표와 현재 진행률을 보여줍니다.
3. 책 검색 / 책 등록 화면에서 네이버 API 또는 샘플 책을 검색합니다.
4. 읽을 가족 구성원을 선택한 뒤 책을 가족 책장에 추가합니다.
5. 독서 기록을 입력하고, 필요하면 최근 입력 기록에서 잘못 저장한 기록을 삭제합니다.
6. 홈 화면으로 돌아가 진행률이 바뀐 것을 보여줍니다.
7. 좋았던 문장을 저장합니다.
8. 월간 리포트에서 자동 요약문을 보여줍니다.
