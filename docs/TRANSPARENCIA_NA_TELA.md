# Transparência na tela: cobertura, objeto da votação, mudança de partido, links, cartões e relatos de erro

Resposta ao feedback de um usuário da plataforma. Cada ponto abaixo é dado de domínio no banco (não constante no código) e tem teste.

## 1. Cobertura de cada painel

`GET /api/v1/cobertura` devolve, por painel (`votacoes`, `proposicoes`, `parlamentares`, `presenca`, `gastos`): fonte, período que a
base cobre, quantidade de registros, data da última carga bem-sucedida e se a base está **completa** ou **parcial**.

- A tabela `ref.cobertura_painel` guarda o nome da fonte, as fontes do ETL que alimentam o painel e o ano em que a base pretende
  começar (`inicio_alvo`). A visão `ref.vw_cobertura_painel` junta a data da última carga (`etl.execucao`), que a API não lê direto.
- O período e a contagem vêm das tabelas de domínio (`cobertura_service.py`). Parcial = período real começando depois do ano-alvo
  (hoje, as votações nominais começam em 2019 e o alvo é 1995). Sem registro, o painel vem `SEM_DADOS`, nunca com período inventado.
- O texto do calendário deixou de dizer "o Congresso realizou votações em apenas N dias" e passou a "a base tem N dias com votação
  nominal cadastrados", dizendo que isto é cobertura da base, não a atividade inteira do Congresso.
- Na tela, `CoberturaDoPainel` aparece no calendário, no monitor do Congresso, na presença, nas emendas e na fidelidade.

## 2. O que foi votado

A fonte só traz o texto livre da deliberação. `ref.objeto_votacao` (rótulo, explicação e se decide o mérito) e
`ref.objeto_votacao_regra` (regex do Postgres, primeira que casa vence) classificam em: requerimento de urgência, requerimento,
destaque, emenda, parecer, redação final e texto principal. Sem regra que case, o objeto é `null` e a tela diz que a fonte não
informa. Objetos que não decidem o mérito mostram um aviso ao lado do placar (por exemplo, "aprovar a urgência não aprova o
projeto"). Está no calendário, no explorador, no monitor do Congresso e no modal de votos (`objeto_votacao_service.py`).
Para ajustar uma regra, edite a linha em `ref.objeto_votacao_regra` (migração de dados).

## 3. Troca de partido versus mudança de nome

Passar de PMDB para MDB não é troca. `filiacao_service.py` classifica cada filiação em relação à anterior:

| Tipo | Quando | Conta como troca |
|---|---|---|
| `INICIAL` | primeira filiação | não |
| `RENOMEACAO` | mesma linhagem (`core.partido.linhagem_id`: PMDB→MDB, PFL→DEM...) | não |
| `FUSAO`, `INCORPORACAO`, `SUCESSAO` | par em `core.partido_sucessao` (DEM+PSL=UNIÃO, PTB+Patriota=PRD, PHS e PSC→PODE, PPL→PCdoB, PROS→Solidariedade, PRP→Patriota) | não |
| `TROCA` | qualquer outra mudança | sim |

As fusões e incorporações vêm de `ref.partido_sucessao_semente` (migração 0041) e `etl.aplicar_linhagens()` as grava em
`core.partido_sucessao`. A data só consta onde é certa (UNIÃO, 08/02/2022). O dossiê, a análise de fidelidade (ganhos, perdas e
quem mais trocou) e as telas usam a mesma classificação.

## 4. Links diretos e cartões

A página inicial lê e escreve na URL o que a tela mostra: `?aba=`, `politico=`, `secao=` (seção da ficha), `partido=`,
`proposicao=` (abre a votação) e `q=` (busca por assunto). O comparador usa `?m1=&m2=`. `Compartilhar` copia o link e baixa um
cartão em imagem (PNG gerado no navegador, `lib/compartilhar.ts`); o cartão **exige** fonte, data, período e etapa (o que foi
votado) e não é gerado sem eles. Aparece na ficha do político, no modal de votos e no comparador.

## 5. Entrada com perguntas simples

`EntradaRapida`: "Como meu deputado votou?", "Quem financiou a campanha?", "Para onde foram as emendas?" e busca por assunto (com
atalhos escala 6x1, salário mínimo, impostos e violência contra a mulher) levam direto à consulta certa.

## 6. Notas e classificações com critério visível

As classificações automáticas dizem por que decidiram:

- Proposta simbólica ou comemorativa: por palavra-chave no título, na ementa ou na área. O dossiê devolve a palavra que decidiu
  (`palavras_encontradas`) e a lista inteira (`relevancia_legislativa.criterio`), com o aviso de que pode errar. Os rótulos
  "leis inúteis", "impacto estrutural" e "foco em pautas simbólicas" saíram: as demais propostas são "sem marca simbólica", sem
  afirmar que têm impacto.
- Nota ROI do Cidadão: a tela mostra a metodologia e a escala inteira (`faixas`); o texto da faixa D deixou de dizer "baixo
  retorno" e descreve a faixa.
- Cada classificação tem "Discorda desta classificação?", ligado à proposição ou à nota.

## 7. "Encontrou uma informação incorreta?"

`POST /api/v1/feedback/erros` grava o relato em `etl.relato_erro` (tabela interna, fora dos schemas de leitura) com o alvo
(político, votação, proposição, partido, painel ou classificação), a seção, a página e um contato opcional. O texto com CPF é
recusado (D3) e há um campo-isca contra robôs. O `POST` é a única escrita pública da API (`allow_methods` do CORS inclui `POST`).

Para ler os relatos novos no servidor:

```sh
docker exec politica_postgres psql -U politica_user -d politica_db -c \
  "SELECT id, criado_em, alvo_tipo, alvo_rotulo, secao, descricao, contato, pagina FROM etl.relato_erro WHERE status = 'NOVO' ORDER BY id"
```

Depois de tratar, `UPDATE etl.relato_erro SET status = 'CORRIGIDO' WHERE id = ...` (`EM_ANALISE`, `CORRIGIDO` ou `DESCARTADO`).

## 8. Participe (Votações): abertas por padrão e atualizado todo dia

A tela abre filtrada nas **votações abertas** (o botão "Todas" e "Encerradas" continuam à mão) e não tem mais a etiqueta "Ao Vivo":
a lista é uma foto diária, e a tela diz "Atualizado em ..." (com aviso se a última coleta tem mais de 36 horas). A API
(`/api/v1/cidadania/consultas`) lê `leg.consulta_publica`; quem grava é o job diário `etl.pipelines.cidadania_atualizacao`, dentro do
`legisdata-cadastro.timer` (detalhes em `docs/DEPLOY_AUTOMATICO.md`). Enquanto o banco não tem nenhuma coleta, a API cai na coleta
direta em memória, como era antes.

