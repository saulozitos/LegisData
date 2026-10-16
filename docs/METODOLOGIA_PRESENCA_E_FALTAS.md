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
- Só entra quem tem ao menos uma presença no mesmo ano: mandato cadastrado como em exercício sem comparecer a nenhum dia
  é cadastro desatualizado (por exemplo, legislatura anterior com situação ainda aberta), e não ausência. Sem essa
  trava, 268 parlamentares recebiam 106 faltas inventadas em 2019.
- Começa em 2003 porque só a partir da 52ª legislatura existem as situações de exercício, licença e suplência.

## Senado

A presença é derivada das votações nominais: voto, `P-NRV` ou presidência da sessão contam como presente; `AP`, `MIS`,
`LS` e `LP` são ausências justificadas; `NCom` (não compareceu) é ausência sem justificativa. Os códigos `REP`, `LA`,
`LAP`, `LG`, `MERC` e `P-OD` não têm significado confirmado e não entram na contagem. A unidade é o dia com votação
nominal, e o partido de cada dia vem da sigla informada pelo Senado na própria votação.

## Taxa e rankings

- A taxa de presença do dossiê usa só dias em que a falta é conhecida (Senado sempre; Câmara de 2003 em diante). Os
  marcos de cada Casa ficam em `ref.cobertura_presenca` (`falta_desde` e `justificativa_desde`) e os tipos de falta
  justificada em `ref.tipo_presenca.justificada`; a visão `leg.vw_presenca_conhecida` aplica os dois e é a fonte do
  dossiê e dos rankings.
- Categoria que o período não permite saber vem como `null`, nunca como zero: faltas justificadas e não justificadas
  são `null` quando nenhum dia do recorte tem fonte que informe justificativa (Câmara antes de 2020), e faltas
  inferidas são `null` quando nenhum dia do recorte é inferido (Senado e Câmara desde 2020). Em períodos mistos, as
  justificadas e as não justificadas contam só os dias em que a fonte as informa; `total_faltas` e `taxa` valem para
  todos os dias medidos.
- `GET /attendance/ranking/politicians` ordena por faltas, taxa de ausência, faltas sem justificativa ou
  "falta muito e produz pouco" (taxa de ausência ÷ (100 + pontos IALP)). Taxa e esse índice exigem 20 dias registrados.
- `GET /attendance/ranking/parties` calcula a taxa de ausência de cada partido (faltas ÷ dias de todos os seus
  parlamentares), com mínimo de 2.000 dias registrados.
- `GET /attendance/coverage` mostra a cobertura por ano, Casa e origem para auditar lacunas.

## Carga

`python etl/run_etl.py --presenca` baixa os arquivos da Câmara e extrai portal e Senado; `--load-presenca` grava em
`leg.presenca`. Cada origem apaga e regrava só as próprias linhas, então é seguro repetir. Senadores e deputados sem
cadastro recebem uma pessoa mínima (nome e identificador oficial, nunca CPF).

Salvaguardas da carga:

- A carga dos arquivos de eventos da Câmara recusa a execução, antes de qualquer alteração, se faltar o arquivo de algum
  ano pedido, e só apaga as linhas `CAMARA_CSV` dos anos que está regravando. Carregar um ano isolado não remove a história
  dos demais.
- Uma fonte oficial (portal da Câmara ou Senado) que chega sem nenhuma linha não apaga a base: a carga registra um aviso e
  deixa as linhas como estão.
- Linhas dos arquivos com identificador ou data inválidos são puladas e contadas em log, sem abortar a carga inteira.
- Os nomes de deputados sem cadastro são consultados na API antes de abrir a transação do banco.

## Partido de cada dia

O ranking por partido usa `leg.presenca.partido_id`, resolvido por `etl.resolver_partido_presenca()` na ordem: sigla da
votação (Senado), partido do mandato no dia, filiação vigente no dia e, por último, o partido da presença mais próxima
do mesmo parlamentar. `partido_origem` registra qual regra valeu (`VOTACAO`, `MANDATO`, `FILIACAO` ou
`PRESENCA_PROXIMA`), e a API informa quantos dias têm partido aproximado e quantos continuam sem partido (esses dois
totais não dependem do mínimo de dias por partido). Na aproximação, a presença mais próxima da mesma Casa vence a de
outra Casa e o empate se resolve pela data mais recente, de modo que duas execuções dão o mesmo resultado.
`etl.sincronizar_legado_leg()` chama o resolvedor ao terminar, porque regrava as linhas de presença do legado sem
partido.

O partido "atual" de um parlamentar (filtros e rótulos de partido dos rankings e do explorador) vem de uma só definição,
a visão `core.vw_partido_atual`: histórico do mandato vigente, depois filiação aberta, depois o partido do mandato mais
recente. Parlamentares sem nenhum mandato nem filiação no schema novo (deputados de 2001 a 2008 que só aparecem nos
arquivos de presença) não têm como ter partido identificado e ficam em `dias_sem_partido_identificado`.

## Atualização automática

`make daily` roda `etl.pipelines.cron_daily_consolidation`, que inclui a atualização incremental de presença
(`etl.pipelines.presenca_atualizacao`): baixa os arquivos de eventos do ano corrente e do anterior, extrai o portal de todos os deputados das legislaturas
(sem restringir, para não apagar dias de quem já saiu), reaproveita o cache dos meses fechados do Senado e regrava as linhas
oficiais. Se a extração tiver falhas, a carga não é executada (evita apagar dias já gravados) e a execução fica
registrada como FALHA em `LogExecucaoCron`, sem interromper as demais etapas.

A mesma consolidação atualiza as votações nominais (`etl.pipelines.votacoes_atualizacao`): extrai o ano anterior e o
corrente e carrega só as votações no schema legado. A ponte para `leg` roda uma única vez por execução, na etapa de
sincronização de mandatos, e a presença vem depois dela (para que o partido dos dias vindos do legado seja resolvido
sobre dados já sincronizados). O extrator do Senado completa a lista anual da API (que atrasa semanas) com as votações
nominais por data do plenário, mas essas sessões chegam sem ementa e sem orientação de bancada. Se a consulta de algum mês
do plenário falhar, o arquivo do ano não é regravado (regravar sem aquele mês apagaria suas sessões) e o mês aparece em
`falhas` do resumo da extração. Enquanto não chega 1º de março, o cache do ano anterior também expira em 24 horas, porque a
lista anual do Senado fecha com atraso.

## Operação no servidor

Instalação do agendamento:

1. Crie o usuário de serviço sem shell (`useradd --system --home /opt/legisdata --shell /usr/sbin/nologin legisdata`) e
   deixe `/opt/legisdata/etl/data` gravável por ele. O restante do projeto pode ficar somente leitura.
2. O `.env` do projeto (`DATABASE_URL`, `POSTGRES_PASSWORD`) deve pertencer ao usuário `legisdata` com `chmod 600`. A
   `DATABASE_URL` precisa apontar para um host alcançável a partir do servidor: no compose de produção a porta do Postgres
   não é publicada, então publique-a só em `127.0.0.1` ou rode o job dentro da rede do compose.
3. Copie `scripts/systemd/legisdata-diario.service` e `.timer` para `/etc/systemd/system/`, ajuste o caminho do projeto e
   rode `systemctl enable --now legisdata-diario.timer`. O service usa `flock` para impedir duas execuções simultâneas
   (por exemplo, o timer junto de um `make daily` manual).

O job regrava arquivos versionados em `etl/data/processed/` (resumos de presença e arquivos de votações). Num checkout de
produção isso deixa a árvore do git "suja": use `git stash`/`git checkout -- etl/data/processed` antes de um `git pull`, ou
mantenha o diretório de dados fora do repositório.

## Deploy das migrações

As migrações 0015 a 0020 reconstroem a ponte do legado (`TRUNCATE` de votos e orientações, reescrita de presença) e podem
levar mais que os 60 segundos do `gunicorn`. Como a API aplica as migrações no boot, uma migração demorada pode ser
interrompida e reiniciada em ciclo. Ao publicar uma versão nova:

1. Faça backup do banco (`pg_dump`) antes.
2. Rode `make db-migrate` com a imagem nova **antes** de subir a API (fora do `gunicorn`) e meça o tempo.
3. Só então suba a imagem nova. Enquanto a migração roda, as leituras de votos ficam bloqueadas.
