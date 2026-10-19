#!/usr/bin/env bash
# Atualização diária das finanças no servidor (timer do systemd do usuário): baixa a CEAP e as emendas oficiais e
# recarrega essas duas no schema `fin`. Roda no contêiner da imagem da API que está no ar, com o checkout montado só para
# leitura e apenas `etl/data` gravável (arquivos extraídos e cache da CEAP por ano). Só o ano corrente (e o anterior até
# março) vai à rede; os anos fechados vêm do cache. Falha de extração preserva os arquivos e o `fin` como estavam.
set -Eeuo pipefail

[[ -z "${LEGISDATA_DIR:-}" && -f "$HOME/.legisdata-deploy/ambiente" ]] && . "$HOME/.legisdata-deploy/ambiente"
RAIZ="${LEGISDATA_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ESTADO_DIR="${DEPLOY_STATE_DIR:-$HOME/.legisdata-deploy}"
REDE="${DEPLOY_NETWORK:-legisdata_default}"

log() { printf '%s [financas] %s\n' "$(date '+%F %T')" "$*"; }

# O deploy também mexe em etl/data (descarta as saídas locais antes do merge): nunca os dois ao mesmo tempo. Usa o mesmo
# lock do deploy e espera até 30 minutos; o deploy, ao achar o lock ocupado, tenta de novo na execução seguinte do timer.
mkdir -p "$ESTADO_DIR"
chmod 700 "$ESTADO_DIR"
exec 9>"$ESTADO_DIR/deploy.lock"
flock -w 1800 9 || { log "deploy em andamento há mais de 30 minutos; tento amanhã"; exit 1; }

set -a
# shellcheck disable=SC1091
. "$RAIZ/.env"
set +a
PG_USER="${POSTGRES_USER:-politica_user}"
PG_DB="${POSTGRES_DB:-politica_db}"

# O código (etl) vem do checkout e as dependências (app, pacotes) da imagem no ar: precisam ser do mesmo commit. Depois de
# um rollback do deploy o checkout fica no commit novo e a imagem no antigo; rodar assim pode falhar de jeitos confusos.
IMAGEM="$(docker inspect --format '{{.Config.Image}}' politica_api)"
COMMIT_DO_CHECKOUT="$(git -C "$RAIZ" rev-parse HEAD)"
COMMIT_DO_CHECKOUT="${COMMIT_DO_CHECKOUT:0:7}" # a mesma conta do deploy (TAG="${ALVO:0:7}"), sem depender do tamanho do `--short`
if [[ ! "${IMAGEM##*:}" =~ ^[0-9a-f]{7}$ ]]; then
  log "a imagem no ar (${IMAGEM}) não tem como tag o commit de 7 caracteres que o deploy publica (ex.: latest); não sei se bate com o checkout ($COMMIT_DO_CHECKOUT)"
  exit 1
fi
if [[ "${IMAGEM##*:}" != "$COMMIT_DO_CHECKOUT" ]]; then
  log "a imagem no ar (${IMAGEM##*:}) não é a do checkout ($COMMIT_DO_CHECKOUT): deploy em andamento ou revertido; tento amanhã"
  exit 1
fi

# A senha do banco vai por arquivo de ambiente 600, nunca na linha de comando (visível em `ps`). O banco vai em variáveis
# separadas e quem monta a URL é o próprio `Settings` do backend, que codifica a senha (um `@`, `/` ou `#` nela quebraria
# uma URL montada aqui). Quebra de linha não cabe em arquivo de ambiente.
# >>> env_banco_financas
[[ -n "${POSTGRES_PASSWORD:-}" ]] || { log "POSTGRES_PASSWORD ausente no .env"; exit 1; }
[[ "$POSTGRES_PASSWORD" != *$'\n'* && "$POSTGRES_PASSWORD" != *$'\r'* ]] || { log "POSTGRES_PASSWORD com quebra de linha não cabe no arquivo de ambiente"; exit 1; }
DIR_TEMP="${XDG_RUNTIME_DIR:-}" # tmpfs do usuário quando existe; a senha não fica em disco comum
[[ -n "$DIR_TEMP" && -d "$DIR_TEMP" && -w "$DIR_TEMP" ]] || DIR_TEMP="${ESTADO_DIR:-${TMPDIR:-/tmp}}"
find "$DIR_TEMP" -maxdepth 1 -name 'legisdata-env.*' -mmin +60 -delete 2>/dev/null || true # restos de uma execução morta
ENV_BANCO="$(mktemp -p "$DIR_TEMP" legisdata-env.XXXXXX)"
trap 'rm -f "$ENV_BANCO"' EXIT
chmod 600 "$ENV_BANCO"
printf 'POSTGRES_USER=%s\nPOSTGRES_PASSWORD=%s\nPOSTGRES_SERVER=postgres\nPOSTGRES_PORT=5432\nPOSTGRES_DB=%s\n' "$PG_USER" "$POSTGRES_PASSWORD" "$PG_DB" >"$ENV_BANCO"
# <<< env_banco_financas

# O .git/config pode guardar credencial de remote: some do contêiner (num worktree o .git é arquivo e não há o que esconder).
ESCONDER_GIT=()
[[ -f "$RAIZ/.git/config" ]] && ESCONDER_GIT=(-v /dev/null:/repo/.git/config:ro)
log "atualizando CEAP e emendas ($IMAGEM)"
# --user: os arquivos gravados em etl/data ficam do dono do checkout. O lock (descritor 9) não passa para o contêiner. O
# contêiner só precisa do banco: sem capacidades, sem privilégios novos e com o .env e o .git/config (outros segredos)
# escondidos. LEGISDATA_ACEITAR_ENCOLHIMENTO=1 na linha de comando libera uma redução legítima só nesta execução.
docker run --rm --network "$REDE" --env-file "$ENV_BANCO" --user "$(id -u):$(id -g)" \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 \
  -e ENVIRONMENT=production -e DB_SSLMODE=disable -e HOME=/tmp \
  -e LEGISDATA_ACEITAR_ENCOLHIMENTO="${LEGISDATA_ACEITAR_ENCOLHIMENTO:-}" \
  -e PYTHONPATH=/repo/backend:/repo --memory 2g --cpus 2 \
  -v "$RAIZ:/repo:ro" -v "$RAIZ/etl/data:/repo/etl/data" -v /dev/null:/repo/.env:ro ${ESCONDER_GIT[@]+"${ESCONDER_GIT[@]}"} -w /app \
  "$IMAGEM" python -m etl.pipelines.financas_atualizacao 9>&-
log "concluído"
