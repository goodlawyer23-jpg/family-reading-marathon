-- 우리가족 독서마라톤 Supabase 스키마
-- Supabase SQL Editor에서 실행하세요.
-- app.py 연결 전 설계/테스트 단계용입니다.

begin;

create extension if not exists pgcrypto;

-- 1. 독서마라톤
create table if not exists public.marathons (
    marathon_id text primary key,
    marathon_name text not null,
    start_date date not null,
    end_date date not null,
    family_target_pages integer not null default 2000
        check (family_target_pages > 0),
    unit_name text not null default '페이지',
    is_active boolean not null default false,
    created_at timestamptz not null default now(),
    constraint marathons_date_range_check check (end_date >= start_date)
);

-- 동시에 하나의 마라톤만 active가 되도록 보장
create unique index if not exists uq_marathons_single_active
    on public.marathons (is_active)
    where is_active = true;

create index if not exists idx_marathons_start_date
    on public.marathons (start_date desc);

-- 2. 가족 러너
create table if not exists public.family_members (
    member_id text primary key,
    name text not null,
    role text not null default '',
    age_group text not null default '성인'
        check (age_group in ('성인', '청소년', '어린이', '유아')),
    weight numeric(6,2) not null default 1.00
        check (weight > 0 and weight <= 20),
    avatar text not null default '🌟',
    created_at timestamptz not null default now()
);

create index if not exists idx_family_members_name
    on public.family_members (name);

-- 3. 책장 항목
-- 같은 실물 도서를 여러 러너/마라톤에 담을 수 있으므로 book_id는 현재 CSV ID를 그대로 사용합니다.
create table if not exists public.books (
    book_id text primary key,
    marathon_id text not null,
    reader_member_id text not null,
    title text not null,
    author text not null default '',
    publisher text not null default '',
    isbn text not null default '',
    image_url text not null default '',
    description text not null default '',
    pubdate date null,
    total_pages integer not null default 0
        check (total_pages >= 0),
    book_weight numeric(6,2) not null default 1.00
        check (book_weight > 0 and book_weight <= 20),
    source_api text not null default 'manual',
    created_at timestamptz not null default now(),

    constraint books_marathon_fk
        foreign key (marathon_id)
        references public.marathons (marathon_id)
        on update cascade
        on delete cascade,

    constraint books_reader_fk
        foreign key (reader_member_id)
        references public.family_members (member_id)
        on update cascade
        on delete restrict
);

create index if not exists idx_books_marathon
    on public.books (marathon_id);

create index if not exists idx_books_reader
    on public.books (reader_member_id);

create index if not exists idx_books_marathon_reader
    on public.books (marathon_id, reader_member_id);

create index if not exists idx_books_isbn
    on public.books (isbn)
    where isbn <> '';

-- 4. 독서 기록
create table if not exists public.reading_logs (
    log_id text primary key,
    marathon_id text not null,
    member_id text not null,
    book_id text not null,
    reading_date date not null,
    pages_read integer not null
        check (pages_read > 0),
    weighted_pages numeric(12,2) not null
        check (weighted_pages >= 0),
    start_page integer not null default 0
        check (start_page >= 0),
    end_page integer not null default 0
        check (end_page >= 0),
    memo text not null default '',
    created_at timestamptz not null default now(),

    constraint reading_logs_page_range_check
        check (start_page = 0 or end_page = 0 or end_page >= start_page),

    constraint reading_logs_marathon_fk
        foreign key (marathon_id)
        references public.marathons (marathon_id)
        on update cascade
        on delete cascade,

    constraint reading_logs_member_fk
        foreign key (member_id)
        references public.family_members (member_id)
        on update cascade
        on delete restrict,

    constraint reading_logs_book_fk
        foreign key (book_id)
        references public.books (book_id)
        on update cascade
        on delete restrict
);

create index if not exists idx_reading_logs_marathon_date
    on public.reading_logs (marathon_id, reading_date desc);

create index if not exists idx_reading_logs_member_book
    on public.reading_logs (member_id, book_id);

create index if not exists idx_reading_logs_book
    on public.reading_logs (book_id);

-- 5. 좋았던 문장
create table if not exists public.quotes (
    quote_id text primary key,
    marathon_id text not null,
    member_id text not null,
    book_id text not null,
    page_number integer not null default 0
        check (page_number >= 0),
    quote_text text not null,
    comment text not null default '',
    created_at timestamptz not null default now(),

    constraint quotes_marathon_fk
        foreign key (marathon_id)
        references public.marathons (marathon_id)
        on update cascade
        on delete cascade,

    constraint quotes_member_fk
        foreign key (member_id)
        references public.family_members (member_id)
        on update cascade
        on delete restrict,

    constraint quotes_book_fk
        foreign key (book_id)
        references public.books (book_id)
        on update cascade
        on delete restrict
);

create index if not exists idx_quotes_marathon_created
    on public.quotes (marathon_id, created_at desc);

create index if not exists idx_quotes_member_book
    on public.quotes (member_id, book_id);

create index if not exists idx_quotes_book
    on public.quotes (book_id);

-- 6. 완독 감상
create table if not exists public.reviews (
    review_id text primary key,
    marathon_id text not null,
    member_id text not null,
    book_id text not null,
    rating numeric(2,1) not null
        check (rating >= 0.5 and rating <= 5.0 and mod(rating * 10, 5) = 0),
    one_line_review text not null,
    full_review text not null default '',
    finished_date date null,
    created_at timestamptz not null default now(),

    constraint reviews_marathon_fk
        foreign key (marathon_id)
        references public.marathons (marathon_id)
        on update cascade
        on delete cascade,

    constraint reviews_member_fk
        foreign key (member_id)
        references public.family_members (member_id)
        on update cascade
        on delete restrict,

    constraint reviews_book_fk
        foreign key (book_id)
        references public.books (book_id)
        on update cascade
        on delete restrict
);

create index if not exists idx_reviews_marathon_created
    on public.reviews (marathon_id, created_at desc);

create index if not exists idx_reviews_member_book
    on public.reviews (member_id, book_id);

create index if not exists idx_reviews_book
    on public.reviews (book_id);

create index if not exists idx_reviews_finished_date
    on public.reviews (finished_date)
    where finished_date is not null;

-- 연결 테스트 전용 테이블
create table if not exists public.connection_tests (
    test_id text primary key,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- RLS는 처음부터 켭니다.
alter table public.marathons enable row level security;
alter table public.family_members enable row level security;
alter table public.books enable row level security;
alter table public.reading_logs enable row level security;
alter table public.quotes enable row level security;
alter table public.reviews enable row level security;
alter table public.connection_tests enable row level security;

-- ============================================================
-- 권장 보안 모델
-- ============================================================
-- Streamlit 서버에서 SUPABASE secret/service_role 키를 사용하는 방식:
--   * secret/service_role 키는 RLS를 우회합니다.
--   * 아래 테이블에 anon/authenticated 정책을 만들지 않습니다.
--   * 키는 반드시 .env 또는 Streamlit Secrets에만 저장합니다.
--   * 브라우저 코드, GitHub, 로그에 절대 노출하지 않습니다.
--
-- 이 SQL은 anon/authenticated에 대한 public 정책을 일부러 만들지 않습니다.
-- 따라서 publishable/anon 키로는 Data API 접근이 차단됩니다.
--
-- 초기 연결 테스트를 anon 키로 해야 하는 특별한 경우에만,
-- 아래 TEMP 정책을 잠깐 실행한 뒤 테스트 후 즉시 삭제하세요.
--
-- create policy "TEMP connection_tests all"
-- on public.connection_tests
-- for all
-- to anon
-- using (true)
-- with check (true);
--
-- 테스트 완료 후:
-- drop policy if exists "TEMP connection_tests all" on public.connection_tests;
--
-- 실제 공개 배포에서 아래와 같은 전체 공개 쓰기 정책은 사용하지 마세요.
-- create policy ... for all to anon using (true) with check (true);

commit;
