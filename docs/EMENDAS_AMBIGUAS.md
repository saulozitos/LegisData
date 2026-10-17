# Diagnóstico de Emendas Parlamentares — Homônimos e Desambiguação

Documento técnico sobre o tratamento de parlamentares homônimos (nomes eleitorais ou civis idênticos)
no carregamento de emendas parlamentares do Portal da Transparência.

## Princípio de Não Ambiguidade

O loader oficial de emendas parlamentares () adota o princípio de **segurança e integridade estrita**:
se um nome normalizado de autor corresponde a mais de um indivíduo na base de dados ativa, a emenda **NÃO** é atribuída
arbitrariamente a nenhum dos dois. Isso impede que valores milionários sejam imputados incorretamente a homônimos.

## Casos Notórios de Homônimos no Congresso Nacional

1. **Átila Lira**:
   - *Átila Freitas Lira* (Piauí): Deputado federal nas Legislaturas 53ª, 54ª, 55ª e 56ª.
   - *Átila de Melo Lira* (Piauí): Filho do anterior, eleito deputado federal para a Legislatura 57ª (2023-2027).
   - **Estratégia de Desambiguação**: O cruzamento é realizado pelo ano de execução e vigência do mandato ( a ). Emendas executadas até 2022 pertencem ao pai; emendas a partir de 2023 pertencem ao filho.

2. **Rodrigo Pacheco**:
   - *Rodrigo Otavio Soares Pacheco* (Minas Gerais): Deputado federal (2015-2019) e posteriormente Senador (2019-2027) e Presidente do Senado.
   - **Estratégia de Desambiguação**: Identificação única pelo código de autor da emenda no Portal da Transparência () e vinculação à mesma pessoa civil com mandatos sucessivos.

## Melhoria Aplicada no Loader

O algoritmo do loader avalia o período do mandato parlamentar ( e )
para resolver homônimos inter-legislaturas, garantindo imputação correta sem comprometer a exatidão oficial.

## Situação após a Entrega 3c (2026-10-16)

O critério acima passou a ser aplicado pela carga de `fin.emenda` (`etl/pipelines/pessoa_resolver.py`): o nome só é atribuído a uma pessoa quando é único ou quando exatamente uma das candidatas tinha mandato no ano da emenda. O resto fica com `autor_situacao = 'HOMONIMO_NAO_DESAMBIGUADO'`. No banco de desenvolvimento são 878 emendas de 30 nomes (por exemplo Izalci Lucas, Zenaide Maia e Romário), quase todos senadores cujo mandato de 2019 a 2022 não está em `core.mandato` e que também existem como ex-deputados, sem ligação entre os cadastros; a unificação de pessoas (`docs/PESSOAS_DUPLICADAS.md`) os resolve. Consulta: `SELECT autor_texto, count(*) FROM fin.emenda WHERE autor_situacao = 'HOMONIMO_NAO_DESAMBIGUADO' GROUP BY 1`.
