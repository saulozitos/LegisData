# Metodologia de Atividade Legislativa Ponderada (IALP) & Grafo de Redes de Coautoria

Este documento estabelece as regras de negócio, modelagem matemática e arquitetura de dados do **Índice de Atividade Legislativa Ponderado (IALP)** e da **Análise de Redes de Coautoria Política** da **Plataforma Cívica Independente (LegisData)**, em conformidade integral com a Especificação Técnica de Transparência Política e Fiscal do Brasil.

---

## 1. Escopo do Sistema e Diagnóstico Cívico

O sistema processa dados estruturados e enriquecidos do Congresso Nacional Brasileiro (Câmara dos Deputados e Senado Federal). O objetivo é gerar **métricas de produtividade parlamentar não enviesadas** e mapear **dinâmicas de articulação política através de grafos de coautoria**.

### Distorções Históricas Mitigadas:
1. **Inflação por Quórum Inicial:** PECs exigem quórum de 1/3 de assinaturas (171 deputados ou 27 senadores). Um parlamentar que apenas apoiava regimentalmente recebia a mesma contagem bruta daquele que concebeu, redigiu e liderou a proposta.
2. **Confusão de Autoria Coletiva:** Projetos de Comissões, Mesas Diretoras ou Poder Executivo eram indevidamente atribuídos a membros individuais, inflando artificialmente inventários pessoais.
3. **Equiparação Indevida de Relevância:** Uma moção ou requerimento comemorativo (burocracia) não pode pontuar igualmente a uma Proposta de Emenda à Constituição (PEC) ou Projeto de Lei Complementar (PLP).

---

## 2. Taxonomia de Autoria e Regras de Negócio

Uma proposição legislativa possui quatro categorias de atores rigorosamente distinguidos:
1. **Autor Principal (Primeiro Signatário) ($A = 1.0$):** O parlamentar (indivíduo) que protocolou e liderou a proposição.
2. **Relator com Parecer Aprovado ($A = 0.8$):** Parlamentar encarregado de instruir, sintetizar emendas e aprovar o parecer técnico na comissão ou plenário.
3. **Coautor (Demais Signatários) ($A = 0.2$):** Parlamentares que assinaram conjuntamente para viabilizar quórum regimental de tramitação e demonstrar apoio partidário.
4. **Autor Institucional / Colegiado ($A = 0.0$):** Comissões Temáticas (ex: CCJ), Mesa Diretora, Bancadas Estaduais ou Poder Executivo. Esses casos são isolados em contagem de "Produção Institucional" para evitar atribuição individual indevida aos membros do colegiado.

---

## 3. Módulo 1: Painel Geral de Produtividade (IALP)

Calcula o **Índice de Atividade Legislativa Ponderado (IALP)** para cada parlamentar individual.

### 3.1 Fórmula do IALP por Proposição ($P$)

$$	ext{Score}(P) = T 	imes A 	imes S$$

Onde:
* $T$ = Peso do Tipo de Proposta
* $A$ = Peso do Grau de Autoria
* $S$ = Multiplicador de Sucesso Tramitacional

### 3.2 Matriz de Pesos e Variáveis

#### Tipo de Proposta ($T$)
* **PEC** (Proposta de Emenda à Constituição): **3.0**
* **PLP** (Projeto de Lei Complementar): **2.5**
* **PL / MPV** (Projeto de Lei Ordinária / Medida Provisória): **2.0**
* **PDL / PR / PRC / PDS** (Decreto Legislativo / Resolução): **1.0**
* **REQ / INC** (Requerimento / Indicação Burocrática): **0.1** *(Evita inflar estatísticas com homenagens ou expedientes de rotina)*

#### Grau de Autoria ($A$)
* **Autor Principal:** **1.0**
* **Relator com Parecer Aprovado:** **0.8**
* **Coautor:** **0.2**
* **Institucional / Colegiado:** **0.0**

#### Sucesso de Tramitação ($S$)
* **Apenas Protocolado / Tramitando:** **1.0x**
* **Aprovado em Comissão Temática:** **1.5x**
* **Aprovado em Plenário (Enviado à outra Casa):** **2.0x**
* **Transformado em Norma Jurídica (Sancionado / Promulgado):** **3.0x**
* **Arquivado:** **0.8x**
* **Rejeitado:** **0.5x**

### 3.3 Métricas Derivadas para Exibição na UI
* **Score de Relevância Consolidado:** $\sum 	ext{Score}(P)$ do parlamentar no recorte temporal.
* **Taxa de Eficácia:** Percentual de projetos como *Autor Principal* que avançaram de fase ou viraram lei:
  $$	ext{Taxa de Eficácia} = rac{	ext{Projetos Avançados ou Sancionados como Autor Principal}}{	ext{Total de Projetos Protocolados como Autor Principal}} 	imes 100$$
* **Índice de Desvio de Foco (Proporção Estrutural vs. Burocrática):** Comparativo do volume de propostas de alta complexidade (PEC, PLP, PL) contra o volume de propostas burocráticas (REQ, INC), acompanhado de diagnóstico analítico.

---

## 4. Módulo 2: Gráfico de Redes (Análise de Coautoria)

Modela as relações políticas do Congresso como um **Grafo Não-Direcionado Ponderado**.

### 4.1 Estrutura do Grafo
* **Nós (Vértices):** Parlamentares (Deputados e Senadores).
  * Atributos: `id`, `name`, `party`, `uf`, `house`, `photo_url`, `community`, `betweenness_centrality`, `degree`.
* **Arestas (Conexões):** Existência de coautoria em uma mesma proposição legislativa.
* **Peso da Aresta ($W$):** O número total de projetos assinados conjuntamente por dois parlamentares específicos ($A$ e $B$).

### 4.2 Algoritmos de Redes Requeridos
1. **Detecção de Comunidades (Algoritmo de Louvain):**
   * Agrupamento modular de nós com base na densidade de conexões de coautoria para expor e colorir graficamente as **bancadas informais** (frentes parlamentares, alinhamentos ideológicos e pragmáticos transpartidários), sobrepondo essa cor ao partido oficial.
2. **Centralidade de Intermediação (Betweenness Centrality):**
   * Mensura os parlamentares que funcionam como "pontes" entre agrupamentos distintos (oposição, centro e situação), revelando o nível real de trânsito e capacidade de articulação política.
3. **Filtros de Rede Dinâmicos:**
   * Renderização de subgrafos isolados:
     * *Rede Geral (Todas as Matérias)*
     * *Rede Ideológica de PECs*
     * *Rede Ordinária de Projetos de Lei (PL & PLP)*
     * *Rede Operacional / Burocrática (REQ & INC)*
   * Slider dinâmico de Força Mínima de Conexão ($W \ge 1$ até $W \ge 15$).

---

## 5. Modelagem Relacional e Consultas de Rede

Tabela de junção relacional em PostgreSQL para viabilizar consultas agregadas eficientes e a geração de matrizes de adjacência do grafo:

```sql
CREATE TABLE proposicoes_autores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "proposicaoId" UUID NOT NULL REFERENCES proposicoes(id),
    "politicoId" UUID REFERENCES politicos(id),
    "nomeAutor" VARCHAR(255) NOT NULL,
    "tipoAutoria" VARCHAR(50) NOT NULL, -- 'AUTOR_PRINCIPAL', 'COAUTOR', 'RELATOR', 'INSTITUCIONAL'
    ordem INT NOT NULL,                  -- 1 para Autor Principal, >1 para Coautores
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5.1 Matriz de Conexão da Rede (Query SQL Otimizada)
```sql
SELECT 
    a."politicoId" AS parlamentar_x,
    b."politicoId" AS parlamentar_y,
    COUNT(DISTINCT a."proposicaoId") AS peso_conexao
FROM proposicoes_autores a
INNER JOIN proposicoes_autores b ON a."proposicaoId" = b."proposicaoId"
INNER JOIN proposicoes p ON a."proposicaoId" = p.id
WHERE a."politicoId" < b."politicoId" -- Evita duplicidade simétrica e auto-conexão
  AND a."tipoAutoria" != 'INSTITUCIONAL'
  AND b."tipoAutoria" != 'INSTITUCIONAL'
GROUP BY a."politicoId", b."politicoId"
HAVING COUNT(DISTINCT a."proposicaoId") >= :min_weight
ORDER BY peso_conexao DESC;
```

---

## 6. Exemplo de Aplicação Prática

### PEC 4/2025:
* **Autor Principal (Cleitinho - Republicanos/MG):**
  $$	ext{Score}(P) = 3.0 	ext{ (PEC)} 	imes 1.0 	ext{ (Autor Principal)} 	imes 1.0 	ext{ (Tramitando)} = 3.00	ext{ pts}$$
* **Coautor (Hamilton Mourão - Republicanos/RS):**
  $$	ext{Score}(P) = 3.0 	ext{ (PEC)} 	imes 0.2 	ext{ (Coautor)} 	imes 1.0 	ext{ (Tramitando)} = 0.60	ext{ pt}$$
* **Aresta no Grafo:** Gera conexão de coautoria entre Cleitinho e Hamilton Mourão com peso ponderado cumulativo. O algoritmo de Louvain identifica a forte afinidade de bancada, agrupando-os na mesma bancada informal.


---

## 7. Módulo 3: Histórico de Deliberações e Transparência de Votos

Este módulo estabelece a taxonomia regimental, a modelagem relacional de dados em PostgreSQL e as regras de renderização na interface (UI) para toda e qualquer deliberação legislativa processada pela **Plataforma Cívica LegisData**, garantindo rastreabilidade integral entre o processo decisório nas comissões e no plenário do Congresso Nacional.

### 7.1 Classificação Regimental das Deliberações

Toda matéria legislativa deliberada no Congresso é estritamente categorizada em um de três tipos de evento:

1. **`DELIBERACAO_COMISSAO` (Decisão em Comissão Temática):**
   * Matérias apreciadas e votadas em comissões permanentes ou especiais com poder conclusivo/terminativo (art. 58, § 2º, I da CF/88 e regimentos internos), sem necessidade de deliberação pelo Plenário.
   * *Exemplos:* CCJC (Constituição e Justiça), CFT (Finanças e Tributação), CAS (Assuntos Sociais), CAE (Assuntos Econômicos).

2. **`VOTACAO_SIMBOLICA` (Deliberação por Aclamação Visual):**
   * Matérias de plenário decididas por acordo unânime ou majoritário entre as lideranças partidárias, sem abertura de painel eletrônico nominal individual.
   * *Mecanismo:* O Presidente conclama: *"Os senhores parlamentares que aprovam permaneçam como se encontram"*, e proclama a aprovação.
   * *Controle Cívico:* A fiscalização pública e posicionamento político são obrigatoriamente auditados pela **matriz de orientações partidárias de bancada** formalizadas em ata.

3. **`VOTACAO_NOMINAL` (Deliberação com Painel Eletrônico e Voto Individual):**
   * Matérias de plenário submetidas compulsoriamente a quórum qualificado (ex: PECs, leis complementares) ou por requerimento de votação nominal deferido, com acionamento do painel eletrônico e registro individual e auditável do voto de cada parlamentar (SIM, NÃO, ABSTENÇÃO, OBSTRUÇÃO).

---

### 7.2 Modelagem Relacional de Dados de Votações (SQL)

Para suportar consultas com integridade referencial ao banco de dados relacional (PostgreSQL), as seguintes tabelas estruturam o histórico de deliberações:

```sql
-- Histórico consolidado de eventos deliberativos de proposições
CREATE TABLE votacoes_proposicao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposicao_id UUID NOT NULL REFERENCES proposicoes(id) ON DELETE CASCADE,
    data_hora TIMESTAMP WITH TIME ZONE NOT NULL,
    local_deliberacao VARCHAR(100) NOT NULL, -- Ex: 'Plenário da Câmara dos Deputados', 'CCJC', 'CAS'
    tipo_deliberacao VARCHAR(30) NOT NULL,    -- 'COMISSAO', 'SIMBOLICA', 'NOMINAL'
    resumo_decisao TEXT NOT NULL,             -- Ex: 'Aprovada a redação final em votação simbólica'
    
    -- Metadados de auditoria para DELIBERACAO_COMISSAO
    nome_comissao VARCHAR(150),
    link_ata_reuniao TEXT,
    relator_nome VARCHAR(150),
    parecer_relator_numero VARCHAR(80),
    parecer_relator_texto TEXT,
    link_parecer_relator TEXT,
    
    -- Placar agregado
    total_sim INT NOT NULL DEFAULT 0,
    total_nao INT NOT NULL DEFAULT 0,
    total_abstencao INT NOT NULL DEFAULT 0,
    total_obstrucao INT NOT NULL DEFAULT 0,
    aprovada BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Rastreabilidade individual de votos reais para deliberações do tipo NOMINAL
CREATE TABLE votos_nominais (
    votacao_id UUID NOT NULL REFERENCES votacoes_proposicao(id) ON DELETE CASCADE,
    parlamentar_id UUID NOT NULL REFERENCES politicos(id) ON DELETE CASCADE,
    voto VARCHAR(20) NOT NULL, -- 'SIM', 'NAO', 'ABSTENCAO', 'OBSTRUCAO'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (votacao_id, parlamentar_id)
);

-- Rastreabilidade da orientação formal de cada bancada para deliberações SIMBOLICA ou NOMINAL
CREATE TABLE orientacoes_partidarias (
    votacao_id UUID NOT NULL REFERENCES votacoes_proposicao(id) ON DELETE CASCADE,
    partido_bancada VARCHAR(50) NOT NULL, -- Ex: 'PT', 'PL', 'Bloco GOV', 'MDB', 'PSD', 'Governo', 'Oposição'
    orientacao VARCHAR(20) NOT NULL,       -- 'SIM', 'NAO', 'LIBERADO', 'OBSTRUCAO'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (votacao_id, partido_bancada)
);

-- Índices para performance analítica
CREATE INDEX idx_votacoes_prop_id ON votacoes_proposicao(proposicao_id);
CREATE INDEX idx_votacoes_prop_tipo ON votacoes_proposicao(tipo_deliberacao);
CREATE INDEX idx_votacoes_prop_data ON votacoes_proposicao(data_hora);
CREATE INDEX idx_votos_nominais_parlamentar ON votos_nominais(parlamentar_id);
CREATE INDEX idx_orientacoes_partido ON orientacoes_partidarias(partido_bancada);
```

---

### 7.3 Regras de Exibição na Interface de Usuário (UI)

A interface de transparência cívica adota três regras de renderização especializadas:

1. **Quando `tipo_deliberacao = 'NOMINAL'`:**
   * Renderiza a lista explícita e paginada de `votos_nominais` com foto, nome eleitoral, sigla partidária, UF e distintivo do voto emitido.
   * Disponibiliza o seletor de abas dinâmicas: *Lado a Lado*, *Apenas SIM*, *Apenas NÃO*, *Abstenções* e *Obstruções*.
   * Exibe o campo de busca instantânea com filtro por nome do parlamentar, partido ou estado.
   * Apresenta a barra visual comparativa proporcional de deliberação.

2. **Quando `tipo_deliberacao = 'SIMBOLICA'`:**
   * **Oculta obrigatoriamente o campo de busca nominal individual** e qualquer listagem parlamentar direta (evitando falsas expectativas de voto pessoal onde não houve painel).
   * **Renderiza o aviso educativo institucional ao cidadão**:
     > *Como funciona a Votação Simbólica? No regime de deliberação simbólica, a matéria é decidida no Plenário por acordo visual e aclamação entre as bancadas partidárias, sem abertura de painel eletrônico nominal nem registro individual de voto de cada parlamentar. A fiscalização democrática é garantida pela orientação formal declarada por cada liderança de bancada.*
   * **Renderiza obrigatoriamente a matriz completa de `orientacoes_partidarias`**, com distintivos coloridos para cada bancada (`SIM`, `NÃO`, `LIBERADO`, `OBSTRUÇÃO`).

3. **Quando `tipo_deliberacao = 'COMISSAO'`:**
   * **Oculta o campo de busca nominal individual**.
   * **Exibe com destaque institucional o nome da comissão temático-permanente** onde a matéria foi deliberada terminativamente (ex: *Comissão de Constituição e Justiça e de Cidadania - CCJC*).
   * **Disponibiliza link direto e seguro para a ata oficial da reunião deliberativa** nos portais da Câmara ou do Senado.
   * **Exibe os dados completos do parecer do relator associado**:
     * Nome do relator técnico;
     * Número oficial do parecer (ex: *Parecer nº 08/2024-CCJC*);
     * Ementa e fundamentação conclusiva do parecer;
     * Link de acesso à íntegra do parecer técnico original.

## ROI do Cidadão (nota do dossiê do político)

A nota de 0 a 100 combina três partes e só é calculada quando há CEAP, subsídios registrados e presenças:

| Parte | Peso | Como é medida |
|-------|------|---------------|
| Assiduidade | 30% | Taxa de presença em plenário (faltas justificadas não contam como presença). |
| Entrega legislativa | 40% | Pontos IALP do parlamentar (tipo da proposição x papel do autor x andamento, pesos em `param.peso`). 100 pontos dão a nota máxima nesta parte. |
| Custo | 30% | Custo operacional (CEAP + subsídios brutos registrados) dividido pelos pontos IALP. Zera quando o custo chega a R$ 100.000 por ponto. |

Faixas: A+ a partir de 85, A a partir de 70, B a partir de 55, C a partir de 40 e D abaixo disso.

Até a versão anterior a parte de entrega era a contagem de proposições "de impacto" (10 proposições davam o máximo) e o custo era dividido por essa contagem. Isso premiava quem apenas assinava projetos e requerimentos de outros parlamentares: um senador com 8 projetos próprios e 64 assinaturas de apoio chegava a A+ com IALP de 31 pontos. Com os pontos IALP, a assinatura de apoio vale pouco (0,05 em PEC, 0,2 nos demais tipos) e o avanço na tramitação passa a decidir a nota.

As referências (100 pontos e R$ 100.000 por ponto) são constantes de `backend/app/api/v1/politicians.py` e podem ser recalibradas com a distribuição real dos parlamentares.
