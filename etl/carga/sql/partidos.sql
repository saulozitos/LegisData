-- Partidos: o catálogo curado (ref.partido_semente) e as siglas que as fontes citam. Idempotente.

INSERT INTO core.midia (tipo, url_origem, fonte_id)
SELECT DISTINCT 'LOGO_PARTIDO', s.logo_url, (SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA')
FROM ref.partido_semente s WHERE nullif(btrim(s.logo_url), '') IS NOT NULL
ON CONFLICT (tipo, url_origem) DO NOTHING;

INSERT INTO core.partido (sigla, nome, numero_eleitoral, ideologia_texto, lema, cor_hex, logo_midia_id, catalogo)
SELECT s.sigla, coalesce(s.nome, s.sigla),
       -- o número eleitoral é único: se a curadoria repetir um, nenhum dos dois fica com ele
       CASE WHEN count(*) OVER (PARTITION BY s.numero_eleitoral) = 1 THEN s.numero_eleitoral END,
       s.ideologia, s.lema, s.cor_hex,
       (SELECT m.id FROM core.midia m WHERE m.tipo = 'LOGO_PARTIDO' AND m.url_origem = s.logo_url), true
FROM ref.partido_semente s
ON CONFLICT (sigla_normalizada) DO UPDATE SET
    nome = EXCLUDED.nome,
    numero_eleitoral = coalesce(EXCLUDED.numero_eleitoral, core.partido.numero_eleitoral),
    ideologia_texto = coalesce(EXCLUDED.ideologia_texto, core.partido.ideologia_texto),
    lema = coalesce(EXCLUDED.lema, core.partido.lema),
    cor_hex = coalesce(EXCLUDED.cor_hex, core.partido.cor_hex),
    logo_midia_id = coalesce(EXCLUDED.logo_midia_id, core.partido.logo_midia_id),
    atualizado_em = now();

-- siglas que as fontes citam e a curadoria não conhece: entram fora do catálogo, com a própria sigla como nome
INSERT INTO core.partido (sigla, nome, catalogo)
SELECT DISTINCT ON (ref.normalizar_texto(c.sigla)) btrim(c.sigla), btrim(c.sigla), false
FROM _in_sigla c
WHERE nullif(btrim(c.sigla), '') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM core.partido p WHERE p.sigla_normalizada = ref.normalizar_texto(c.sigla))
  AND NOT EXISTS (SELECT 1 FROM core.partido_alias a WHERE a.sigla_normalizada = ref.normalizar_texto(c.sigla))
ORDER BY ref.normalizar_texto(c.sigla), c.sigla
ON CONFLICT DO NOTHING;

INSERT INTO core.partido_alias (partido_id, sigla_alias, tipo)
SELECT c.id, a.sigla_alias, 'GRAFIA_FONTE'
FROM ref.partido_alias_semente a
JOIN core.partido c ON c.sigla_normalizada = a.sigla_destino_normalizada
WHERE a.sigla_alias_normalizada <> c.sigla_normalizada
  AND NOT EXISTS (SELECT 1 FROM core.partido x WHERE x.sigla_normalizada = a.sigla_alias_normalizada)
ON CONFLICT (sigla_normalizada) DO NOTHING;

-- posição ideológica: curadoria do LegisData, sem fonte primária (a observação diz isso)
INSERT INTO core.partido_posicao_ideologica (partido_id, escala, espectro, fonte_id, observacao)
SELECT c.id, 'ESPECTRO_5', s.espectro, (SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA'),
       'Classificação curada em ref.partido_semente, sem fonte primária registrada'
FROM ref.partido_semente s JOIN core.partido c ON c.sigla_normalizada = s.sigla_normalizada
WHERE s.espectro IS NOT NULL
ON CONFLICT (partido_id, escala, fonte_id, ano_referencia) DO UPDATE SET espectro = EXCLUDED.espectro;

INSERT INTO core.partido_posicao_ideologica (partido_id, escala, valor, fonte_id, observacao)
SELECT c.id, 'ESCALA_1_10', s.escala_valor, (SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA'),
       'ESCALA_IDEOLOGICA_PADRAO (iple_service.py), atribuída no código a BLS / Power & Zucco / Tarouco & Madeira'
FROM ref.partido_semente s JOIN core.partido c ON c.sigla_normalizada = s.sigla_normalizada
WHERE s.escala_valor IS NOT NULL
ON CONFLICT (partido_id, escala, fonte_id, ano_referencia) DO UPDATE SET valor = EXCLUDED.valor;

SELECT etl.aplicar_linhagens();
