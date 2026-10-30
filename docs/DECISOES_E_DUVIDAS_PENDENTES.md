# Registro de Decisões e Pontos para Alinhamento com o Usuário — LegisData

Este documento registra as decisões técnicas, regras de negócio e pontos metodológicos que demandam direcionamento e validação do usuário/mantenedor do projeto.

Data do registro: 2026-10-13.

**Atualização de 2026-10-16:** as decisões 1 e 2 foram aplicadas na Entrega 3c com a opção recomendada nas duas (autor sem correspondência mantém o nome oficial da fonte, sem `pessoa_id`; homônimos só são desfeitos pelo intervalo de mandato, e o restante fica como "não desambiguado"). Ver `fin.emenda.autor_situacao`.

---

## 1. Mapeamento de Autores Históricos das Emendas (102 Nomes Legados)

- **Contexto**: O documento [`EMENDAS_AUTORES_NAO_ENCONTRADOS.md`](file:///home/saulo/Workspace/LegisData/docs/EMENDAS_AUTORES_NAO_ENCONTRADOS.md) lista 1.077 emendas cujos autores (102 nomes distintos) não constam na base de parlamentares das Legislaturas 55 a 57 (exercícios anteriores a 2015 ou suplentes sem mandato efetivo).
- **Opções de Decisão para o Usuário**:
  1. *(Recomendado)* Manter esses registros atribuídos ao autor textual oficial que consta na prestação de contas do Portal da Transparência (exibindo o nome textual do autor e a legenda "Mandato anterior a 2015 / Não cadastrado nesta legislatura"), sem forçar vínculo com políticos atuais.
  2. Criar uma tabela de equivalência e enriquecimento manual (`etl/data/raw/autores_emendas_de_para.json`) mapeando os 102 nomes para seus CPFs históricos.

---

## 2. Desambiguação de Homônimos Históricos (Emendas Ambíguas)

- **Contexto**: O documento [`EMENDAS_AMBIGUAS.md`](file:///home/saulo/Workspace/LegisData/docs/EMENDAS_AMBIGUAS.md) detalha 570 emendas associadas a 10 nomes ambíguos (ex.: "Átila Lira" pai e filho; "Rodrigo Pacheco" Deputado vs. Senador).
- **Opções de Decisão para o Usuário**:
  1. *(Recomendado)* Aplicar a regra estrita de intervalo temporal: emendas de 2019 a 2022 com a Casa "Câmara" atribuem-se ao mandato de deputado, e a partir de 2023 ao mandato sucessor correspondente. Emendas sem distinção de Casa ou ano dúbio permanecem estritamente rotuladas como "Autor Homônimo / Não desambiguado", preservando a integridade legal.
  2. Fornecer um arquivo manual de chave `(codigo_emenda -> politico_id)` específico para essas 570 emendas.

---

## 3. Estratégia de Armazenamento dos Dados Brutos do ETL (~5,8 GB)

- **Contexto**: Os arquivos brutos baixados (`etl/data/raw/` de TSE, PNAD, Votações e Transferências) somam ~5,8 GB e estão no `.gitignore`.
- **Opções de Decisão para o Usuário**:
  1. *(Recomendado)* **Manter local na máquina de desenvolvimento e servidor de produção**: O pipeline de ETL possui scripts inteligentes e idempotentes (`download_presenca_camara.py`, `remuneracao_extractor.py`, `run_etl.py`) que baixam e processam sob demanda com cache local.
  2. **Repositório Git Submodule / LFS**: Criar um repositório Git dedicado apenas para armazenar os arquivos `.json.gz` e `.zip` consolidados, adicionando-o como submódulo opcional no repositório principal.

---

## 4. Lista de notas fiscais da CEAP no dossiê (Entrega 3c)

- **Contexto**: o ETL publica a CEAP como total por parlamentar, ano e tipo de despesa, mais os 15 maiores fornecedores. O dossiê mostrava esses totais anuais na tabela "Últimos Comprovantes Fiscais", como se fossem notas, e o link para o documento oficial da nota nunca existiu de fato nos dados atuais. A tabela virou "Gasto da cota por ano".
- **Consequência**: o cidadão não vê mais nota por nota nem abre o documento no portal da Câmara.
- **Opção para decidir**: baixar os cerca de 4 milhões de documentos desde 2009 (CSV anual da Câmara) para uma tabela `fin.despesa_cota_documento` com a URL do portal. Custa armazenamento e uma carga maior; entrega rastreabilidade por nota. Fica pendente da sua decisão.

## 5. Histórico de campanhas no dossiê (Entrega 3c)

- **Contexto**: no arquivo do TSE, 568 de 724 parlamentares têm doações em mais de uma eleição (2002 a 2022). Somar todas as eleições num único total e mostrar "Eleição 2018" ao lado de R$ de 2018 e de 2022 enganava o cidadão. O dossiê passou a mostrar só a campanha mais recente (rótulo "última campanha"), e `GET /politicians/{id}/doacoes` aceita `?ano_eleicao=` e devolve `eleicoes_disponiveis`.
- **Consequência**: o histórico de eleições anteriores continua no banco e na API, mas a tela do dossiê ainda não tem seletor de eleição.
- **Opção para decidir**: acrescentar ao `FinancingTab` um seletor de eleição que consulte `/doacoes?ano_eleicao=`, ou manter só a campanha mais recente.

## 6. Formas de número preservadas pelo filtro de CPF em texto livre (Entrega 3c)

- **Contexto**: o filtro de CPF dos campos de texto livre do TSE (descrição de bens, detalhes de certidão) remove a forma canônica `NNN.NNN.NNN-NN` em qualquer vizinhança, inclusive depois de "R$" e colada a dígito anterior. Fora dela, reconhece o desenho de grupos 3-3-3-2 com até 3 separadores (qualquer caractere que não seja letra ou dígito) e 10 ou 11 dígitos corridos, e **preserva de propósito** o que pode ser valor em reais: 10 ou 11 dígitos corridos seguidos de vírgula e 1 ou 2 dígitos (`12345678900,50`), qualquer sequência precedida de "R$" que não seja a forma canônica (`R$ 12345678900`, `R$ 123 456 789 00`) e a forma `NNN.NNN.NNN,NN` (vírgula antes dos dois últimos dígitos). Com separadores entre os grupos e casa decimal (`111 222 333 44,50`) o CPF sai.
- **Consequência**: um CPF escrito exatamente nas formas preservadas, em texto livre, não é removido. Também escapam as caudas raras: 4 ou mais caracteres de separação entre os grupos, o último grupo partido (`111 222 333 4 4`) e letras latinas usadas como separador (`111o222o333o44`). As "letras" Hangul invisíveis (U+115F, U+1160, U+3164, U+FFA0) viram espaço antes da análise. Nos arquivos atuais isso não ocorre (0 alterações e 0 CPFs restantes nas 15.379 descrições de bens e nas 32 certidões); o risco é de cargas futuras.
- **Também de propósito**: 10 ou 11 dígitos corridos sem outra pista são removidos, mesmo quando poderiam ser um RENAVAM, um telefone sem separador ou uma área; `123456789.00`, `100.000.000.00`, `Lotes 101 102 103 10`, `PROTOCOLO 123456789/10`, `CONTA 123456789-10` e um trecho de linha digitável de boleto também perdem o número. Privacidade vale mais que preservar esse dado. Qualquer quebra de linha ou tabulação conta como separador, e o texto livre sai sempre em uma linha só (`Casa\nCarro` vira `Casa Carro`), com ou sem CPF. Em nomes de doador e fornecedor não há valor em reais, então a vírgula antes dos dois últimos dígitos também vale.
- **Opção para decidir**: manter assim, ou trocar a regra por uma lista de rótulos aceitos ("CPF", "C.P.F.") e remover só o que vem depois deles.
- **Tabelas legadas**: `public.doacoes_campanha`, `public.certidoes_judiciais` e as demais tabelas do `public` sem leitor foram removidas pela migração 0035 (Entrega 4b), junto com o loader legado (`tse_loaders.py`); os textos antigos que guardavam CPF saíram com elas.

## 7. Resolução de pessoa sem o ano da eleição e escolha da entrada repetida (Entrega 3c)

- **Patrimônio, doações e certidões do TSE** resolvem a pessoa só por identificador ou por nome único (`resolver(item)` sem ano). Um homônimo sem identificador não é desfeito pelo mandato e o registro fica em `sem_pessoa`. É de propósito: passar `ano_eleicao + 1` (início do mandato) atribuiria dados de um candidato derrotado ao homônimo que tomou posse, e o ETL nunca atribui por palpite. O custo é perder esses registros; a unificação de pessoas duplicadas (`docs/PESSOAS_DUPLICADAS.md`) é o caminho para recuperá-los.
- **CEAP com entradas repetidas da mesma casa** (caso raro: duas entradas do arquivo resolvidas para a mesma pessoa) escolhem a linha vencedora por tabela (despesa, fornecedor, resumo), pelo conteúdo, e o resumo de notas some se qualquer das entradas tiver a quantidade desconhecida. Não há "entrada vencedora" única por pessoa.
- **Fornecedores da CEAP** vêm truncados em 15 por entrada: o total de um fornecedor que está no top 15 de uma casa e fora do da outra é subestimado, e a concentração do dossiê parte dessa lista parcial.

