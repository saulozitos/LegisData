"""Escrita atômica e proteção contra sobrescrever arquivo bom com resultado vazio."""

import json
import os

import pandas as pd
import pytest

from etl.utils.io_utils import atomic_write_json, atomic_write_text, is_empty_payload, write_json_if_valid


def test_atomic_write_json_cria_diretorio_e_conteudo(tmp_path):
    destino = tmp_path / "novo" / "dados.json"
    atomic_write_json(destino, {"ação": 1})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"ação": 1}
    assert "ação" in destino.read_text(encoding="utf-8")  # ensure_ascii=False
    assert [p.name for p in destino.parent.iterdir()] == ["dados.json"]  # sem sobras temporárias


def test_falha_na_serializacao_preserva_arquivo_anterior_e_nao_deixa_temporario(tmp_path):
    destino = tmp_path / "dados.json"
    atomic_write_json(destino, {"v": "bom"})

    class NaoSerializavel:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(destino, {"v": NaoSerializavel()})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"v": "bom"}
    assert [p.name for p in tmp_path.iterdir()] == ["dados.json"]


def test_falha_no_replace_remove_temporario(tmp_path, monkeypatch):
    destino = tmp_path / "x.txt"
    atomic_write_text(destino, "antigo")

    def quebra(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", quebra)
    with pytest.raises(OSError):
        atomic_write_text(destino, "novo")
    monkeypatch.undo()
    assert destino.read_text() == "antigo"
    assert [p.name for p in tmp_path.iterdir()] == ["x.txt"]


def test_write_json_if_valid_preserva_arquivo_bom_quando_resultado_vazio(tmp_path):
    destino = tmp_path / "senadores.json"
    assert write_json_if_valid(destino, [{"id": 1}]) is True
    assert write_json_if_valid(destino, []) is False
    assert json.loads(destino.read_text(encoding="utf-8")) == [{"id": 1}]


def test_write_json_if_valid_nao_cria_arquivo_vazio(tmp_path):
    destino = tmp_path / "nada.json"
    assert write_json_if_valid(destino, {}) is False
    assert not destino.exists()


def test_write_json_if_valid_respeita_validator(tmp_path):
    destino = tmp_path / "v.json"
    assert write_json_if_valid(destino, [1, 2], validator=lambda x: len(x) > 5) is False
    assert not destino.exists()


def test_is_empty_payload():
    assert is_empty_payload(None) and is_empty_payload([]) and is_empty_payload({}) and is_empty_payload(pd.DataFrame())
    assert not is_empty_payload([0]) and not is_empty_payload(pd.DataFrame({"a": [1]}))
