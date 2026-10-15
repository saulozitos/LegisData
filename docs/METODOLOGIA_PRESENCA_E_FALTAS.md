# Presença, faltas e justificativas (1995 em diante)

Tudo é gravado em `leg.presenca` (uma linha por parlamentar, Casa e dia), com a origem em `fonte_id`. O tipo da linha é
um código de `ref.tipo_presenca`.

## O que cada fonte oferece

| Casa e período | Fonte | Presença | Falta | Justificativa |
|----------------|-------|----------|-------|----------------|
| Câmara, 2020 em diante | Portal da Câmara, relatório "Presença em Plenário" (`CAMARA_PORTAL`) | sim | sim | sim |
| Câmara, 2003 a 2019 | Arquivos de eventos e de presença em eventos (`CAMARA_CSV`) | sim | **inferida** | não |
| Câmara, 2001 e 2002 | Mesmos arquivos | parcial (2001 quase vazio) | não | não |
| Câmara, 1995 a 2000 | Os arquivos trazem presença de apenas um parlamentar por ano | não | não | não |
| Senado, 1995 em diante | Votações nominais de plenário (`SENADO_API`) | sim | sim (`NCom`) | sim (AP, MIS, LS, LP) |

A Câmara não publica, em dados abertos, a frequência de plenário anterior a 2020, e as votações nominais digitais
começam no fim de 2001. Por isso não há como obter presença confiável de 1995 a 2000 sem inventar dado; esses anos
ficam sem registro e a tela avisa.

## Falta inferida (Câmara, 2003-02-03 a 2019)

Um dia conta como sessão realizada quando há ao menos uma sessão deliberativa do plenário com 52 presentes ou mais (um
décimo da Casa, mínimo regimental para abrir). Num desses dias, o deputado em exercício (situação `EXERCICIO` ou
`SUPLENCIA` em `core.mandato_situacao`) que não aparece em nenhuma sessão é registrado como `AUSENCIA_INFERIDA`.

- Nunca é misturada com a falta oficial: o dossiê, a API e as telas mostram a contagem separada.
- Não tem justificativa: a fonte não a informa.
- Começa em 2003 porque só a partir da 52ª legislatura existem as situações de exercício, licença e suplência.

## Senado

A presença é derivada das votações nominais: voto, `P-NRV` ou presidência da sessão contam como presente; `AP`, `MIS`,
`LS` e `LP` são ausências justificadas; `NCom` (não compareceu) é ausência sem justificativa. Os códigos `REP`, `LA`,
`LAP`, `LG`, `MERC` e `P-OD` não têm significado confirmado e não entram na contagem. A unidade é o dia com votação
nominal, e o partido de cada dia vem da sigla informada pelo Senado na própria votação.

## Taxa e rankings

- A taxa de presença do dossiê usa só dias em que a falta é conhecida (Senado sempre; Câmara de 2003 em diante).
- `GET /attendance/ranking/politicians` ordena por faltas, taxa de ausência, faltas sem justificativa ou
  "falta muito e produz pouco" (taxa de ausência ÷ (100 + pontos IALP)). Taxa e esse índice exigem 20 dias registrados.
- `GET /attendance/ranking/parties` calcula a taxa de ausência de cada partido (faltas ÷ dias de todos os seus
  parlamentares), com mínimo de 2.000 dias registrados.
- `GET /attendance/coverage` mostra a cobertura por ano, Casa e origem para auditar lacunas.

## Carga

`python etl/run_etl.py --presenca` baixa os arquivos da Câmara e extrai portal e Senado; `--load-presenca` grava em
`leg.presenca`. Cada origem apaga e regrava só as próprias linhas, então é seguro repetir. Senadores e deputados sem
cadastro recebem uma pessoa mínima (nome e identificador oficial, nunca CPF).

## Partido de cada dia

O ranking por partido usa `leg.presenca.partido_id`, resolvido por `etl.resolver_partido_presenca()` na ordem: sigla da
votação (Senado), partido do mandato no dia, filiação vigente no dia e, por último, o partido da presença mais próxima
do mesmo parlamentar. `partido_origem` registra qual regra valeu (`VOTACAO`, `MANDATO`, `FILIACAO` ou
`PRESENCA_PROXIMA`), e a API informa quantos dias têm partido aproximado e quantos continuam sem partido.

## Atualização automática

`make daily` roda `etl.pipelines.cron_daily_consolidation`, que inclui a atualização incremental de presença
(`etl.pipelines.presenca_atualizacao`): baixa os arquivos de eventos do ano corrente e do anterior, extrai o portal de todos os deputados das legislaturas
(sem restringir, para não apagar dias de quem já saiu), reaproveita o cache dos meses fechados do Senado e regrava as linhas
oficiais. Se a extração tiver falhas, a carga não é executada (evita apagar dias já gravados) e a execução fica
registrada como FALHA em `LogExecucaoCron`, sem interromper as demais etapas.

Para agendar no servidor, copie `scripts/systemd/legisdata-diario.service` e `.timer` para `/etc/systemd/system/`,
ajuste o diretório do projeto e rode `systemctl enable --now legisdata-diario.timer`. O processo precisa alcançar o
Postgres (no compose de produção a porta não é publicada; use `docker-compose.dev.yml` ou rode dentro da rede do compose).

A mesma consolidação atualiza as votações nominais (`etl.pipelines.votacoes_atualizacao`): extrai o ano anterior e o
corrente, carrega só as votações e sincroniza com `leg`. O extrator do Senado completa a lista anual da API (que atrasa
semanas) com as votações nominais por data do plenário, mas essas sessões chegam sem ementa e sem orientação de bancada.
