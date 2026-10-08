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
| Ibovespa | `--economic` | Yahoo Finance (^BVSP, barra mensal de dezembro), conferido com a tabela da B3 | Se divergirem >1% o ano é descartado. Ano em curso: `ibovespa_ultimo_pregao` + `parcial=true`, sem `ibovespa_fechamento` |
| Composição do Congresso | `--composicao` | Presidentes das Casas, base/oposição e bancadas na posse: **curadoria manual**. Conferência: TSE `consulta_cand` (eleitos por partido) | `verificacao_tse` por casa/mandato. O TSE conta o partido no dia da eleição (trocas partidárias explicam diferenças). Eleição de 1990 ausente dos dados abertos → Senado de 1995 não verificável |

## Lacunas conhecidas
- Pobreza/extrema pobreza antes de 2012, analfabetismo antes de 2016 e insegurança alimentar em 2009/2013/2017-18:
  sem série oficial automatizável (o Ipeadata, que cobriria parte disso, não respondeu a partir do ambiente de desenvolvimento).
- Feminicídio (ver acima).
- Itamar Franco (1992-94) e Temer (2016) iniciaram no meio de uma legislatura: sem conferência de bancada própria.
