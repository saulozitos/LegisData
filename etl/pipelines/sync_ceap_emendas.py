"""
Pipeline unificado e idempotente de CEAP (Câmara + Senado) e Emendas Parlamentares.

Substitui `sync_ceap_emendas_2019_2026.py` e `sync_ceap_emendas_lula_bolsonaro.py`, que:
  * gravavam nos mesmos arquivos com esquemas diferentes (chave `por_ano` int x str, cargo DEPUTADO x DEPUTADO_FEDERAL);
  * somavam sobre o resumo existente (rodar duas vezes duplicava `total_gasto`);
  * usavam `hash()` (não determinístico) e aceitavam respostas truncadas (`IncompleteRead.partial`);
  * fabricavam emendas com tetos e cidades inventados.

Aqui o resultado é sempre recalculado do zero para o intervalo pedido (mesma entrada => mesma saída),
as agregações usam identificadores oficiais (ideCadastro / codSenador) e nada é gravado se a extração falhar.

CPF de fornecedor pessoa física nunca é gravado (decisão D3): `CeapAccumulator.add` guarda só o CNPJ de 14 dígitos e o
nome sem documento pessoal embutido, então nem o arquivo processado nem o cache por ano carregam o documento da fonte.

Cada ano é baixado separadamente. Com `cache_dir`, o ano já fechado (depois de 1º de abril do ano seguinte) fica em
cache e só é baixado de novo quando o cache vence (`VALIDADE_DO_CACHE_DIAS`); a atualização diária vai à rede apenas
para o ano corrente (e o anterior até março). Com ou sem cache, vale a mesma política de rede: pausa entre downloads
(a Câmara responde 429 a vários CSVs anuais seguidos), uma segunda tentativa depois de uma pausa maior, e um ano que
volta vazio ou com formato inesperado é falha (nunca "gasto zero"). Um ano com cache vencido cuja nova baixa falha usa o
cache vencido como reserva (e o resumo avisa), em vez de travar a CEAP inteira. A extração de cada fonte é isolada: uma
falha inesperada numa delas não impede a gravação da outra.

Uso:
    python -m etl.pipelines.sync_ceap_emendas --ano-inicio 2019 --ano-fim 2026
"""

import argparse
import copy
import io
import json
import logging
import math
import time
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd

from etl.config import PROCESSED_DATA_DIR, TETO_DO_CSV, TETO_DO_DOWNLOAD
from etl.extractors.emendas_extractor import EmendasExtractor
from etl.pipelines.loader_helpers import cnpj_do_fornecedor, nome_do_fornecedor
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json, write_json_if_valid
from etl.utils.provenance import mark_official

logger = logging.getLogger("CeapEmendasSync")

CEAP_OUTPUT = "despesas_ceap_2019_2026.json"  # nome histórico: a partir de 2027 o arquivo também terá dados de 2027
EMENDAS_OUTPUT = "emendas_parlamentares_2019_2026.json"
ANO_INICIAL_CEAP = 2008  # início da publicação aberta da CEAP
ANO_INICIAL_ARQUIVO = 2019  # início dos arquivos processados (`run_etl --ceap-ano-inicio` e a atualização diária)
TOP_FORNECEDORES = 15
FONTE_CEAP_CAMARA = "Câmara dos Deputados — Cota Parlamentar (CSV oficial)"
FONTE_CEAP_SENADO = "Senado Federal — CEAPS (API de Dados Abertos Administrativos)"
CARGOS = frozenset({"DEPUTADO_FEDERAL", "SENADOR"})
CASA_DO_CARGO = {"DEPUTADO_FEDERAL": "camara", "SENADOR": "senado"}
FONTES = ("ceap", "emendas")

CAMARA_COLS = {
    "txNomeParlamentar",
    "ideCadastro",
    "sgUF",
    "sgPartido",
    "numAno",
    "numMes",
    "txtDescricao",
    "vlrLiquido",
    "txtFornecedor",
    "txtCNPJCPF",
}
# O que o CSV precisa ter para a agregação fazer sentido; a falta de qualquer uma é falha do ano (a Câmara renomeou?)
CAMARA_OBRIGATORIAS = CAMARA_COLS - {"sgUF", "sgPartido", "numMes"}

# ── Política de rede e de cache ───────────────────────────────────────────────────────────────────────────────────────
# Suba VERSAO_DO_CACHE a cada mudança no formato do cache ou na regra de agregação (`CeapAccumulator.add`, `para_json`,
# `mesclar`, colunas lidas): os anos fechados em cache carregariam a regra antiga para sempre. Um teste trava o formato.
VERSAO_DO_CACHE = 2
PASTA_DO_CACHE = "ceap_por_ano"
VALIDADE_DO_CACHE_DIAS = 90  # um ano fechado é baixado de novo depois disso (estornos e correções tardias)
# A Câmara responde 429 (Too Many Requests) a vários CSVs anuais seguidos (visto com 7 downloads em 30 s). O Senado
# limita em 10 requisições por segundo e aqui há uma por ano; a pausa dele é só cortesia.
PAUSA_POR_CASA = {"camara": 10.0, "senado": 1.0}
ESPERA_NOVA_TENTATIVA = 90.0
MESES_DE_ATRASO_DO_ANO_NOVO = 3  # até março o arquivo/lançamento do ano novo pode não existir ainda (o Senado atrasa)
FUSO_DO_BRASIL = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
FRACAO_MINIMA_DAS_EMENDAS = 0.8  # lista de emendas com menos que isso do arquivo anterior é tratada como truncada
LIMITE_DO_VALOR = 10**13  # R$ 10 trilhões: acima disso o número é lixo, e um inteiro gigante não pode estourar o float
# O que pode dar errado ao baixar e ler um ano da fonte: qualquer um vira falha daquele ano, nunca derruba o `run`
ERROS_DA_EXTRACAO = (
    HttpError,
    zipfile.BadZipFile,
    zlib.error,
    EOFError,
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    IndexError,
    pd.errors.ParserError,
    pd.errors.EmptyDataError,
)


def hoje_no_brasil() -> date:
    """A data em Brasília: o servidor e os contêineres rodam em UTC, e 1º de abril vira às 21h do dia 31."""
    return datetime.now(FUSO_DO_BRASIL).date()


# ── Valores lidos da fonte ────────────────────────────────────────────────────────────────────────────────────────────
def _num(valor: Any) -> Optional[float]:
    """O valor em reais, ou None quando falta ou não é um número (nunca 0.0: lançamento sem valor não é gasto zero)."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(str(valor).strip().replace(",", ".")) if not isinstance(valor, (int, float)) else float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return numero if math.isfinite(numero) and abs(numero) <= LIMITE_DO_VALOR else None


def _inteiro_da_fonte(valor: Any) -> Optional[int]:
    """Inteiro de uma célula ("123", "123.0", 123, NaN, vazio); None se falta ou não é inteiro."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return int(float(texto)) if "." in texto or "e" in texto.lower() else int(texto)
    except (ValueError, OverflowError):
        return None


def _numero(valor: Any) -> bool:
    """Número válido no cache: nem bool, nem NaN/infinito, nem inteiro gigante (que estouraria o float)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return False
    return (math.isfinite(valor) if isinstance(valor, float) else True) and abs(valor) <= LIMITE_DO_VALOR


def _inteiro(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor <= 10**9


# ── Formato do registro (uma só definição: `add`, `mesclar` e a validação do cache usam estas fábricas) ───────────────
def _registro_vazio(cargo: str, ident: Any, nome: str, ano: int) -> Dict[str, Any]:
    return {
        "nome": nome,
        "nome_ano": ano,
        "cargo": cargo,
        "camara_id": ident if cargo == "DEPUTADO_FEDERAL" and isinstance(ident, int) else None,
        "senado_id": ident if cargo == "SENADOR" and isinstance(ident, int) else None,
        "total_gasto": 0.0,
        "total_notas": 0,
        "por_ano": {},
        "por_tipo": {},
        "por_ano_tipo": {},
        "fornecedores": {},
    }


def _fornecedor_vazio(nome: str, cnpj: Optional[str]) -> Dict[str, Any]:
    return {"nome": nome, "cnpj_cpf": cnpj, "total": 0.0, "notas": 0}


CAMPOS_DO_REGISTRO = frozenset(_registro_vazio("SENADOR", 1, "X", 2000))
CAMPOS_DO_FORNECEDOR = frozenset(_fornecedor_vazio("X", None))


def _validar_registro(chave: Any, reg: Any) -> Tuple[str, Any]:
    """Confere a forma completa de um item do cache; qualquer divergência levanta ValueError (cache refeito)."""
    if not (isinstance(chave, list) and len(chave) == 2):
        raise ValueError("chave do cache fora do formato [cargo, identificador]")
    cargo, ident = chave
    if cargo not in CARGOS or isinstance(ident, bool) or not isinstance(ident, (int, str)):
        raise ValueError("cargo ou identificador inválido")
    if not isinstance(reg, dict) or set(reg) != CAMPOS_DO_REGISTRO:
        raise ValueError("registro do cache com campos diferentes dos do acumulador")
    if not (isinstance(reg["nome"], str) and reg["nome"] and reg["cargo"] == cargo):
        raise ValueError("nome ou cargo do registro inválido")
    # os identificadores do registro são os da chave: o loader liga o gasto à pessoa por eles
    esperado = _registro_vazio(cargo, ident, reg["nome"], 0)
    if reg["camara_id"] != esperado["camara_id"] or reg["senado_id"] != esperado["senado_id"]:
        raise ValueError("camara_id/senado_id não correspondem à chave")
    if not (_numero(reg["total_gasto"]) and _inteiro(reg["total_notas"]) and _inteiro(reg["nome_ano"])):
        raise ValueError("totais do registro inválidos")
    for campo in ("por_ano", "por_tipo"):
        mapa = reg[campo]
        if not isinstance(mapa, dict) or not all(isinstance(k, str) and _numero(v) for k, v in mapa.items()):
            raise ValueError(f"{campo} inválido")
    por_ano_tipo = reg["por_ano_tipo"]
    if not isinstance(por_ano_tipo, dict) or not all(
        isinstance(a, str) and isinstance(t, dict) and all(isinstance(k, str) and _numero(v) for k, v in t.items())
        for a, t in por_ano_tipo.items()
    ):
        raise ValueError("por_ano_tipo inválido")
    fornecedores = reg["fornecedores"]
    if not isinstance(fornecedores, dict):
        raise ValueError("fornecedores inválidos")
    for nome, forn in fornecedores.items():
        if not (isinstance(forn, dict) and set(forn) == CAMPOS_DO_FORNECEDOR and forn["nome"] == nome):
            raise ValueError("fornecedor com campos diferentes dos do acumulador")
        if not (_numero(forn["total"]) and _inteiro(forn["notas"])):
            raise ValueError("totais do fornecedor inválidos")
        # o saneamento vale também para o que já está em disco: uma regra nova de nome ou de documento recusa o cache velho
        if nome_do_fornecedor(nome) != nome or not (
            forn["cnpj_cpf"] is None
            or (isinstance(forn["cnpj_cpf"], str) and cnpj_do_fornecedor(forn["cnpj_cpf"]) == forn["cnpj_cpf"])
        ):
            raise ValueError("fornecedor ou documento fora da regra de saneamento")
    return cargo, ident


class CeapAccumulator:
    """
    Acumula despesas por parlamentar. Chave = (cargo, identificador oficial); o nome é só rótulo (o do ano mais recente).
    Valores negativos (estornos) reduzem os totais; `total_notas` conta apenas lançamentos positivos.
    """

    def __init__(self) -> None:
        self._dados: Dict[Tuple[str, Any], Dict[str, Any]] = {}

    @property
    def vazio(self) -> bool:
        return not self._dados

    def add(
        self,
        cargo: str,
        ident: Any,
        nome: str,
        ano: int,
        mes: Optional[int],
        tipo: str,
        fornecedor: str,
        cnpj: Optional[str],
        valor: float,
    ) -> None:
        if not nome or not math.isfinite(valor) or valor == 0:
            return
        # Nada de CPF em disco (D3): só o CNPJ de 14 dígitos fica, e o nome perde o documento pessoal embutido (MEI
        # aparece como "NOME 09876543200"). O loader aplica as mesmas regras, então o `fin` recebe o mesmo de antes.
        fornecedor = nome_do_fornecedor(fornecedor)
        cnpj = cnpj_do_fornecedor(cnpj)
        chave = (cargo, ident if ident is not None else nome.upper().strip())
        reg = self._dados.setdefault(chave, _registro_vazio(cargo, ident, nome.upper().strip(), ano))
        if ano > reg["nome_ano"]:  # o rótulo é o do lançamento mais recente, na ordem que os anos chegarem
            reg["nome"], reg["nome_ano"] = nome.upper().strip(), ano
        ano_s = str(ano)
        reg["total_gasto"] += valor
        if valor > 0:
            reg["total_notas"] += 1
        reg["por_ano"][ano_s] = reg["por_ano"].get(ano_s, 0.0) + valor
        reg["por_tipo"][tipo] = reg["por_tipo"].get(tipo, 0.0) + valor
        por_tipo_ano = reg["por_ano_tipo"].setdefault(ano_s, {})
        por_tipo_ano[tipo] = por_tipo_ano.get(tipo, 0.0) + valor

        forn = reg["fornecedores"].setdefault(fornecedor, _fornecedor_vazio(fornecedor, cnpj))
        forn["total"] += valor
        if valor > 0:
            forn["notas"] += 1
        if not forn.get("cnpj_cpf") and cnpj:
            forn["cnpj_cpf"] = cnpj

    def para_json(self) -> List[Dict[str, Any]]:
        """Estado completo (sem truncar fornecedores) para o cache por ano; a chave vira lista [cargo, identificador]."""
        return [{"chave": [cargo, ident], "reg": reg} for (cargo, ident), reg in self._dados.items()]

    @classmethod
    def de_json(cls, itens: Any) -> "CeapAccumulator":
        """Reconstrói o acumulador de um cache; forma inválida ou chave repetida em qualquer item levanta ValueError."""
        if not isinstance(itens, list):
            raise ValueError("dados do cache não são lista")
        acc = cls()
        for item in itens:
            if not isinstance(item, dict) or "chave" not in item or "reg" not in item:
                raise ValueError("item do cache sem chave/reg")
            cargo, ident = _validar_registro(item["chave"], item["reg"])
            if (cargo, ident) in acc._dados:
                raise ValueError("chave repetida no cache")
            acc._dados[(cargo, ident)] = item["reg"]
        return acc

    def mesclar(self, outro: "CeapAccumulator") -> None:
        """Soma os totais de `outro` (anos diferentes dos já acumulados). O nome é o do ano mais recente, em qualquer ordem."""
        for chave, novo in outro._dados.items():
            reg = self._dados.get(chave)
            if reg is None:
                self._dados[chave] = copy.deepcopy(novo)
                continue
            if novo["nome_ano"] > reg["nome_ano"]:
                reg["nome"], reg["nome_ano"] = novo["nome"], novo["nome_ano"]
            reg["total_gasto"] += novo["total_gasto"]
            reg["total_notas"] += novo["total_notas"]
            for campo in ("por_ano", "por_tipo"):
                for k, v in novo[campo].items():
                    reg[campo][k] = reg[campo].get(k, 0.0) + v
            for ano, tipos in novo["por_ano_tipo"].items():
                destino = reg["por_ano_tipo"].setdefault(ano, {})
                for tipo, v in tipos.items():
                    destino[tipo] = destino.get(tipo, 0.0) + v
            for nome_f, forn in novo["fornecedores"].items():
                atual = reg["fornecedores"].setdefault(nome_f, _fornecedor_vazio(nome_f, forn.get("cnpj_cpf")))
                atual["total"] += forn["total"]
                atual["notas"] += forn["notas"]
                if not atual.get("cnpj_cpf") and forn.get("cnpj_cpf"):
                    atual["cnpj_cpf"] = forn["cnpj_cpf"]

    def finalize(self, fonte_por_cargo: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """Arredonda, mantém os maiores fornecedores e resolve homônimos sem perder ninguém."""
        saida: Dict[str, Dict[str, Any]] = {}
        for (cargo, ident), reg in sorted(self._dados.items(), key=lambda kv: (kv[1]["nome"], str(kv[0][1]))):
            top = sorted(reg["fornecedores"].values(), key=lambda f: f["total"], reverse=True)[:TOP_FORNECEDORES]
            final = {
                **{k: v for k, v in reg.items() if k != "nome_ano"},  # detalhe interno do acumulador
                "total_gasto": round(reg["total_gasto"], 2),
                "por_ano": {a: round(v, 2) for a, v in sorted(reg["por_ano"].items())},
                "por_tipo": {t: round(v, 2) for t, v in sorted(reg["por_tipo"].items())},
                "por_ano_tipo": {
                    a: {t: round(v, 2) for t, v in sorted(tipos.items())}
                    for a, tipos in sorted(reg["por_ano_tipo"].items())
                },
                "fornecedores": {f["nome"]: {**f, "total": round(f["total"], 2)} for f in top},
            }
            mark_official(final, fonte_por_cargo[cargo])
            nome = reg["nome"]
            if nome in saida:  # homônimo: desambigua pelo identificador oficial
                nome = f"{nome} [{ident}]"
            saida[nome] = final
        return saida


# ── Extração de um ano ────────────────────────────────────────────────────────────────────────────────────────────────
Extrator = Callable[..., Tuple[int, List[int]]]


def _registrar_linhas_invalidas(fonte: str, ano: int, invalidas: int) -> None:
    if invalidas:
        logger.warning(
            "[%s %s] %d lançamento(s) sem valor numérico ficaram de fora (sem valor não é gasto zero)",
            fonte,
            ano,
            invalidas,
        )


def extract_camara_ceap(
    http: HttpClient, anos: Iterable[int], acc: CeapAccumulator, ausentes: Optional[List[int]] = None
) -> Tuple[int, List[int]]:
    """
    Baixa o CSV anual da Câmara. Devolve (registros, anos_com_falha). Um ano cujo arquivo não existe (HTTP 404) entra
    também em `ausentes`, para o chamador distinguir "ainda não publicado" de falha de rede. Qualquer problema ao ler o
    ano (zip corrompido, coluna renomeada, linha malformada) é falha daquele ano: nada dele chega ao acumulador.
    """
    total, falhas = 0, []
    for ano in anos:
        t0 = time.time()
        url = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
        try:
            conteudo = http.get_bytes(url, max_bytes=TETO_DO_DOWNLOAD)
            with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                membro = z.infolist()[0]
                if membro.file_size > TETO_DO_CSV:
                    raise ValueError(f"CSV descomprimido de {membro.file_size} bytes passa do teto de {TETO_DO_CSV}")
                with z.open(membro) as f:
                    df = pd.read_csv(
                        f,
                        sep=";",
                        encoding="utf-8-sig",
                        low_memory=False,
                        usecols=lambda c: c in CAMARA_COLS,
                        # texto puro: um documento só de dígitos seria lido como float ("07575651000159" -> 7575651000159.0)
                        dtype={"txtCNPJCPF": str, "ideCadastro": str, "numAno": str, "numMes": str},
                    )
            faltam = CAMARA_OBRIGATORIAS - set(df.columns)
            if faltam:
                raise ValueError(f"colunas ausentes no CSV: {sorted(faltam)}")
            parcial, invalidas = CeapAccumulator(), 0
            for row in df.to_dict(orient="records"):
                valor = _num(row.get("vlrLiquido"))
                if valor is None:
                    invalidas += 1
                    continue
                documento = row.get("txtCNPJCPF")
                parcial.add(
                    "DEPUTADO_FEDERAL",
                    _inteiro_da_fonte(row.get("ideCadastro")),
                    str(row.get("txNomeParlamentar") or ""),
                    _inteiro_da_fonte(row.get("numAno")) or ano,
                    _inteiro_da_fonte(row.get("numMes")),
                    str(row.get("txtDescricao") or "OUTROS").strip(),
                    str(row.get("txtFornecedor") or "Não informado").strip(),
                    str(documento) if isinstance(documento, str) else None,
                    valor,
                )
        except ERROS_DA_EXTRACAO as exc:
            logger.warning("[Câmara %s] falha na extração: %s", ano, exc)
            falhas.append(ano)
            if isinstance(exc, HttpError) and exc.status == 404 and ausentes is not None:
                ausentes.append(ano)
            continue
        _registrar_linhas_invalidas("Câmara", ano, invalidas)
        acc.mesclar(parcial)
        total += len(df)
        logger.info("[Câmara %s] %s registros em %.1fs", ano, f"{len(df):,}", time.time() - t0)
    return total, falhas


def extract_senado_ceaps(
    http: HttpClient, anos: Iterable[int], acc: CeapAccumulator, ausentes: Optional[List[int]] = None
) -> Tuple[int, List[int]]:
    """Baixa a CEAPS do Senado ano a ano. Respostas truncadas são re-tentadas; formato inesperado é falha do ano."""
    total, falhas = 0, []
    for ano in anos:
        t0 = time.time()
        url = f"https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}"
        try:
            dados = http.get_json(url, max_bytes=TETO_DO_DOWNLOAD)
            itens = dados if isinstance(dados, list) else (dados.get("despesas") if isinstance(dados, dict) else None)
            if not isinstance(itens, list):  # `null`/objeto sem a lista não é "ano sem despesas": é resposta inesperada
                raise ValueError(f"resposta do Senado sem a lista de despesas ({type(dados).__name__})")
            parcial, invalidas = CeapAccumulator(), 0
            for item in itens:
                valor = _num(item.get("valorReembolsado")) if isinstance(item, dict) else None
                if valor is None:
                    invalidas += 1
                    continue
                parcial.add(
                    "SENADOR",
                    _inteiro_da_fonte(item.get("codSenador")),
                    str(item.get("nomeSenador") or ""),
                    _inteiro_da_fonte(item.get("ano")) or ano,
                    _inteiro_da_fonte(item.get("mes")),
                    str(item.get("tipoDespesa") or "OUTROS").strip(),
                    str(item.get("fornecedor") or "Não informado").strip(),
                    item.get("cpfCnpj") if isinstance(item.get("cpfCnpj"), str) else None,
                    valor,
                )
        except ERROS_DA_EXTRACAO as exc:
            logger.warning("[Senado %s] falha na extração: %s", ano, exc)
            falhas.append(ano)
            if isinstance(exc, HttpError) and exc.status == 404 and ausentes is not None:
                ausentes.append(ano)
            continue
        _registrar_linhas_invalidas("Senado", ano, invalidas)
        acc.mesclar(parcial)
        total += len(itens)
        logger.info("[Senado %s] %s registros em %.1fs", ano, f"{len(itens):,}", time.time() - t0)
    return total, falhas


# ── Cache por ano ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _definitivo(ano: int, hoje: date) -> bool:
    """
    A CEAP de um ano só é dado fechado depois de 1º de abril do ano seguinte (a Câmara e o Senado ainda corrigem
    lançamentos nos primeiros meses). Antes disso o ano é baixado de novo a cada execução e nunca fica em cache.
    """
    return hoje >= date(ano + 1, 4, 1)


def _arquivo_do_cache(cache_dir: Path, casa: str, ano: int) -> Path:
    return Path(cache_dir) / f"{casa}_{ano}.json"


def _ler_cache(
    cache_dir: Path, casa: str, ano: int, hoje: date, aceitar_vencido: bool = False
) -> Optional[CeapAccumulator]:
    """
    O cache do ano, ou None se não existe, tem forma inválida, é de outra versão, nasceu antes de o ano fechar, tem data
    no futuro ou venceu (`aceitar_vencido` deixa passar só o vencimento: é a reserva quando a nova baixa falha).
    """
    try:
        conteudo = json.loads(_arquivo_do_cache(cache_dir, casa, ano).read_text(encoding="utf-8"))
        if not isinstance(conteudo, dict) or conteudo.get("versao") != VERSAO_DO_CACHE:
            return None
        if conteudo.get("casa") != casa or conteudo.get("ano") != ano or not conteudo.get("dados"):
            return None
        gerado_em = date.fromisoformat(conteudo["gerado_em"])
        if gerado_em > hoje or not _definitivo(ano, gerado_em):
            return None
        if not aceitar_vencido and (hoje - gerado_em).days > VALIDADE_DO_CACHE_DIAS:
            return None
        return CeapAccumulator.de_json(conteudo["dados"])
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return None


def _gravar_cache(cache_dir: Path, casa: str, ano: int, acc: CeapAccumulator, hoje: date) -> None:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        _arquivo_do_cache(cache_dir, casa, ano),
        {
            "versao": VERSAO_DO_CACHE,
            "casa": casa,
            "ano": ano,
            "gerado_em": hoje.isoformat(),
            "dados": acc.para_json(),
        },
        indent=None,
        allow_nan=False,
    )


def _baixar_ano(
    http: HttpClient, ano: int, casa: str, extrator: Extrator, hoje: date, ja_publicado: bool
) -> Tuple[Optional[CeapAccumulator], bool]:
    """
    Baixa um ano, com uma segunda tentativa depois de `ESPERA_NOVA_TENTATIVA` (menos para arquivo inexistente).
    Devolve (acumulador, ainda_sem_arquivo): acumulador None é falha. `ainda_sem_arquivo` só vale para o ano corrente nos
    primeiros meses, quando a fonte pode não ter publicado o ano novo (falta de arquivo não é zero gasto) E só se o ano
    ainda não tinha sido publicado antes (`ja_publicado`): um vazio ou 404 que aparece depois de o ano já ter dados é
    soluço da fonte, e apagar o ano do arquivo e do `fin` seria perder dado.
    """
    no_comeco_do_ano = ano == hoje.year and hoje.month <= MESES_DE_ATRASO_DO_ANO_NOVO and not ja_publicado
    for tentativa in (1, 2):
        parcial, ausentes = CeapAccumulator(), []
        _, falhou = extrator(http, [ano], parcial, ausentes=ausentes)
        if not falhou and not parcial.vazio:
            return parcial, False
        if falhou and ano in ausentes:
            return (None, True) if no_comeco_do_ano else (None, False)  # 404 não ganha segunda tentativa
        if not falhou and no_comeco_do_ano:
            return None, True  # resposta vazia no começo do ano: ainda não há despesa lançada
        logger.warning(
            "[%s %s] %s; %s",
            casa,
            ano,
            "falhou" if falhou else "veio vazio",
            "nova tentativa depois da pausa" if tentativa == 1 else "desistindo",
        )
        if tentativa == 1:
            time.sleep(ESPERA_NOVA_TENTATIVA)
    return None, False


@dataclass
class ResultadoDosAnos:
    baixados: int = 0
    falhas: List[int] = field(default_factory=list)
    do_cache: List[int] = field(default_factory=list)
    sem_arquivo: List[int] = field(default_factory=list)
    cache_vencido: List[int] = field(default_factory=list)  # a baixa falhou e o cache vencido serviu de reserva


def _extrair_anos(
    http: HttpClient,
    anos: Iterable[int],
    casa: str,
    extrator: Extrator,
    acc: CeapAccumulator,
    cache_dir: Optional[Path],
    hoje: date,
    publicados: Optional[Set[int]] = None,
) -> ResultadoDosAnos:
    """
    Extrai ano a ano, em ordem crescente. Com `cache_dir`, ano fechado e em cache entra sem baixar nada; os demais são
    baixados (com pausa entre downloads) e, se o ano já está fechado, vão para o cache. Se a baixa de um ano fechado
    falha mas existe um cache vencido dele, o cache vencido entra no lugar (e fica registrado): travar a CEAP inteira por
    um ano que já se conhece seria pior. Uma falha sem reserva em qualquer ano aborta a gravação do arquivo final.
    """
    resultado, baixou = ResultadoDosAnos(), False
    for ano in sorted(anos):
        if cache_dir is not None and _definitivo(ano, hoje):
            guardado = _ler_cache(cache_dir, casa, ano, hoje)
            if guardado is not None:
                acc.mesclar(guardado)
                resultado.do_cache.append(ano)
                continue
        if baixou:
            time.sleep(PAUSA_POR_CASA[casa])
        baixou = True
        parcial, ainda_sem_arquivo = _baixar_ano(http, ano, casa, extrator, hoje, ano in (publicados or set()))
        if ainda_sem_arquivo:
            resultado.sem_arquivo.append(ano)
            continue
        if parcial is None:
            vencido = _ler_cache(cache_dir, casa, ano, hoje, aceitar_vencido=True) if cache_dir is not None else None
            if vencido is not None:
                logger.warning("[%s %s] a baixa falhou; usando o cache vencido como reserva", casa, ano)
                acc.mesclar(vencido)
                resultado.cache_vencido.append(ano)
            else:
                resultado.falhas.append(ano)
            continue
        resultado.baixados += 1
        if cache_dir is not None and _definitivo(ano, hoje):
            _gravar_cache(cache_dir, casa, ano, parcial, hoje)
        acc.mesclar(parcial)
    return resultado


def anos_publicados_no_arquivo(caminho: Path) -> Dict[str, Set[int]]:
    """Os anos que o arquivo processado da CEAP já traz com gasto, por casa ("camara"/"senado"); vazio se ilegível."""
    publicados: Dict[str, Set[int]] = {"camara": set(), "senado": set()}
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        for reg in dados.values():
            casa = CASA_DO_CARGO.get(reg.get("cargo"))
            if casa:
                publicados[casa].update(int(ano) for ano, valor in reg.get("por_ano", {}).items() if valor)
    except (OSError, ValueError, AttributeError, TypeError):
        return {"camara": set(), "senado": set()}
    return publicados


def run(
    ano_inicio: int = ANO_INICIAL_CEAP,
    ano_fim: Optional[int] = None,
    ceap: bool = True,
    emendas: bool = True,
    http: Optional[HttpClient] = None,
    cache_dir: Optional[Path] = None,
    hoje: Optional[date] = None,
    anos_publicados: Optional[Dict[str, Set[int]]] = None,
) -> Dict[str, Any]:
    """
    Sincroniza CEAP e emendas. Com `cache_dir`, a CEAP de cada ano já fechado é guardada e não é baixada de novo até o
    cache vencer: a atualização diária só refaz o ano corrente (e o anterior até março). Cada fonte é independente: a
    falha (até a inesperada) de uma não impede a gravação da outra, e o resumo diz o que foi gravado (`ceap_gravado`,
    `emendas_gravado`). `anos_publicados` (casa -> anos que já tinham gasto) protege o ano corrente de ser apagado por um
    soluço da fonte no começo do ano; sem ele vale o que o arquivo processado anterior já traz.
    """
    hoje = hoje or hoje_no_brasil()
    ano_fim = ano_fim or hoje.year
    if ano_inicio > ano_fim:
        raise ValueError("ano_inicio não pode ser maior que ano_fim")
    http_injetado = http is not None
    http = http or HttpClient(timeout=60.0, max_retries=3)
    anos = list(range(ano_inicio, ano_fim + 1))
    resumo: Dict[str, Any] = {"anos": f"{ano_inicio}-{ano_fim}"}

    if ceap:
        try:
            _sincronizar_ceap(http, anos, cache_dir, hoje, anos_publicados, resumo)
        except Exception as exc:  # noqa: BLE001 - uma fonte nunca derruba a outra; o erro fica no resumo e no log
            logger.error("CEAP: falha inesperada: %s", exc, exc_info=True)
            resumo["ceap_gravado"], resumo["ceap_erro"] = False, f"{type(exc).__name__}: {exc}"

    if emendas:
        try:
            _sincronizar_emendas(ano_inicio, ano_fim, http if http_injetado else None, resumo)
        except Exception as exc:  # noqa: BLE001
            logger.error("Emendas: falha inesperada: %s", exc, exc_info=True)
            resumo["emendas_gravado"], resumo["emendas_erro"] = False, f"{type(exc).__name__}: {exc}"

    logger.info("Sincronização concluída: %s", resumo)
    return resumo


def _sincronizar_ceap(
    http: HttpClient,
    anos: List[int],
    cache_dir: Optional[Path],
    hoje: date,
    anos_publicados: Optional[Dict[str, Set[int]]],
    resumo: Dict[str, Any],
) -> None:
    acc = CeapAccumulator()
    ja_publicados = (
        anos_publicados if anos_publicados is not None else anos_publicados_no_arquivo(PROCESSED_DATA_DIR / CEAP_OUTPUT)
    )
    por_casa = {}
    for casa, extrator in (("camara", extract_camara_ceap), ("senado", extract_senado_ceaps)):
        por_casa[casa] = _extrair_anos(http, anos, casa, extrator, acc, cache_dir, hoje, ja_publicados.get(casa, set()))
    falhas = {casa: r.falhas for casa, r in por_casa.items()}
    resumo["ceap_anos_baixados"] = {casa: r.baixados for casa, r in por_casa.items()}
    resumo["ceap_falhas"] = falhas
    if cache_dir is not None:
        resumo["ceap_anos_do_cache"] = {casa: r.do_cache for casa, r in por_casa.items()}
    for chave, atributo in (("ceap_anos_sem_arquivo", "sem_arquivo"), ("ceap_anos_cache_vencido", "cache_vencido")):
        achados = {casa: getattr(r, atributo) for casa, r in por_casa.items() if getattr(r, atributo)}
        if achados:
            resumo[chave] = achados
    if any(falhas.values()):
        # Um ano faltando silenciosamente geraria totais subestimados: aborta sem gravar.
        logger.error("CEAP incompleta (anos com falha: %s). Arquivo anterior preservado.", falhas)
        resumo["ceap_gravado"] = False
        return
    resultado = acc.finalize({"DEPUTADO_FEDERAL": FONTE_CEAP_CAMARA, "SENADOR": FONTE_CEAP_SENADO})
    resumo["ceap_gravado"] = write_json_if_valid(PROCESSED_DATA_DIR / CEAP_OUTPUT, resultado, indent=None)
    resumo["ceap_parlamentares"] = len(resultado)


def _sincronizar_emendas(ano_inicio: int, ano_fim: int, http: Optional[HttpClient], resumo: Dict[str, Any]) -> None:
    registros = EmendasExtractor(http=http).fetch_portal()
    registros = [r for r in registros if ano_inicio <= r["ano"] <= ano_fim] if registros else []
    resumo["emendas_registros"] = len(registros)
    if _emendas_truncadas(registros, PROCESSED_DATA_DIR / EMENDAS_OUTPUT):
        resumo["emendas_gravado"] = False
    else:
        resumo["emendas_gravado"] = write_json_if_valid(PROCESSED_DATA_DIR / EMENDAS_OUTPUT, registros, indent=None)


def _emendas_truncadas(registros: List[Any], anterior: Path) -> bool:
    """True se a lista nova tem menos de FRACAO_MINIMA_DAS_EMENDAS do arquivo anterior (download cortado no meio)."""
    try:
        antes = json.loads(anterior.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(antes, list) or not antes or not registros:
        return False
    if len(registros) < len(antes) * FRACAO_MINIMA_DAS_EMENDAS:
        logger.error(
            "Emendas: %d registros contra %d no arquivo anterior (menos de %.0f%%); download tratado como truncado, "
            "arquivo anterior preservado.",
            len(registros),
            len(antes),
            FRACAO_MINIMA_DAS_EMENDAS * 100,
        )
        return True
    return False


def fontes_nao_gravadas(resumo: Dict[str, Any]) -> List[str]:
    """As fontes ("ceap", "emendas") que o `run` tentou e não gravou; vazio quando tudo foi gravado ou não foi pedido."""
    return [fonte for fonte in FONTES if resumo.get(f"{fonte}_gravado") is False]


def main(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Sincroniza CEAP (Câmara/Senado) e emendas parlamentares.")
    parser.add_argument("--ano-inicio", type=int, default=ANO_INICIAL_CEAP)
    parser.add_argument("--ano-fim", type=int, default=None)
    parser.add_argument("--sem-ceap", action="store_true")
    parser.add_argument("--sem-emendas", action="store_true")
    args = parser.parse_args(argv)
    return run(args.ano_inicio, args.ano_fim, ceap=not args.sem_ceap, emendas=not args.sem_emendas)


if __name__ == "__main__":
    main()
