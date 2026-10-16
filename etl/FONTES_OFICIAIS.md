# Fontes oficiais das séries socioeconômicas

Todas as séries abaixo vêm de APIs/arquivos públicos. **Lacunas ficam `None`/`null`**: nada é interpolado,
estimado ou preenchido por palpite. Cada registro traz `fonte` (e, quando há mais de uma pesquisa, `serie_*`).

| Dado | Etapa | Fonte | Observações |
|---|---|---|---|
| Gini (Brasil e UF) | `--social` | IBGE/SIDRA t7435 (PNAD Contínua, 2012+, renda domiciliar per capita) e t1167 (PNAD, 1992-2011, pessoas de 10+ com rendimento) | Definições **diferentes**: `serie_gini` por ano e `quebra_metodologica_gini` em 2012 |
| Analfabetismo 15+ | `--social` | SIDRA t7113 (PNAD Contínua, 2016+) | Antes de 2016 não há série equivalente no SIDRA → `null` |
| Extrema pobreza / pobreza | `--social` | SIDRA t5817 (ODS 1.1.1, linha internacional) e t5877 (ODS 1.2.1, linha nacional), 2012+ | Milhões de pessoas = % × população (t6579; Censo 2022 em t9514). 2023 sem população publicada → milhões `null` |
| Insegurança alimentar (% de domicílios) | `--social` | SIDRA t3017 (PNAD 2004) e t9552 (PNAD Contínua 2023-2024) | 2009, 2013 e 2017-18 não estão no SIDRA → `null`. Rede PENSSAN (2020, 2022) em campos próprios `rede_penssan_*`, nunca na série do IBGE |
| Desemprego | `--economic` / `--social` | PME/IBGE via BCB SGS 10777 (6 regiões metropolitanas, ≤2011) e PNAD Contínua SIDRA t6468 (≥2012) | Só anos completos (12 meses PME; 4 trimestres PNADC). Quebra em 2012 |
| Repasses federais por UF | `--orcamento` | Portal da Transparência (CGU), CSV mensal de Transferências, a partir de 2014-01 | Mandatos anteriores a 2014 saem com `parcial=true`. O portal bloqueia rajadas (HTTP 405): o extrator espera e retoma do cache; **não grava** se faltar mês antigo |
| Homicídios | `--economic` | Atlas da Violência (IPEA, SIM/DataSUS), séries 328 (contagem) e 20 (taxa) por UF | Taxa nacional = Σ homicídios / Σ população implícita nas próprias séries do Atlas; pode diferir ±0,4 da taxa de manchete do Atlas |
| Feminicídio | — | **Sem fonte aberta automatizável** | `taxa_feminicidios` fica `null` em todos os anos (antes eram valores digitados e retroações estimadas) |
| Desmatamento (Amazônia Legal) | `--economic` | INPE/PRODES, `ratesAAAA.json` do painel TerraBrasilis (taxa consolidada por Estado) | 1993 e 1994 repetem a média 1993-94 divulgada pelo INPE. A soma das geometrias do WFS **não** reproduz a taxa oficial (até 12% de diferença) |
| Ibovespa | — | Yahoo Finance e tabela digitada da B3 | **Removido do pipeline `--economic`** e da API: não é fonte oficial rastreada (decisão D7). O extrator `ibovespa_extractor` segue no repositório sem uso |
| Composição do Congresso | `--composicao` | Presidentes das Casas, base/oposição e bancadas na posse: **curadoria manual**. Conferência: TSE `consulta_cand` (eleitos por partido) | `verificacao_tse` por casa/mandato. O TSE conta o partido no dia da eleição (trocas partidárias explicam diferenças). Eleição de 1990 ausente dos dados abertos → Senado de 1995 não verificável |

## Lacunas conhecidas
- Pobreza/extrema pobreza antes de 2012, analfabetismo antes de 2016 e insegurança alimentar em 2009/2013/2017-18:
  sem série oficial automatizável (o Ipeadata, que cobriria parte disso, não respondeu a partir do ambiente de desenvolvimento).
- Feminicídio (ver acima).
- Temer (2016) iniciou no meio de uma legislatura: sem conferência de bancada própria. A janela dos dados começa em 1995-01-01 (decisão D8) e a linha presidencial em Fernando Henrique Cardoso.

## Carga no banco (schema `eco`)

`python etl/run_etl.py --load-economia` grava as séries em `eco.observacao` e os dados curados dos mandatos presidenciais em
`core.mandato_presidencial` / `core.marco_governo`. Só entram séries com fonte oficial rastreada em `etl.fonte`; linha
`is_synthetic` e célula vazia viram ausência de observação (nunca zero) e nada anterior a 1995-01-01 é gravado.

| Série (`eco.serie.codigo`) | Fonte | Periodicidade |
|---|---|---|
| `IPCA_MENSAL`, `CAMBIO_MENSAL`, `DIVIDA_LIQUIDA_PIB_MENSAL`, `SALARIO_MINIMO_MENSAL`, `SELIC_META`, `DESEMPREGO_PNADC_MENSAL` | BCB SGS (433, 3698, 4513, 1619, 432, 24369) | mensal (Selic: último valor do mês) |
| `IPCA_ACUM_ANO`, `PIB_CRESC_REAL`, `DESEMPREGO_ANUAL`, `CAMBIO_*_ANO`, `SALARIO_MINIMO`, `DIVIDA_LIQUIDA_PIB` | BCB SGS e IBGE (consolidados pelo `--economic`) | anual |
| `DESMATAMENTO_AMAZONIA` | INPE / PRODES | anual |
| `HOMICIDIOS_TAXA`, `HOMICIDIOS_TOTAL` | IPEA, Atlas da Violência | anual |
| `GINI`, `ANALFABETISMO`, `EXTREMA_POBREZA_*`, `POBREZA_PCT`, `INSEGURANCA_ALIMENTAR_*` e as versões `*_UF` | IBGE / SIDRA | anual (nacional e por UF) |

**Removidos por não terem fonte oficial rastreável (decisão D7):** aprovação popular (Datafolha/CNT digitada em
`seed_executivo.py`), emendas mensais acumuladas do painel do Executivo, Ibovespa e feminicídio. O painel do Executivo
mostra inflação (IPCA em 12 meses), desemprego (PNAD Contínua, desde 2012), câmbio e Selic.

## Dados curados e microdados carregados em `eco` e `leg` (entrega 3b)

| Dado | Arquivo | Fonte | Observação |
|---|---|---|---|
| Subsídio parlamentar | `subsidio_parlamentar.csv` | Decretos legislativos (7/1995, 112/2007, 805/2010, 276/2014, 172/2022), conferidos no texto na Câmara (Legislação Informatizada) | Valor vigente no fim de cada ano, com a norma na `nota`; ano sem norma que traga o valor não entra: 2003 a 2006 ficam de fora (o DL 444/2002 liga a remuneração ao teto do STF e não traz valor em reais) e 2026 não tinha norma |
| Composição do Congresso | `composicao_congresso.json` | Curadoria (Arquivo Histórico da Câmara e do Senado) conferida com o TSE (`consulta_cand`) | Bancadas, presidentes das Casas e `verificacao_tse` vão para `leg.*`; a governabilidade é calculada das bancadas |
| Produção legislativa do Executivo | `producao_executivo.csv` | Curadoria (SICON, SEPAR/Presidência, OLB, Anais do Congresso) | Insumo do IPLE; sem fonte aberta automatizável |
| Distribuição de renda por faixa de salário mínimo | `pnad_faixas_salario_minimo.json` | IBGE, microdados da PNAD Contínua anual (visita 5), gerado por `--pnad` | Sem o ano no banco, a API não mostra percentual |

`python etl/run_etl.py --load-economia` carrega tudo isso, e o cron diário (`make daily`, etapa 1c) atualiza as séries econômicas.
