# Pessoas cadastradas duas vezes em `core.pessoa`

Levantamento feito no banco de desenvolvimento em 16/10/2026, na migration 0024. Nada foi unificado: este documento só
registra os casos, a causa provável, o efeito nas telas e a regra proposta para resolver depois. A unificação está
fora do escopo da entrega 2C e entra no planejamento da entrega 3 (limpeza do legado).

## Resumo

| Medida | Valor |
|--------|-------|
| Pessoas em `core.pessoa` | 3.384 |
| Grupos de pessoas com o mesmo nome (sem acento e sem diferença de maiúsculas) | 468 |
| Cadastros dentro desses grupos | 969 |
| Cadastros desses grupos sem nenhum identificador oficial | 329 |
| Votos nominais pendurados nesses cadastros sem identificador | 311.379 de 1.262.239 |
| Cadastros com identificador da Câmara em grupo duplicado | 441 |
| Cadastros com identificador do Senado em grupo duplicado | 199 |

O critério é o mesmo de `ref.normalizar_texto(nome_exibicao)`. Ele encontra homônimos de verdade além de duplicatas,
por isso cada grupo precisa de conferência antes de unir (ver "Regra proposta").

## Os quatro padrões

### 1. Cadastro do legado sem identificador × cadastro novo com identificador (328 grupos)

É o caso mais comum e o que mais afeta as telas. A pessoa existe duas vezes:

- Uma pessoa criada a partir de `stg.politicos` pela fusão do staging (fonte 11), **sem** `CAMARA_ID`/`SENADO_ID`,
  com o mandato de 2019 em diante e todos os **votos nominais** (`leg.voto`).
- Outra pessoa criada pelas cargas novas (arquivos da Câmara e presença, fonte 2), **com** `CAMARA_ID`, com a
  **presença** (`leg.presenca`) e a **autoria** (`leg.autoria`), mas sem voto.

Exemplos (ids de `core.pessoa`):

| Nome | Com identificador | Sem identificador | Votos no cadastro sem identificador | Presenças/autorias no cadastro com identificador |
|------|-------------------|-------------------|-------------------------------------|---------------------------------------------------|
| Abílio Santana | 2551 (`CAMARA_ID` 204554) | 4940 | 1.465 | 430 / 20 |
| Abou Anni | 2534 (`CAMARA_ID` 204521) | 4941 | 1.611 | 448 / 96 |
| Alessandro Molon | 2122 (`CAMARA_ID` 160511) | 4744 | 1.386 | 1.254 / 854 |
| Alexandre Frota | 2544 (`CAMARA_ID` 204544) | 4943 | (no 4943) | 448 / 776 |
| André de Paula | 1518 (`CAMARA_ID` 74471) | 4946 | (no 4946) | 1.606 / 398 |

Números: 323 cadastros sem identificador têm voto; 6 têm só mandato; nenhum está vazio. Em 299 dos 328 grupos há
exatamente um cadastro com identificador, o que torna a união direta. Os outros 29 grupos têm mais de um candidato com
identificador e exigem decisão manual.

Há ainda 31 grupos com três ou mais cadastros (por exemplo Aelton Freitas: 1907 com `CAMARA_ID`, 3991 com `SENADO_ID` e 5179 sem
identificador) e 23 pessoas sem identificador sem nenhum homônimo: são presidentes, ministros e ex-ministros criados
pela ponte (por exemplo Fernando Henrique Cardoso, id 740), que não é duplicata.

### 2. Mesma pessoa na Câmara e no Senado (150 grupos)

O deputado que virou senador aparece com um `CAMARA_ID` num cadastro e um `SENADO_ID` em outro, por exemplo Aécio Neves
(24 e 3930), Álvaro Dias (1150 e 3964) e Alexandre Silveira (1909 e 4085). Aqui as duas linhas são a mesma pessoa de
fato: o cadastro do Senado guarda a presença em votações do Senado (243 linhas para Aécio) e o da Câmara guarda a
autoria e o mandato de deputado.

Efeito: o dossiê de quem passou pelas duas Casas mostra só metade da vida legislativa, e os rankings de autores e de
ausências contam essa pessoa duas vezes, cada uma com a metade dos números.

Alan Rick (48 com `SENADO_ID` 5672; 2307 com `CAMARA_ID` 178836) é o inverso: o cadastro 48 já tem os dois mandatos
(deputado e senador) mas só o identificador do Senado, enquanto o 2307 tem o da Câmara.

### 3. Dois `CAMARA_ID` diferentes com o mesmo nome (21 grupos) e dois `SENADO_ID` (1 grupo)

Nem tudo é duplicata. A lista abaixo separa os casos por evidência.

**Homônimos prováveis (não unir sem conferir data de nascimento e mandatos):** Átila Lira (100, nascido em 1980, e
1507, deputado desde 1995), Mariana Carvalho (290, nascida em 1994, e 2395), Reinhold Stephanes (187 e 1000),
Bebeto (686 e 2306), João Carlos Bacelar (542 e 1224) e os demais em que as duas linhas têm mandato e presença próprios
em legislaturas diferentes.

**Duplicatas prováveis (linha em caixa alta, sem mandato e sem presença, criada por autoria de proposição):**
ANDRE FERNANDES (1830), BILAC PINTO (1837), JOSE GUIMARAES (1833), JOSIAS GOMES (1842), ROCHA LOURES (1834) e
JOÃO MAIA (1267), cada uma com um cadastro maior no mesmo grupo. Esses cadastros em caixa alta vêm das autorias de
proposições do legado.

**Sem decisão possível só pelo banco:** os pares em que as duas linhas têm mandato e presença em períodos diferentes
(por exemplo Antônio Andrade, 500 e 1922, e Ricardo Izar, 877 e 2224). A Câmara muda o identificador de um deputado ao
longo do tempo em alguns casos, mas isso não está confirmado nos dados abertos.

### 4. Ministro cadastrado à parte do deputado

Antonio Palocci aparece como deputado (1673, `CAMARA_ID` 74701) e como ministro (748, sem identificador, mandato de
ministro de 2003 a 2006). A ponte cria uma pessoa de ministro pelo nome (`md5('ministro:' || nome)`) quando o ministro
não está ligado a um político do legado. Outros ministros que também foram parlamentares seguem o mesmo caminho.

## Efeito nas telas e no dossiê

- **Votos, presença e autoria ficam em cadastros diferentes** (padrão 1). Quem abrir o dossiê pelo cadastro com
  identificador vê presença e autoria, mas nenhum voto; quem abrir pelo cadastro sem identificador vê o inverso. Os
  rankings de presença e de autores só enxergam a metade da pessoa.
- **O identificador oficial é o que a ETL e as telas novas usam**; o cadastro do legado só continua aparecendo porque as
  tabelas de voto e de mandato apontam para ele.
- **Contagens de pessoas estão infladas** em até 501 unidades (437 grupos de dois cadastros e 31 de três ou mais; parte são homônimos), o que afeta
  qualquer "quantos parlamentares" calculado em cima de `core.pessoa`.
- O ranking de partidos e o partido atual (`core.vw_partido_atual`) dependem do mandato, que está no cadastro sem
  identificador; por isso a presença do cadastro com identificador acaba sem partido ou com partido aproximado
  (`dias_com_partido_aproximado`).

## Como reproduzir o levantamento

```sql
-- grupos com o mesmo nome normalizado
SELECT ref.normalizar_texto(nome_exibicao) AS nome, array_agg(id ORDER BY id) AS pessoas
FROM core.pessoa
GROUP BY 1
HAVING count(*) > 1;

-- cadastros sem identificador oficial que têm voto
SELECT p.id, p.nome_exibicao, count(v.*) AS votos
FROM core.pessoa p
JOIN leg.voto v ON v.pessoa_id = p.id
WHERE NOT EXISTS (SELECT 1 FROM core.pessoa_identificador i WHERE i.pessoa_id = p.id)
GROUP BY 1, 2
ORDER BY votos DESC;
```

## Regra proposta para unificar (a decidir)

1. **Chave de união**: mesmo nome normalizado **e** pelo menos uma coincidência forte (data de nascimento, mesma
   legislatura e mesma UF no mandato, ou um identificador oficial em comum). Nome igual sozinho não basta, por causa dos
   homônimos do padrão 3.
2. **Pessoa sobrevivente**: a que tem identificador oficial. Mover para ela `leg.voto`, `core.mandato` e
   `core.mandato_legado`, `core.pessoa_nome` e as demais referências a `pessoa_id`; guardar o `uid` da pessoa removida
   numa tabela de redirecionamento (os links antigos do dossiê usam `uid`).
3. **Conflitos de chave primária**: `leg.voto` tem chave `(votacao_id, pessoa_id)`. Se as duas pessoas votaram na
   mesma votação, vale o voto da fonte oficial.
4. **Câmara e Senado**: a pessoa sobrevivente passa a ter os dois identificadores, e o cadastro do outro é removido.
5. **Homônimos confirmados**: ficam separados e ganham a data de nascimento como diferenciador no nome de exibição das
   telas de busca.
6. **Prevenção**: a ponte do legado (`etl.merge_legislativo`) e as cargas de presença devem procurar a pessoa por
   identificador oficial antes de criar uma nova. Hoje criam sem checar o cadastro do outro lado.
7. **Teste de regressão**: depois da unificação, `SELECT` do levantamento acima deve devolver só os homônimos
   confirmados, e a soma de votos, presenças e autorias antes e depois da união tem que ser igual.

## Fora do escopo

Esta entrega não mexe nos cadastros. Os números do dossiê e dos rankings seguem a definição atual (uma linha de
`core.pessoa` é uma pessoa) e a limitação está registrada aqui para quem for decidir a unificação.
