"""
Atualização diária das finanças: extrai a CEAP (Câmara e Senado) e as emendas e recarrega as duas no schema `fin`.

A CEAP de cada ano já fechado (depois de 1º de abril do ano seguinte) vem do cache em `etl/data/raw/ceap_por_ano` e não é
baixada de novo: só o ano corrente (e o anterior até março) vai à rede. As emendas são um único arquivo do Portal da
Transparência, baixado por inteiro.

Cada fonte é independente. A que foi gravada é recarregada no `fin`; a que falhou deixa o arquivo e o `fin` como estavam
(nunca se recarrega a partir de um arquivo que a extração não renovou: depois de um deploy ele é o retrato antigo do git).
Se alguma fonte falhou, a execução termina com erro depois de recarregar a outra. Os dados de remuneração, patrimônio,
doações e certidões não mudam por dia e ficam fora desta atualização.

Uma segunda execução ao mesmo tempo (o timer e o `make daily`, por exemplo) é recusada por um lock no próprio pipeline. Onde
existe o lock do deploy (o diretório de estado dele, no host que faz o deploy), a execução também o respeita: o deploy
descarta as saídas locais de `etl/data` e semeia o `fin` do git, e as duas coisas não podem se misturar com uma extração.
O timer já segura esse lock fora do contêiner, onde o arquivo não existe e esta checagem não faz nada.

Uso: python -m etl.pipelines.financas_atualizacao
"""

import fcntl
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Set

from etl.config import DATA_DIR, RAW_DATA_DIR
from etl.pipelines import financas_loader, sync_ceap_emendas
from etl.pipelines.loader_helpers import descricao_do_erro
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

logger = logging.getLogger("FinancasAtualizacao")

CACHE_DIR = RAW_DATA_DIR / sync_ceap_emendas.PASTA_DO_CACHE
LOCK = DATA_DIR / ".financas.lock"


def lock_do_deploy() -> Path:
    """Onde o deploy guarda o lock dele (mesma convenção do `deploy.sh`: DEPLOY_STATE_DIR ou ~/.legisdata-deploy)."""
    base = os.environ.get("DEPLOY_STATE_DIR")
    return (Path(base) if base else Path.home() / ".legisdata-deploy") / "deploy.lock"


def _travar(caminho: Path, criar: bool) -> Optional[Any]:
    """Abre o arquivo e pega o lock sem esperar; None se está ocupado. Sem truncar e sem seguir link simbólico."""
    descritor = os.open(caminho, os.O_RDWR | (os.O_CREAT if criar else 0) | os.O_NOFOLLOW, 0o600)
    arquivo = os.fdopen(descritor, "r+")
    try:
        fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        arquivo.close()
        return None
    return arquivo


def atualizar(
    engine: Engine,
    hoje: Optional[date] = None,
    cache_dir: Optional[Path] = None,
    lock: Optional[Path] = None,
    lock_do_deploy_em: Optional[Path] = None,
) -> Dict[str, Any]:
    caminho_do_lock = Path(lock or LOCK)
    caminho_do_lock.parent.mkdir(parents=True, exist_ok=True)
    proprio = _travar(caminho_do_lock, criar=True)
    if proprio is None:
        logger.warning("Outra atualização das finanças está em andamento; esta execução foi pulada.")
        return {"pulada": "outra atualização das finanças em andamento"}
    deploy = None
    try:
        caminho_do_deploy = lock_do_deploy_em or lock_do_deploy()
        if caminho_do_deploy.exists():  # só onde há deploy; o lock nunca é criado por aqui
            deploy = _travar(caminho_do_deploy, criar=False)
            if deploy is None:
                logger.warning("Deploy em andamento; esta atualização das finanças foi pulada.")
                return {"pulada": "deploy em andamento"}
        return _atualizar(engine, hoje or sync_ceap_emendas.hoje_no_brasil(), cache_dir or CACHE_DIR)
    finally:
        if deploy is not None:
            deploy.close()
        proprio.close()


def anos_ja_carregados(engine: Engine) -> Optional[Dict[str, Set[int]]]:
    """Os anos da CEAP que o `fin` já tem; sem resposta do banco, None (vale só o que o arquivo processado traz)."""
    try:
        return financas_loader.anos_publicados_da_ceap(engine)
    except DBAPIError as exc:
        logger.warning("Não consegui levantar os anos da CEAP já carregados no fin: %s", descricao_do_erro(exc))
        return None


def _atualizar(engine: Engine, hoje: date, cache_dir: Path) -> Dict[str, Any]:
    resumo = sync_ceap_emendas.run(
        ano_inicio=sync_ceap_emendas.ANO_INICIAL_ARQUIVO,
        ano_fim=hoje.year,
        cache_dir=cache_dir,
        hoje=hoje,
        anos_publicados=anos_ja_carregados(engine),
    )
    # lista positiva (ausência de resposta não é gravação), a mesma que a CLI usa
    gravadas = sync_ceap_emendas.fontes_gravadas(resumo)
    nao_gravadas = sync_ceap_emendas.fontes_nao_gravadas(resumo)
    resultado: Dict[str, Any] = {"extracao": resumo, "carregadas": gravadas}
    erros = []
    if gravadas:
        try:
            # a carga de cada fonte registra, na própria transação, que o `fin` passou a ter dado fresco dela
            resultado["carga"] = financas_loader.carregar(
                engine, chaves=gravadas, ao_confirmar=financas_loader.registrar_carga_fresca
            )
        except RuntimeError as exc:
            erros.append(str(exc))
    if nao_gravadas:
        erros.insert(0, f"fontes não gravadas, arquivo e fin preservados: {nao_gravadas}")
    logger.info("Finanças atualizadas: %s", resultado)
    if erros:
        raise RuntimeError("; ".join(erros))
    return resultado


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ensure_backend_on_path()
    from app.core.database import engine

    try:
        atualizar(engine)
    except Exception as exc:  # noqa: BLE001 - o serviço do systemd registra o código de saída
        logger.error("Atualização das finanças falhou: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
