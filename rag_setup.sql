-- Setup del RAG de Sofia en Supabase (correr UNA vez en el SQL Editor de Supabase).
-- Crea la extension pgvector, la tabla de conocimiento y la funcion de busqueda semantica.
-- Dimension 1024 = voyage-3.5-lite. Si cambias de modelo de embeddings, ajusta el numero.

create extension if not exists vector;

create table if not exists kb_varka (
  id         bigserial primary key,
  seccion    text,
  contenido  text,
  embedding  vector(1024)
);

-- Indice para busqueda por similitud coseno (rapido).
create index if not exists kb_varka_embedding_idx
  on kb_varka using hnsw (embedding vector_cosine_ops);

-- Funcion que devuelve los match_count fragmentos mas parecidos a query_embedding.
create or replace function match_kb(
  query_embedding vector(1024),
  match_count int default 4
)
returns table (id bigint, seccion text, contenido text, similitud float)
language sql stable
as $$
  select
    kb_varka.id,
    kb_varka.seccion,
    kb_varka.contenido,
    1 - (kb_varka.embedding <=> query_embedding) as similitud
  from kb_varka
  order by kb_varka.embedding <=> query_embedding
  limit match_count;
$$;