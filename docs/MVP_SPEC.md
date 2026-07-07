\# MVP\_SPEC.md



\## 1. MVP 목표



Streamlit으로 “우리가족 독서마라톤” MVP를 만든다.



MVP는 개인 컴퓨터에서 실행 가능해야 하며, GitHub에 업로드하고 Streamlit Community Cloud로 배포할 수 있어야 한다.



1차 MVP의 목표는 다음이다.



\* API 없이도 샘플 데이터로 작동한다.

\* API 키가 있으면 책 검색 API를 사용할 수 있다.

\* 가족 구성원, 책, 독서 기록, 좋았던 문장을 저장할 수 있다.

\* 가족 전체 독서 목표 대비 진행률을 보여준다.

\* 발표 시연이 가능한 화면 흐름을 갖춘다.



\## 2. 기술 스택



\* Python

\* Streamlit

\* pandas

\* requests

\* plotly 또는 matplotlib

\* CSV

\* GitHub

\* Streamlit Community Cloud



\## 3. 기본 폴더 구조



```text

family-reading-marathon/

&#x20; app.py

&#x20; requirements.txt

&#x20; README.md

&#x20; .gitignore

&#x20; data/

&#x20;   books.csv

&#x20;   family\_members.csv

&#x20;   reading\_logs.csv

&#x20;   quotes.csv

&#x20;   reviews.csv

&#x20;   settings.csv

&#x20; sample\_data/

&#x20;   sample\_books.csv

&#x20; docs/

&#x20;   PROJECT\_BRIEF.md

&#x20;   MVP\_SPEC.md

&#x20;   DEV\_LOG.md

&#x20;   PRESENTATION\_OUTLINE.md

```



\## 4. 데이터 파일



\### books.csv



책 정보를 저장한다.



필수 컬럼:



\* book\_id

\* title

\* author

\* publisher

\* isbn

\* image\_url

\* description

\* pubdate

\* total\_pages

\* source\_api

\* created\_at



\### family\_members.csv



가족 구성원 정보를 저장한다.



필수 컬럼:



\* member\_id

\* name

\* role

\* age\_group

\* weight

\* avatar

\* created\_at



예시:



\* 아빠

\* 엄마

\* 첫째

\* 둘째



\### reading\_logs.csv



독서 기록을 저장한다.



필수 컬럼:



\* log\_id

\* member\_id

\* book\_id

\* reading\_date

\* pages\_read

\* weighted\_pages

\* start\_page

\* end\_page

\* memo

\* created\_at



\### quotes.csv



좋았던 문장을 저장한다.



필수 컬럼:



\* quote\_id

\* member\_id

\* book\_id

\* page\_number

\* quote\_text

\* comment

\* created\_at



\### reviews.csv



한 줄 감상 또는 완독 감상을 저장한다.



필수 컬럼:



\* review\_id

\* member\_id

\* book\_id

\* rating

\* one\_line\_review

\* full\_review

\* finished\_date

\* created\_at



\### settings.csv



독서마라톤 설정값을 저장한다.



필수 컬럼:



\* marathon\_name

\* start\_date

\* end\_date

\* family\_target\_pages

\* unit\_name



\## 5. 계산 규칙



\### 개인 누적 페이지



각 구성원의 `pages\_read` 합계로 계산한다.



\### 가중치 반영 페이지



`weighted\_pages = pages\_read × member\_weight`



예시:



\* 성인: 1.0

\* 초등학생: 1.2

\* 미취학 또는 저학년 어린이: 1.5



\### 가족 전체 누적 페이지



모든 구성원의 `weighted\_pages` 합계로 계산한다.



\### 가족 전체 진행률



`가족 전체 누적 페이지 ÷ 가족 목표 페이지 × 100`



\### 책별 진행률



`해당 책에서 읽은 페이지 ÷ total\_pages × 100`



전체 페이지 수가 없으면 사용자가 직접 입력할 수 있게 한다.



\## 6. 필수 화면



\### 1. 홈 / 대시보드



표시 항목:



\* 서비스명

\* 독서마라톤 기간

\* 가족 목표 페이지

\* 가족 전체 누적 페이지

\* 가족 전체 진행률

\* 구성원별 누적 페이지

\* 최근 기록 피드

\* 샘플 데이터 생성 버튼



\### 2. 책 검색 / 책 등록



기능:



\* 책 제목 검색

\* API 검색 결과 표시

\* 샘플DB 검색 지원

\* 책 직접 등록

\* 선택한 책을 가족 책장에 추가



표시 항목:



\* 표지

\* 제목

\* 저자

\* 출판사

\* ISBN

\* 책 소개

\* 전체 페이지 수



\### 3. 가족 책장



표시 항목:



\* 책 표지 카드

\* 제목

\* 저자

\* 출판사

\* 읽는 사람

\* 읽는 중 / 완독 상태

\* 책별 진행률



\### 4. 독서 기록 입력



입력 항목:



\* 가족 구성원

\* 책

\* 읽은 날짜

\* 읽은 페이지 수

\* 시작 페이지

\* 끝 페이지

\* 메모



저장 시 처리:



\* 구성원 가중치를 반영해 `weighted\_pages` 계산

\* `reading\_logs.csv`에 저장

\* 대시보드 수치 업데이트



\### 5. 좋았던 문장



입력 항목:



\* 가족 구성원

\* 책

\* 페이지 번호

\* 좋았던 문장

\* 내 생각



표시 항목:



\* 문장 목록

\* 작성자

\* 책 제목

\* 페이지

\* 코멘트



\### 6. 월간 리포트



표시 항목:



\* 이번 달 총 페이지

\* 목표 달성률

\* 가족별 누적 페이지

\* 가장 많이 읽은 사람

\* 가장 꾸준히 기록한 사람

\* 완독한 책

\* 이달의 문장

\* 규칙 기반 자동 요약문



\## 7. API 연동 구조



책 검색 함수는 분리해서 작성한다.



권장 함수 구조:



\* `search\_books\_naver(query, client\_id, client\_secret)`

\* `search\_books\_sample(query)`

\* `add\_book\_to\_library(book\_data)`

\* `fetch\_book\_pages\_by\_isbn(isbn)`



API 키가 없거나 호출에 실패하면 앱이 중단되지 않고 샘플 검색 또는 수동 등록으로 넘어가야 한다.



\## 8. 샘플 데이터



발표 시연을 위해 샘플 데이터 생성 버튼을 둔다.



샘플 데이터에는 다음이 포함된다.



\* 가족 구성원 4명

\* 샘플 도서 5\~10권

\* 최근 7일 독서 기록

\* 좋았던 문장 몇 개

\* 한 줄 감상 몇 개

\* 7월 독서마라톤 목표 설정



샘플 데이터 버튼을 누르면 API 없이도 모든 화면이 작동해야 한다.



\## 9. API 키 처리



API 키는 코드에 직접 넣지 않는다.



로컬 실행 시:



\* `.env` 파일 또는 앱 화면 입력 방식 사용



Streamlit Community Cloud 배포 시:



\* Streamlit Secrets 사용



`.env`는 `.gitignore`에 포함한다.



\## 10. 1차 제외 기능



1차 MVP에서는 다음 기능을 제외한다.



\* 로그인

\* 회원가입

\* 결제

\* SNS 공유

\* OCR

\* 바코드 스캔

\* 카카오톡/Teams 알림

\* 실제 AI API 연동

\* 복잡한 권한 관리

\* 모바일 앱



\## 11. 규칙 기반 리포트



실제 AI API는 사용하지 않는다.



대신 기록 데이터를 바탕으로 간단한 자동 문장을 생성한다.



예시:



“이번 달 우리 가족은 총 1,240페이지를 읽었습니다. 목표 2,000페이지 중 62%를 달성했습니다. 가장 많이 읽은 사람은 엄마이고, 가장 꾸준히 기록한 사람은 첫째입니다.”



\## 12. README 포함 내용



README에는 다음 내용을 포함한다.



\* 프로젝트 소개

\* 주요 기능

\* 폴더 구조

\* 로컬 실행 방법

\* API 키 설정 방법

\* Streamlit Community Cloud 배포 방법

\* 샘플 데이터 사용 방법

\* 1차 MVP 한계

\* 향후 확장 아이디어



\## 13. 로컬 실행 명령어



```bash

python -m venv .venv

.venv\\Scripts\\activate

pip install -r requirements.txt

streamlit run app.py

```



\## 14. 배포 주의사항



Streamlit Community Cloud 배포 시 다음을 고려한다.



\* `app.py`는 루트 폴더에 둔다.

\* `requirements.txt`를 반드시 포함한다.

\* API 키는 Secrets에 저장한다.

\* 배포 환경에서 CSV 파일 저장이 영구적이지 않을 수 있다.

\* 발표 시연은 샘플 데이터 기반으로 안정적으로 작동해야 한다.



\## 15. 개발 우선순위



1\. CSV 자동 생성

2\. 샘플 데이터 생성

3\. 가족 구성원 등록

4\. 책 직접 등록

5\. 독서 기록 입력

6\. 대시보드 계산

7\. 책 검색 API 연결

8\. 가족 책장 카드 UI

9\. 좋았던 문장 기록

10\. 월간 리포트

11\. 디자인 개선

12\. GitHub 업로드

13\. Streamlit Community Cloud 배포



\## 16. 성공 기준



MVP 성공 기준은 다음과 같다.



\* 로컬에서 `streamlit run app.py`로 실행된다.

\* 샘플 데이터 생성 버튼만으로 전체 데모가 가능하다.

\* 책을 등록하고 독서 기록을 입력하면 진행률이 바뀐다.

\* 가족 구성원별 누적 페이지가 표시된다.

\* 좋았던 문장을 저장하고 볼 수 있다.

\* GitHub에 올려도 API 키가 노출되지 않는다.

\* Streamlit Community Cloud 배포가 가능하다.



