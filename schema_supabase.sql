-- Esquema para Simulador Oposiciones DE25 GR2 - Nivel 3
-- Ejecutar en Supabase > SQL Editor > New query > Run.

create extension if not exists pgcrypto;

create table if not exists public.questions (
    id integer primary key,
    exam_code text not null default 'DE25_GR2',
    question_text text not null,
    option_a text,
    option_b text,
    option_c text,
    option_d text,
    correct_option text check (correct_option in ('A','B','C','D')),
    correct_text text,
    theme text,
    confidence text default 'Media',
    status text default 'Propuesta no oficial',
    notes text,
    source text,
    updated_at timestamptz not null default now()
);

create table if not exists public.quiz_attempts (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    created_at timestamptz not null default now(),
    num_questions integer not null,
    correct integer not null,
    wrong integer not null,
    blank integer not null,
    penalty numeric not null default 0,
    raw_score numeric not null,
    net_score numeric not null,
    themes text[],
    question_ids integer[]
);

create table if not exists public.quiz_answers (
    id uuid primary key default gen_random_uuid(),
    attempt_id uuid references public.quiz_attempts(id) on delete cascade,
    user_id text not null,
    question_id integer references public.questions(id) on delete cascade,
    selected_option text,
    correct_option text,
    is_correct boolean not null default false,
    is_blank boolean not null default false,
    created_at timestamptz not null default now()
);

create table if not exists public.question_edits (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    question_id integer references public.questions(id) on delete cascade,
    old_correct_option text,
    new_correct_option text,
    old_status text,
    new_status text,
    old_confidence text,
    new_confidence text,
    notes text,
    created_at timestamptz not null default now()
);

create index if not exists idx_questions_theme on public.questions(theme);
create index if not exists idx_questions_confidence on public.questions(confidence);
create index if not exists idx_attempts_user_created on public.quiz_attempts(user_id, created_at desc);
create index if not exists idx_answers_user_question on public.quiz_answers(user_id, question_id);
create index if not exists idx_answers_attempt on public.quiz_answers(attempt_id);

-- RLS activado. La app usa la service role key desde Streamlit Secrets, que evita exponer la base al navegador.
alter table public.questions enable row level security;
alter table public.quiz_attempts enable row level security;
alter table public.quiz_answers enable row level security;
alter table public.question_edits enable row level security;

-- Función para actualizar updated_at en questions.
create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_questions_updated_at on public.questions;
create trigger trg_questions_updated_at
before update on public.questions
for each row execute function public.set_updated_at();
