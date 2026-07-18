-- 우리가족 독서마라톤: 책별 가중치 추가
-- 기존 행과 기존 기록은 삭제하지 않습니다.
-- Supabase SQL Editor에서 앱 코드 배포 전에 한 번만 실행하세요.

begin;

alter table public.books
    add column if not exists book_weight numeric(6,2);

update public.books
set book_weight = 1.00
where book_weight is null or book_weight <= 0;

alter table public.books
    alter column book_weight set default 1.00,
    alter column book_weight set not null;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'books_book_weight_check'
          and conrelid = 'public.books'::regclass
    ) then
        alter table public.books
            add constraint books_book_weight_check
            check (book_weight > 0 and book_weight <= 20);
    end if;
end $$;

-- 현재 러너 가중치 × 책별 가중치를 기존 독서 기록에도 반영합니다.
update public.reading_logs rl
set weighted_pages = round(
    rl.pages_read::numeric
    * fm.weight::numeric
    * b.book_weight::numeric,
    2
)
from public.family_members fm, public.books b
where rl.member_id = fm.member_id
  and rl.book_id = b.book_id;

commit;
