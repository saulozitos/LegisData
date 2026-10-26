#!/usr/bin/env bash
# Deploy automático do LegisData no servidor: roda a cada poucos minutos (timer do systemd do usuário) e, quando há
# commit novo na main com as imagens publicadas no GHCR, faz nesta ordem:
#   1. backup do banco (pg_dump) -> 2. atualiza o código (ff-only) -> 3. migrações -> 4. carga das séries econômicas
#   -> 5. sobe as imagens novas -> 6. confere a saúde; se falhar, volta para as imagens anteriores.
# O banco só é tocado depois do backup, e o estado só avança quando tudo termina bem (a próxima execução tenta de novo).
set -Eeuo pipefail

# LEGISDATA_DIR aponta para o checkout do projeto. O timer o recebe do systemd; numa execução manual vem do mesmo arquivo.
[[ -z "${LEGISDATA_DIR:-}" && -f "$HOME/.legisdata-deploy/ambiente" ]] && . "$HOME/.legisdata-deploy/ambiente"
RAIZ="${LEGISDATA_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ESTADO_DIR="${DEPLOY_STATE_DIR:-$HOME/.legisdata-deploy}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
REDE="${DEPLOY_NETWORK:-legisdata_default}"
REGISTRO="${DEPLOY_REGISTRY:-ghcr.io/saulozitos}"
# >>> guardar_backups
GUARDAR_BACKUPS="${DEPLOY_KEEP_BACKUPS:-14}"
# vem do ambiente e entra em contexto aritmético: só inteiro positivo (um valor inválido apagaria todos os dumps)
[[ "$GUARDAR_BACKUPS" =~ ^[1-9][0-9]{0,3}$ ]] || GUARDAR_BACKUPS=14
# <<< guardar_backups
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

log() { printf '%s [deploy] %s\n' "$(date '+%F %T')" "$*"; }

# >>> pendencias
# Tarefas de finanças que o deploy não conseguiu terminar e que a próxima execução (ou o instalar.sh) precisa cumprir:
#   carga      - a carga de finanças falhou numa tolerância: tentar de novo mesmo sem commit novo (no máximo uma vez por
#                hora, para uma falha que não se resolve sozinha não virar um deploy completo a cada 2 minutos);
#   refrescar  - o commit pediu a atualização diária e a unit ainda não existia (ou não disparou).
PENDENTE="${ESTADO_DIR}/financas_pendente"
CARGA_TENTADA="${ESTADO_DIR}/financas_carga_tentada"
INTERVALO_DA_CARGA="${INTERVALO_DA_CARGA:-3600}"
[[ "$INTERVALO_DA_CARGA" =~ ^[0-9]+$ ]] || INTERVALO_DA_CARGA=3600
pendente_tem() { [[ -f "$PENDENTE" ]] && grep -qx "$1" "$PENDENTE"; }
pendente_marca() { pendente_tem "$1" || printf '%s\n' "$1" >>"$PENDENTE"; }
pendente_limpa() {
  [[ -f "$PENDENTE" ]] || return 0
  grep -vx "$1" "$PENDENTE" >"$PENDENTE.novo" || true
  if [[ -s "$PENDENTE.novo" ]]; then mv "$PENDENTE.novo" "$PENDENTE"; else rm -f "$PENDENTE.novo" "$PENDENTE"; fi
}
carga_pode_repetir() { # há carga pendente e a última tentativa tem mais de INTERVALO_DA_CARGA segundos
  pendente_tem carga || return 1
  local tentada
  tentada="$(cat "$CARGA_TENTADA" 2>/dev/null || true)"
  [[ "$tentada" =~ ^[0-9]+$ ]] || return 0 # sem carimbo legível, repete
  (($(date +%s) - tentada >= INTERVALO_DA_CARGA))
}
disparar_financas() { # dispara a atualização diária; falha se a unit não existe ou o systemd não aceitou
  systemctl --user cat legisdata-financas.service >/dev/null 2>&1 || return 1
  systemctl --user start --no-block legisdata-financas.service
}
# <<< pendencias

mkdir -p "$ESTADO_DIR" "$BACKUP_DIR"
chmod 700 "$ESTADO_DIR" # guarda o estado do deploy e, sem XDG_RUNTIME_DIR, o arquivo de ambiente com a senha
# Os dumps têm o banco inteiro: só o dono lê (inclusive os de execuções anteriores).
chmod 700 "$BACKUP_DIR"
chmod 600 "$BACKUP_DIR"/legisdata_*.dump 2>/dev/null || true
# Depois de se reexecutar (abaixo) o lock já está aberto no descritor 9, herdado do processo anterior.
# O --dry-run não altera nada, então não disputa o lock (senão, com a atualização das finanças rodando, ele sairia "ok" sem testar).
# >>> trava_do_deploy
# LEGISDATA_DEPLOY_LOCK (a mesma variável que a atualização das finanças lê) leva o lock para um diretório que outro usuário alcance
if [[ -z "${_LEGISDATA_DEPLOY_REEXEC:-}" && $DRY_RUN -eq 0 ]]; then
  exec 9>"${LEGISDATA_DEPLOY_LOCK:-$ESTADO_DIR/deploy.lock}"
  flock -n 9 || { log "outra execução em andamento"; exit 0; }
fi
# <<< trava_do_deploy

cd "$RAIZ"
git fetch -q origin main
# Numa reexecução o alvo é o da primeira execução: o script e o commit implantado não podem divergir.
# >>> alvo
ALVO="${_LEGISDATA_DEPLOY_ALVO:-$(git rev-parse origin/main)}"
[[ "$ALVO" =~ ^[0-9a-f]{40}$ ]] || { log "alvo inválido ($ALVO); abortando"; exit 1; }
# <<< alvo
# >>> alvo_na_main
# o alvo herdado do ambiente também precisa ser um commit da main (um SHA qualquer de 40 hex não basta)
git merge-base --is-ancestor "$ALVO" origin/main 2>/dev/null || { log "alvo $ALVO não é ancestral de origin/main; abortando"; exit 1; }
# <<< alvo_na_main
TAG="${ALVO:0:7}"
ATUAL="$(cat "$ESTADO_DIR/ultimo_sha" 2>/dev/null || true)"
# >>> mesmo_commit
# Numa reexecução (a cópia instalada do script era outra) a primeira passada já decidiu e carimbou: herda a decisão em vez de
# repetir o bloco, que veria o próprio carimbo recém-gravado e sairia sem fazer a tentativa.
REPETICAO="${_LEGISDATA_DEPLOY_REPETICAO:-0}"
[[ "$REPETICAO" =~ ^[01]$ ]] || REPETICAO=0 # vem do ambiente: nada além de 0 ou 1 entra em contexto aritmético
if [[ -z "${_LEGISDATA_DEPLOY_REEXEC:-}" && "$ATUAL" == "$ALVO" ]]; then
  # mesmo commit: só há o que fazer se um pedido de atualização ficou parado ou se a carga pendente já pode repetir. O
  # dry-run não altera nada: não dispara o serviço nem mexe nas pendências.
  if [[ $DRY_RUN -eq 0 ]] && pendente_tem refrescar && disparar_financas; then
    pendente_limpa refrescar
    log "atualização das finanças pendente disparada"
  fi
  carga_pode_repetir || exit 0
  REPETICAO=1
  # a tentativa é carimbada ANTES da carga: qualquer falha dela (tolerada ou não) espera o intervalo para repetir
  if [[ $DRY_RUN -eq 0 ]]; then date +%s >"$CARGA_TENTADA"; fi
fi
# <<< mesmo_commit

# As imagens são publicadas só depois do CI passar; sem elas não há o que implantar ainda.
for img in legisdata-backend legisdata-frontend; do
  if ! docker pull -q "$REGISTRO/$img:$TAG" >/dev/null 2>&1; then
    log "imagem $img:$TAG ainda não publicada (CI em andamento ou falhou); tento de novo na próxima"
    exit 0
  fi
done
log "implantando $TAG (anterior: ${ATUAL:0:7})"
[[ $DRY_RUN -eq 1 ]] && { log "dry-run: imagens existem, nada alterado"; exit 0; }

# O timer executa a cópia instalada em $ESTADO_DIR, que pode ser mais antiga que o script da main. Antes de mexer em
# qualquer coisa, passa a usar o script do commit que será implantado (reexecuta uma única vez).
if [[ -z "${_LEGISDATA_DEPLOY_REEXEC:-}" ]] && git cat-file -e "$ALVO:scripts/deploy/deploy.sh" 2>/dev/null; then
  git show "$ALVO:scripts/deploy/deploy.sh" >"$ESTADO_DIR/deploy.sh.novo"
  if ! bash -n "$ESTADO_DIR/deploy.sh.novo"; then
    log "script de deploy do commit $TAG com erro de sintaxe; mantenho o atual"
  elif ! cmp -s "$ESTADO_DIR/deploy.sh.novo" "$ESTADO_DIR/deploy.sh"; then
    chmod 755 "$ESTADO_DIR/deploy.sh.novo" && mv "$ESTADO_DIR/deploy.sh.novo" "$ESTADO_DIR/deploy.sh"
    log "script de deploy atualizado para o da main; reexecutando"
    _LEGISDATA_DEPLOY_REEXEC=1 _LEGISDATA_DEPLOY_ALVO="$ALVO" _LEGISDATA_DEPLOY_REPETICAO="$REPETICAO" exec "$ESTADO_DIR/deploy.sh" "$@"
  fi
  rm -f "$ESTADO_DIR/deploy.sh.novo"
fi

# O .env tem a senha do banco: só o dono lê.
chmod 600 "$RAIZ/.env" 2>/dev/null || true
set -a
# shellcheck disable=SC1091
. "$RAIZ/.env"
set +a
PG_USER="${POSTGRES_USER:-politica_user}"
PG_DB="${POSTGRES_DB:-politica_db}"

# 1. backup antes de qualquer alteração (formato custom, restaurável com pg_restore)
# Uma tentativa anterior deste mesmo commit que falhou já deixou o backup de antes das migrações: reaproveita-o, para
# um deploy quebrado repetido pelo timer não encher a rotação com dumps de um banco já migrado e apagar o bom.
DUMP="$(ls -1t "$BACKUP_DIR"/legisdata_"${TAG}"_*.dump 2>/dev/null | head -n 1 || true)"  # *.dump.parcial não casa
if [[ -n "$DUMP" && -s "$DUMP" ]]; then
  log "backup deste commit já existe, reaproveitado: $DUMP"
else
  DUMP="$BACKUP_DIR/legisdata_${TAG}_$(date +%Y%m%d_%H%M%S).dump"
  # O dump só ganha o nome definitivo depois de terminar bem; um pg_dump interrompido nunca vira "backup bom".
  rm -f "$BACKUP_DIR"/*.dump.parcial
  # umask só neste subshell: o resto do script (git merge, arquivos do checkout) mantém as permissões normais
  if ! (umask 077 && docker exec politica_postgres pg_dump -U "$PG_USER" -d "$PG_DB" -Fc >"$DUMP.parcial") ||
    [[ ! -s "$DUMP.parcial" ]]; then
    log "backup falhou ou veio vazio, abortando"
    rm -f "$DUMP.parcial"
    exit 1
  fi
  mv "$DUMP.parcial" "$DUMP"
  log "backup: $DUMP ($(du -h "$DUMP" | cut -f1))"
fi
# shellcheck disable=SC2012
ls -1t "$BACKUP_DIR"/legisdata_*.dump | tail -n +"$((GUARDAR_BACKUPS + 1))" | xargs -r rm -f

# 2. código (compose, dados do ETL, scripts). O cron diário regrava arquivos versionados de etl/data/processed no
# checkout; essas mudanças locais impediriam o fast-forward. Os arquivos voltam ao commit e o próximo cron os atualiza.
if ! git diff --quiet -- etl/data/processed || [[ -n "$(git ls-files --others --exclude-standard -- etl/data/processed)" ]]; then
  log "descartando saídas do cron em etl/data/processed antes de atualizar o código:"
  { git diff --name-only -- etl/data/processed; git ls-files --others --exclude-standard -- etl/data/processed; } |
    while read -r arquivo; do log "  $arquivo"; done
  git checkout -q -- etl/data/processed
  git clean -fdq -- etl/data/processed
fi
COMMIT_ANTERIOR="$(git rev-parse HEAD)"  # o compose deste commit é o que o rollback precisa (o novo pode ter outros volumes)
git merge --ff-only -q "$ALVO"

# >>> url_encode
url_encode() { # codifica um texto para a parte de usuário/senha de uma URL (RFC 3986: só A-Za-z0-9._~- ficam como estão)
  local LC_ALL=C texto="$1" i c saida=""
  for ((i = 0; i < ${#texto}; i++)); do
    c="${texto:i:1}"
    case "$c" in
      [A-Za-z0-9._~-]) saida+="$c" ;;
      *) saida+="$(printf '%%%02X' "'$c")" ;;
    esac
  done
  printf '%s' "$saida"
}
# <<< url_encode

# A URL do banco (com a senha) vai por arquivo de ambiente 600, nunca na linha de comando (visível em `ps`). A senha entra
# codificada (um `@`, `/`, `#` ou `%` nela quebraria a URL); quebra de linha não cabe em arquivo de ambiente.
# >>> env_banco
[[ -n "${POSTGRES_PASSWORD:-}" ]] || { log "POSTGRES_PASSWORD ausente no .env"; exit 1; }
[[ "$POSTGRES_PASSWORD" != *$'\n'* && "$POSTGRES_PASSWORD" != *$'\r'* ]] || { log "POSTGRES_PASSWORD com quebra de linha não cabe no arquivo de ambiente"; exit 1; }
URL_BANCO="postgresql+psycopg2://${PG_USER}:$(url_encode "$POSTGRES_PASSWORD")@postgres:5432/${PG_DB}"
# O arquivo vai para o diretório de runtime do usuário (tmpfs, 700) quando existe; senão para o estado do deploy.
DIR_TEMP="${XDG_RUNTIME_DIR:-}"
[[ -n "$DIR_TEMP" && -d "$DIR_TEMP" && -w "$DIR_TEMP" ]] || DIR_TEMP="${ESTADO_DIR:-${TMPDIR:-/tmp}}"
find "$DIR_TEMP" -maxdepth 1 -name 'legisdata-env.*' -mmin +60 -delete 2>/dev/null || true # restos de uma execução morta
ENV_BANCO="$(mktemp -p "$DIR_TEMP" legisdata-env.XXXXXX)"
trap 'rm -f "$ENV_BANCO"' EXIT
chmod 600 "$ENV_BANCO"
printf 'ALEMBIC_DATABASE_URL=%s\nDATABASE_URL=%s\nPOSTGRES_PASSWORD=%s\n' "$URL_BANCO" "$URL_BANCO" "$POSTGRES_PASSWORD" >"$ENV_BANCO"
# <<< env_banco
# Contenção de todo contêiner que o deploy sobe com o banco: sem capacidades, sem privilégios novos.
CONTENCAO=(--cap-drop ALL --security-opt no-new-privileges --pids-limit 512)
# O .git/config pode guardar credencial de remote: some do contêiner (num worktree o .git é arquivo e não há o que esconder).
ESCONDER_GIT=()
[[ -f "$RAIZ/.git/config" ]] && ESCONDER_GIT=(-v /dev/null:/repo/.git/config:ro)
um_comando() { # roda um comando Python no contêiner da imagem nova, na rede do compose
  # LEGISDATA_ACEITAR_ENCOLHIMENTO=1 libera, só nesta execução, uma carga de finanças que reduz uma tabela a menos da metade.
  # O contêiner só precisa do banco: sem capacidades, sem privilégios novos e com o .env (outros segredos) escondido.
  docker run --rm --network "$REDE" --env-file "$ENV_BANCO" -e ENVIRONMENT=production -e DB_SSLMODE=disable \
    "${CONTENCAO[@]}" \
    -e LEGISDATA_ACEITAR_ENCOLHIMENTO="${LEGISDATA_ACEITAR_ENCOLHIMENTO:-}" \
    -e LEGISDATA_FIN_TEM_ALGUM_DADO="${LEGISDATA_FIN_TEM_ALGUM_DADO:-}" -e LEGISDATA_FIN_MODO="${LEGISDATA_FIN_MODO:-nenhuma}" \
    -e PYTHONPATH=/repo/backend:/repo -v "$RAIZ:/repo:ro" -v /dev/null:/repo/.env:ro ${ESCONDER_GIT[@]+"${ESCONDER_GIT[@]}"} \
    -w /app \
    "$REGISTRO/legisdata-backend:$TAG" "$@" 9>&-
}

# >>> decidir_financas
# Decide como o deploy trata as finanças. A atualização diária (legisdata-financas.timer) deixa CEAP e emendas do `fin` mais
# novas que os arquivos do git; recarregá-las do git apagaria as emendas novas (que voltariam com outro `uid`) e
# devolveria a CEAP ao passado. Então o git só semeia o que o timer ainda não assumiu (ver "fontes_do_timer" abaixo).
#   uso:   decidir_financas <commit anterior> <commit alvo> <t se o fin tem CEAP> <t se o fin tem emendas> [pendências]
#                           [t se o timer já carregou a CEAP] [t se o timer já carregou as emendas]
#   Os dois últimos argumentos ausentes valem "t": quem esquecê-los cai no lado seguro (nunca semeia nem reescreve uma fonte
#   do timer). O chamador real sempre os passa, começando em "f" e subindo para "t" conforme o banco responde.
#   A tabela de semeadura (qual fonte o git semeia) é a de `semeadura_das_financas.modo_de_semeadura`; um teste compara as 16
#   combinações.
#   saída: "<modo> <refrescar>"
#     Uma fonte só fica fora da semeadura quando o fin tem dado dela E o timer a assumiu:
#     modo "completa":    nenhuma das duas fontes está nesse caso: semeia tudo dos arquivos do git;
#     modo "sem_emendas": só as emendas estão: semeia a CEAP e as estáticas, sem tocar nas emendas;
#     modo "sem_ceap":    só a CEAP está: semeia as emendas e as estáticas, sem tocar na CEAP;
#     modo "estaticas":   recarrega só remuneração, patrimônio, doações e certidões (um arquivo ou o código mudou);
#     modo "nenhuma":     nada mudou, mantém o fin;
#     refrescar 1:        o commit mudou a extração/carga de CEAP e emendas (ou o fin acabou de ser semeado do git): vale
#                         rodar a atualização diária já, para o fin não esperar até a madrugada.
#   Pendências (conteúdo de financas_pendente, uma por linha): "carga" força ao menos as estáticas, "refrescar" pede a
#   atualização. "O timer já carregou" é uma linha em etl.execucao que a carga fresca grava NA MESMA TRANSAÇÃO que os dados
#   (volta com um backup restaurado e não fica para trás se a carga falhou; não é o cache de extração). Sem ela o fin só
#   tem o retrato do git, que é o dado mais novo que existe; semeia a fonte de novo para as regras de saneamento do commit
#   chegarem ao fin.
decidir_financas() {
  local atual="$1" alvo="$2" tem_ceap="$3" tem_emendas="$4" pendencias="${5:-}" ceap_do_timer="${6:-t}" emendas_do_timer="${7:-t}"
  local modo="nenhuma" refrescar=0 semear_ceap=1 semear_emendas=1
  local estaticas=(
    etl/data/processed/remuneracao_parlamentares.json etl/data/processed/declaracoes_patrimonio.json
    etl/data/processed/tse_doacoes_campanha.json etl/data/processed/certidoes_tse.json
    etl/pipelines/financas_loader.py etl/pipelines/loader_helpers.py etl/pipelines/semeadura_das_financas.py
    etl/pipelines/pessoa_resolver.py etl/pipelines/carga_economica.py etl/config.py etl/utils backend/alembic/versions
  )
  local do_timer=(
    etl/pipelines/sync_ceap_emendas.py etl/pipelines/financas_atualizacao.py etl/pipelines/financas_loader.py
    etl/pipelines/loader_helpers.py etl/pipelines/semeadura_das_financas.py etl/pipelines/pessoa_resolver.py
    etl/extractors/emendas_extractor.py
    etl/config.py etl/utils backend/alembic/versions scripts/deploy/atualizar_financas.sh
    scripts/systemd/legisdata-financas.service scripts/systemd/legisdata-financas.timer
  )
  [[ "$tem_ceap" == t && "$ceap_do_timer" == t ]] && semear_ceap=0
  [[ "$tem_emendas" == t && "$emendas_do_timer" == t ]] && semear_emendas=0
  if ((semear_ceap && semear_emendas)); then
    echo "completa 1"
    return 0
  fi
  if ((semear_ceap)); then
    echo "sem_emendas 1"
    return 0
  fi
  if ((semear_emendas)); then
    echo "sem_ceap 1"
    return 0
  fi
  if [[ -z "$atual" ]] || ! git cat-file -e "$atual^{commit}" 2>/dev/null; then
    echo "estaticas 1" # commit anterior desconhecido: recarrega o que pode e pede a atualização
    return 0
  fi
  git diff --quiet "$atual" "$alvo" -- "${estaticas[@]}" || modo="estaticas"
  git diff --quiet "$atual" "$alvo" -- "${do_timer[@]}" || refrescar=1
  grep -qx carga <<<"$pendencias" && [[ "$modo" == "nenhuma" ]] && modo="estaticas"
  grep -qx refrescar <<<"$pendencias" && refrescar=1
  echo "$modo $refrescar"
}
# <<< decidir_financas

# 3. migrações e 4. carga das séries econômicas e da curadoria (idempotentes)
log "migrações"
docker run --rm --network "$REDE" --env-file "$ENV_BANCO" -e ENVIRONMENT=production -e DB_SSLMODE=disable \
  "${CONTENCAO[@]}" "$REGISTRO/legisdata-backend:$TAG" alembic upgrade head 9>&-
# Só depois que o schema `eco` existe (a migração 0025 em diante) e o código da carga está no checkout.
TEM_ECO="$(docker exec politica_postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "select to_regclass('eco.observacao') is not null")"
if [[ "$TEM_ECO" == "t" && -f "$RAIZ/etl/pipelines/carga_economica.py" ]]; then
  log "carga de séries, mandatos, composição do Congresso e PNAD"
  # Finanças só é tolerada se `fin` já tem dados: aí a API nova segue servindo o que já estava lá. No primeiro deploy
  # (fin recém-criado e vazio) uma falha da carga aborta antes do `compose up` e o contêiner antigo continua no ar.
  # Perguntas ao banco: a CEAP e as emendas têm dado (decidem o que semear), e algum dado de finanças existe (decide a tolerância).
  TEM_CEAP="$(docker exec politica_postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "select exists(select 1 from fin.despesa_cota) and exists(select 1 from fin.despesa_cota_fornecedor) and exists(select 1 from fin.despesa_cota_resumo)")"
  TEM_EMENDAS="$(docker exec politica_postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "select exists(select 1 from fin.emenda)")"
  LEGISDATA_FIN_TEM_ALGUM_DADO="$(docker exec politica_postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "select exists(select 1 from fin.despesa_cota) or exists(select 1 from fin.despesa_cota_fornecedor) or exists(select 1 from fin.despesa_cota_resumo) or exists(select 1 from fin.emenda)")"
  export LEGISDATA_FIN_TEM_ALGUM_DADO
  PENDENCIAS="$(cat "$PENDENTE" 2>/dev/null || true)"
  # >>> fontes_do_timer
  # a fonte é do timer se a ÚLTIMA carga dela no fin veio de uma extração fresca (linha em etl.execucao, gravada na
  # transação da carga; uma semeadura do git grava "fresca=false" e revoga); sem a linha o fin só tem o retrato do git
  FONTES_DO_TIMER="$(docker exec politica_postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "select coalesce(string_agg(carga, ' '), '') from (select distinct on (c) c as carga, fresca from (select coalesce(parametros->>'carga', parametros->>'fonte') as c, parametros->>'fresca' as fresca, id from etl.execucao where estagio = 'CARREGAR' and status = 'OK') x where c is not null order by c, id desc) t where fresca = 'true'")"
  CEAP_DO_TIMER=f
  EMENDAS_DO_TIMER=f
  [[ " $FONTES_DO_TIMER " == *" ceap "* ]] && CEAP_DO_TIMER=t
  [[ " $FONTES_DO_TIMER " == *" emendas "* ]] && EMENDAS_DO_TIMER=t
  # <<< fontes_do_timer
  read -r LEGISDATA_FIN_MODO LEGISDATA_FIN_REFRESCAR < <(decidir_financas "$ATUAL" "$ALVO" "$TEM_CEAP" "$TEM_EMENDAS" "$PENDENCIAS" "$CEAP_DO_TIMER" "$EMENDAS_DO_TIMER")
  # >>> pos_decisao
  if [[ $REPETICAO -eq 1 ]]; then LEGISDATA_FIN_REFRESCAR=0; fi # repetir a carga não repete o pedido de atualização
  # <<< pos_decisao
  export LEGISDATA_FIN_MODO LEGISDATA_FIN_REFRESCAR
  case "$LEGISDATA_FIN_MODO" in
    completa) log "finanças: fin sem dados ou ainda sem nenhuma fonte do timer; semeando tudo dos arquivos do git" ;;
    sem_emendas) log "finanças: as emendas já são do timer; semeio a CEAP e recarrego as estáticas" ;;
    sem_ceap) log "finanças: a CEAP já é do timer; semeio as emendas e recarrego as estáticas" ;;
    estaticas) log "finanças: recarrego remuneração, patrimônio, doações e certidões; CEAP e emendas ficam como a atualização diária deixou" ;;
    *) log "finanças: este commit não mudou os arquivos nem o código da carga; mantenho o fin atual" ;;
  esac
  SAIDA_CARGA="$(um_comando python -c "
import os
from app.core.database import engine
from etl.pipelines.carga_economica import TOLERADAS_NO_DEPLOY, carregar_tudo, falhas_toleradas, plano_do_modo
from etl.pipelines.financas_loader import registrar_carga_do_git
toleradas = TOLERADAS_NO_DEPLOY if os.environ.get('LEGISDATA_FIN_TEM_ALGUM_DADO') == 't' else ()
plano = plano_do_modo(os.environ.get('LEGISDATA_FIN_MODO', 'nenhuma'), ao_confirmar=registrar_carga_do_git)
resultados = carregar_tudo(engine, toleradas=toleradas, **plano)
for chave, resultado in resultados.items():
    print(chave, resultado)
for chave in falhas_toleradas(resultados):
    print('FALHA_TOLERADA', chave)
")"
  printf '%s\n' "$SAIDA_CARGA"
  # >>> apos_carga
  # Uma carga de finanças tolerada que falhou não derruba o deploy, mas fica pendente: a próxima execução tenta de novo.
  if grep -q '^FALHA_TOLERADA ' <<<"$SAIDA_CARGA"; then
    pendente_marca carga
    date +%s >"$CARGA_TENTADA"
    log "AVISO: a carga de finanças falhou (tolerada); tento de novo em até $((INTERVALO_DA_CARGA / 60)) minutos"
  else
    pendente_limpa carga
    rm -f "$CARGA_TENTADA"
  fi
  # <<< apos_carga
fi

# 5. imagens novas
ANTERIOR="$(cat "$ESTADO_DIR/ultima_tag" 2>/dev/null || docker inspect --format '{{.Config.Image}}' politica_api | sed 's/.*://')"
export IMAGE_TAG="$TAG"
docker compose up -d --no-build backend frontend

# 6. saúde; sem saúde em 3 minutos, volta para a tag anterior
for _ in $(seq 1 36); do
  estado="$(docker inspect --format '{{.State.Health.Status}}' politica_api 2>/dev/null || echo starting)"
  [[ "$estado" == "healthy" ]] && break
  sleep 5
done
if [[ "$estado" != "healthy" ]]; then
  log "API não ficou saudável ($estado); voltando para $ANTERIOR (backup: $DUMP)"
  # com o compose do commit anterior (o novo pode ter tirado volumes de que a imagem antiga precisa); se não der para
  # lê-lo, com o compose atual
  if git show "$COMMIT_ANTERIOR:docker-compose.yml" >"$ENV_BANCO.compose" 2>/dev/null; then
    IMAGE_TAG="$ANTERIOR" docker compose --project-directory "$RAIZ" -f "$ENV_BANCO.compose" up -d --no-build backend frontend
    rm -f "$ENV_BANCO.compose"
  else
    IMAGE_TAG="$ANTERIOR" docker compose up -d --no-build backend frontend
  fi
  exit 1
fi

# O timer executa a cópia em $ESTADO_DIR/deploy.sh (sobrevive a um `git merge` que mexa no script); atualiza-a aqui.
if [[ -f "$RAIZ/scripts/deploy/deploy.sh" ]] && ! cmp -s "$RAIZ/scripts/deploy/deploy.sh" "$ESTADO_DIR/deploy.sh"; then
  install -m 755 "$RAIZ/scripts/deploy/deploy.sh" "$ESTADO_DIR/deploy.sh.novo" && mv "$ESTADO_DIR/deploy.sh.novo" "$ESTADO_DIR/deploy.sh"
fi
# O timer das finanças executa a cópia em $ESTADO_DIR/atualizar_financas.sh; a mantém igual à do commit implantado.
if [[ -f "$RAIZ/scripts/deploy/atualizar_financas.sh" ]] && bash -n "$RAIZ/scripts/deploy/atualizar_financas.sh" &&
  ! cmp -s "$RAIZ/scripts/deploy/atualizar_financas.sh" "$ESTADO_DIR/atualizar_financas.sh"; then
  install -m 755 "$RAIZ/scripts/deploy/atualizar_financas.sh" "$ESTADO_DIR/atualizar_financas.sh.novo" &&
    mv "$ESTADO_DIR/atualizar_financas.sh.novo" "$ESTADO_DIR/atualizar_financas.sh"
fi
echo "$TAG" >"$ESTADO_DIR/ultima_tag"
echo "$ALVO" >"$ESTADO_DIR/ultimo_sha"
# Atualização diária das finanças: se o commit mudou a extração ou a carga (ou o fin acabou de ser semeado do git), roda já.
# A unit só existe depois do `instalar.sh`; sem ela o pedido fica registrado (financas_pendente) e o instalador o cumpre.
# >>> disparo_financas
if [[ "${LEGISDATA_FIN_REFRESCAR:-0}" == "1" ]] || pendente_tem refrescar; then
  if disparar_financas; then
    pendente_limpa refrescar
    log "atualização das finanças disparada (o commit mudou a extração ou a carga de CEAP e emendas)"
  else
    pendente_marca refrescar
    log "AVISO: não consegui disparar legisdata-financas.service (a unit não está instalada ou o systemd recusou); o pedido ficou registrado e o instalar.sh o cumpre"
  fi
elif ! systemctl --user cat legisdata-financas.service >/dev/null 2>&1; then
  log "AVISO: legisdata-financas.timer não está instalado; CEAP e emendas só atualizam com ele (rode o instalar.sh, docs/DEPLOY_AUTOMATICO.md)"
fi
# <<< disparo_financas
docker image prune -f >/dev/null 2>&1 || true
log "deploy de $TAG concluído"
