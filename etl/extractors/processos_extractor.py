"""
Extrator de processos judiciais: enriquece com o DataJud (CNJ) os números de processo da curadoria.

O DataJud só responde por número de processo e não expõe as partes; por isso ele nunca descobre os processos de uma
pessoa. O vínculo vem de `processos_curados.json`: cada entrada traz a pessoa (os mesmos identificadores das demais
fontes), o número CNJ e o link da fonte oficial que liga o processo à pessoa. Daqui sai `processos_judiciais.json`,
que a carga `processos` do `fin` lê.

A curadoria é a fonte de verdade: o arquivo gerado reflete exatamente o que ela contém e o DataJud confirma. Por isso,
- uma curadoria válida e vazia grava `[]` (é assim que se retira um vínculo errado do dossiê);
- fica de fora, e é contado, o processo com número inválido, link que não é de fonte oficial (`https` de domínio
  público e sem CPF), sem identificador oficial da pessoa (Câmara ou Senado), de um tribunal que o DataJud não cobre
  (STF, por exemplo), que o DataJud não tem, de documento malformado, sem classe oficial, sob sigilo ou cujo documento
  devolvido não é o número pedido;
- mas se o DataJud não deu resposta conclusiva (429, timeout, HTTP de erro) para algum processo, NADA é gravado e o
  erro sobe: uma falha de rede não pode virar a retirada de processos reais. O mesmo vale para um processo que já
  estava no arquivo gerado e agora "some" do DataJud: retirar um vínculo já publicado só vale por remoção explícita na
  curadoria, nunca por um sinal fraco como a resposta vazia de um tribunal que migrou de sistema.

Nada é inferido sobre o desfecho: o dossiê mostra só o último movimento que o tribunal registrou.
"""

import logging
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from etl.config import PROCESSED_DATA_DIR, PROCESSOS_ARQUIVO, PROCESSOS_CURADORIA_ARQUIVO
from etl.pipelines.loader_helpers import (
    assuntos_sem_cpf,
    cnj_digitos,
    cnj_valido,
    inteiro,
    link_oficial,
    sob_sigilo,
    texto_oficial_sem_cpf,
)
from etl.utils.datafiles import load_json
from etl.utils.datajud_client import (
    DataJudClient,
    ErroDoDataJud,
    deduzir_aliases_datajud,
    parse_cnj_parts,
)
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("ProcessosExtractor")

# Campos de identificação da pessoa que a curadoria carrega para o resolvedor de pessoas.
CAMPOS_DA_PESSOA = ("nome_civil", "nome_eleitoral", "camara_id", "senado_id")
# Texto livre do DataJud que vai para o arquivo versionado: sem CPF já aqui (D3), não só na carga.
CAMPOS_DE_TEXTO = ("tribunal", "grau", "classe_tpu_nome", "orgao_julgador", "ultimo_movimento")


def cobertura_do_datajud(numero: str) -> bool:
    """O DataJud tem índice para o tribunal do número (o STF e as justiças sem índice público ficam de fora)."""
    partes = parse_cnj_parts(numero)
    return bool(partes and deduzir_aliases_datajud(partes))


def _limpar_textos(resumo: Dict[str, Any]) -> None:
    for campo in CAMPOS_DE_TEXTO:
        resumo[campo] = texto_oficial_sem_cpf(resumo.get(campo))
    resumo["assuntos_tpu"] = assuntos_sem_cpf(resumo.get("assuntos_tpu"))


class ProcessoPublicadoSemConfirmacao(ErroDoDataJud):
    """
    Um processo que já estava no arquivo gerado não se confirmou nesta rodada, mas o DataJud respondeu (não é falha de
    rede): documento ausente, malformado, de outro número, sem classe, ou tribunal sem cobertura. Retirar um vínculo
    publicado só vale por remoção na curadoria, então a extração aborta sem gravar.
    """


# Motivos que, para um processo JÁ publicado, abortam a extração em vez de retirá-lo do arquivo (sinal fraco do tribunal).
# Ficam de fora o que é decisão da curadoria ou do tribunal de fato: entrada inválida e processo que passou a ser sigiloso.
MOTIVOS_QUE_NAO_RETIRAM = frozenset({"sem_cobertura", "nao_encontrados", "malformados", "divergentes", "sem_classe"})


def _identificado(entrada: Dict[str, Any]) -> bool:
    """A curadoria traz o identificador oficial (Câmara ou Senado) da pessoa: processo nunca vai por palpite de nome."""
    return any(inteiro(entrada.get(campo)) is not None for campo in ("camara_id", "senado_id"))


def _avaliar(
    entrada: Any, client: DataJudClient, hoje: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    (item, None, None) quando o processo da curadoria se confirma no DataJud; senão (None, motivo, número). O número é
    o da curadoria, em formato CNJ, ou None quando a entrada nem o tem. Motivo "erros" é a falta de resposta
    conclusiva do DataJud.
    """
    if not isinstance(entrada, dict):
        return None, "invalidas", None
    numero = cnj_valido(entrada.get("numero_processo"))
    vinculo = link_oficial(entrada.get("link_comprovacao"))
    if numero is None or vinculo is None:
        return None, "invalidas", numero
    if not _identificado(entrada):
        return None, "sem_identificador", numero
    if not cobertura_do_datajud(numero):
        logger.warning("Processo %s é de um tribunal que o DataJud não cobre; fora da carga.", numero)
        return None, "sem_cobertura", numero
    try:
        origem = client.consultar_processo(numero)
    except ErroDoDataJud as erro:
        logger.error("%s", erro)
        return None, "erros", numero
    if not origem:
        logger.warning("Processo %s não encontrado no DataJud; fora da carga.", numero)
        return None, "nao_encontrados", numero
    try:
        resumo = client.consolidar_resumo_processo(origem)
    except (TypeError, AttributeError, ValueError):
        logger.warning("Documento do DataJud malformado para %s; fora da carga.", numero)
        return None, "malformados", numero
    if cnj_digitos(resumo.get("numero_processo")) != cnj_digitos(numero):
        logger.warning("O DataJud devolveu outro processo para %s; fora da carga.", numero)
        return None, "divergentes", numero
    if sob_sigilo(resumo.pop("nivel_sigilo", None)):
        logger.warning("Processo %s sob sigilo; fora da carga.", numero)
        return None, "sigilosos", numero
    resumo.pop("classe_assunto", None)  # texto derivado: quem monta "Classe / Assuntos" é a API, a partir dos campos
    _limpar_textos(resumo)
    if not resumo.get("classe_tpu_nome"):
        logger.warning("Processo %s sem classe oficial no DataJud; fora da carga.", numero)
        return None, "sem_classe", numero
    item = {campo: entrada[campo] for campo in CAMPOS_DA_PESSOA if campo in entrada}
    item.update(resumo)
    # o número é o da curadoria, já validado e no formato CNJ; o do DataJud vem sem pontuação
    item["numero_processo"] = numero
    item["link_comprovacao"] = vinculo
    # o dia em que o DataJud foi de fato lido (o do cache, quando veio dele), não o da rodada
    dia_da_consulta = getattr(client, "dia_da_consulta", None)
    item["consultado_em"] = (dia_da_consulta(numero) if callable(dia_da_consulta) else None) or hoje
    return item, None, numero


def enriquecer(
    curadoria: List[Any],
    client: Optional[DataJudClient] = None,
    anteriores: Optional[Set[str]] = None,
    hoje: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Os processos da curadoria com os metadados do DataJud, e a contagem do que ficou de fora e por quê. `anteriores` são
    os números (só dígitos) do arquivo gerado na rodada anterior: um deles que o DataJud não confirma agora por um dos
    `MOTIVOS_QUE_NAO_RETIRAM` conta como `publicados_sem_confirmacao` (a extração aborta), não como retirada.
    """
    client = client or DataJudClient()
    anteriores = anteriores or set()
    dia_da_rodada = (hoje or date.today()).isoformat()
    contagem: Dict[str, int] = defaultdict(int)
    saida: List[Dict[str, Any]] = []
    for entrada in curadoria:
        item, motivo, numero = _avaliar(entrada, client, dia_da_rodada)
        if item is not None:
            saida.append(item)
            continue
        if motivo in MOTIVOS_QUE_NAO_RETIRAM and numero is not None and cnj_digitos(numero) in anteriores:
            logger.error(
                "Processo %s já estava na carga e não se confirmou agora (%s); nada será alterado. Para retirá-lo, "
                "remova-o da curadoria.",
                numero,
                motivo,
            )
            motivo = "publicados_sem_confirmacao"
        contagem[str(motivo)] += 1
    return saida, dict(contagem)


def _numeros_anteriores(caminho: Path) -> Set[str]:
    """Os números (só dígitos) do arquivo gerado antes; ausente ou ilegível, nenhum."""
    anterior = load_json(caminho, None)
    if not isinstance(anterior, list):
        return set()
    return {cnj_digitos(i.get("numero_processo")) for i in anterior if isinstance(i, dict)} - {""}


def extrair(processed_dir: Path = PROCESSED_DATA_DIR, client: Optional[DataJudClient] = None) -> Dict[str, int]:
    """
    Lê a curadoria, consulta o DataJud e grava `processos_judiciais.json`. Curadoria ausente ou que não é uma lista não
    altera nada; processo sem resposta conclusiva do DataJud (ou que sumiu do DataJud depois de publicado) levanta
    `ErroDoDataJud` sem gravar.
    """
    curadoria = load_json(processed_dir / PROCESSOS_CURADORIA_ARQUIVO, None)
    if not isinstance(curadoria, list):
        logger.warning("%s ausente ou inválido; nada foi extraído.", PROCESSOS_CURADORIA_ARQUIVO)
        return {"processos": 0}
    processos, contagem = enriquecer(curadoria, client, _numeros_anteriores(processed_dir / PROCESSOS_ARQUIVO))
    if contagem.get("publicados_sem_confirmacao"):
        raise ProcessoPublicadoSemConfirmacao(
            f"{contagem['publicados_sem_confirmacao']} processo(s) já publicado(s) sem confirmação do DataJud; "
            f"{PROCESSOS_ARQUIVO} não foi alterado. Para retirar um vínculo, remova-o da curadoria."
        )
    if contagem.get("erros"):
        raise ErroDoDataJud(
            f"{contagem['erros']} processo(s) sem resposta conclusiva do DataJud; {PROCESSOS_ARQUIVO} não foi alterado. "
            "Rode de novo quando o DataJud responder."
        )
    atomic_write_json(processed_dir / PROCESSOS_ARQUIVO, processos)
    return {**contagem, "processos": len(processos)}
