-- Filiações: o partido de cada pessoa em cada período, DERIVADO do que as fontes oficiais já gravaram em `core`:
--   1. core.mandato_partido  - partido por período dentro do mandato (eventos da Câmara; é o dado mais exato);
--   2. core.mandato.partido_id - partido na posse, para o mandato que não tem períodos (senadores, presidentes, lista atual).
-- Nenhum arquivo digitado à mão. A tabela inteira é refeita a cada carga (é só uma visão materializada do que já está
-- no banco), então rodar de novo não duplica nem deixa resto. Fora do período conhecido não há filiação: desconhecido é vazio.
-- Entrada: nenhuma. Saída: _rej (motivo, n), onde cada motivo diz por que um trecho lido não virou linha própria.

CREATE TEMP TABLE _seg ON COMMIT DROP AS
SELECT m.pessoa_id, mp.partido_id, lower(mp.periodo) AS ini,
       CASE WHEN upper_inf(mp.periodo) THEN NULL ELSE upper(mp.periodo) - 1 END AS fim, 1 AS prio, mp.fonte_id
FROM core.mandato_partido mp JOIN core.mandato m ON m.id = mp.mandato_id
UNION ALL
SELECT m.pessoa_id, m.partido_id, m.inicio, m.fim, 2, m.fonte_id
FROM core.mandato m
WHERE m.partido_id IS NOT NULL AND m.condicao <> 'NOMEADO'
  AND NOT EXISTS (SELECT 1 FROM core.mandato_partido mp WHERE mp.mandato_id = m.id);

-- mesmo dia de início: vale o período exato (prio 1), depois o de partido id menor
CREATE TEMP TABLE _uni ON COMMIT DROP AS
SELECT x.pessoa_id, x.partido_id, x.ini, x.fim, x.fonte_id
FROM (SELECT s.*, row_number() OVER (PARTITION BY s.pessoa_id, s.ini ORDER BY s.prio, s.partido_id) AS rn FROM _seg s) x
WHERE x.rn = 1;

-- um partido por vez: o trecho termina na véspera do próximo, se sobrepuser
CREATE TEMP TABLE _cort ON COMMIT DROP AS
SELECT k.pessoa_id, k.partido_id, k.ini, k.fonte_id,
       CASE WHEN k.prox IS NOT NULL AND (k.fim IS NULL OR k.fim >= k.prox) THEN k.prox - 1 ELSE k.fim END AS fim,
       (k.prox IS NOT NULL AND (k.fim IS NULL OR k.fim >= k.prox)) AS inferido
FROM (SELECT u.*, lead(u.ini) OVER (PARTITION BY u.pessoa_id ORDER BY u.ini) AS prox FROM _uni u) k;

-- trechos seguidos do mesmo partido viram uma filiação só
CREATE TEMP TABLE _ilha ON COMMIT DROP AS
SELECT c.*, sum(c.novo::int) OVER (PARTITION BY c.pessoa_id ORDER BY c.ini) AS grupo
FROM (SELECT t.*, (lag(t.partido_id) OVER w IS DISTINCT FROM t.partido_id
                   OR lag(t.fim) OVER w IS NULL OR lag(t.fim) OVER w + 1 < t.ini) AS novo
      FROM _cort t WINDOW w AS (PARTITION BY t.pessoa_id ORDER BY t.ini)) c;

INSERT INTO _rej SELECT 'ENGOLIDO_POR_PERIODO_COM_MESMO_INICIO', (SELECT count(*) FROM _seg) - (SELECT count(*) FROM _uni)
WHERE (SELECT count(*) FROM _seg) > (SELECT count(*) FROM _uni);
INSERT INTO _rej SELECT 'UNIDO_AO_TRECHO_SEGUIDO_DO_MESMO_PARTIDO', (SELECT count(*) FROM _uni) - count(DISTINCT (pessoa_id, grupo))
FROM _ilha HAVING (SELECT count(*) FROM _uni) > count(DISTINCT (pessoa_id, grupo));

DELETE FROM core.filiacao;
INSERT INTO core.filiacao (pessoa_id, partido_id, periodo, fim_inferido, fonte_id)
SELECT g.pessoa_id, g.partido_id, daterange(g.ini, g.fim, '[]'), g.inferido, g.fonte_id
FROM (SELECT DISTINCT ON (i.pessoa_id, i.grupo) i.pessoa_id, i.partido_id,
             min(i.ini) OVER w AS ini, i.fim, i.inferido, i.fonte_id
      FROM _ilha i WINDOW w AS (PARTITION BY i.pessoa_id, i.grupo)
      ORDER BY i.pessoa_id, i.grupo, i.ini DESC) g;
