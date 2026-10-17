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
