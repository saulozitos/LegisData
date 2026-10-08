"""Diagnóstico das emendas sem vínculo: institucional x ambíguo x ausente (mesmo critério do loader)."""

from etl.scripts import diagnose_emendas as de


def _emenda(nome, valor):
    return {"politician_name": nome, "valor_empenhado": valor}


def test_diagnostico_separa_vinculadas_institucionais_ambiguas_e_ausentes():
    # Ana Souza tem nome eleitoral = civil (mesmo político: conta uma vez); João Silva são DOIS políticos
    nomes = [
        (1, "Ana Souza"),
        (1, "Ana Souza"),
        (2, "Ana Souza Lima"),
        (3, "Zé Dep"),
        (4, "João Silva"),
        (5, "Joao Silva"),
    ]
    emendas = [
        _emenda("ANA SOUZA", 100),  # vinculada (nome único)
        _emenda("RELATOR GERAL", 1000),
        _emenda("BANCADA DO CEARA", 500),
        _emenda("JOAO SILVA", 40),  # ambíguo
        _emenda("EX PARLAMENTAR", 7),  # ausente
        _emenda("", 3),  # sem nome
    ]
    r = de.diagnosticar(emendas, nomes)
    assert r["vinculadas"] == {"emendas": 1, "valor_empenhado": 100.0}
    sv = r["sem_vinculo"]
    assert sv["institucional"]["emendas"] == 2 and sv["institucional"]["valor_empenhado"] == 1500.0
    assert sv["institucional"]["autores_distintos"] == 2
    assert sv["ambiguo"] == {"emendas": 1, "valor_empenhado": 40.0, "autores_distintos": 1, "exemplos": ["JOAO SILVA"]}
    assert sv["ausente"]["emendas"] == 2 and sv["ausente"]["valor_empenhado"] == 10.0


def test_classificar_nome_vazio_e_institucional():
    assert de.classificar("", {}) == "ausente"
    assert de.classificar("Comissão de Saúde", {}) == "institucional"
    assert de.classificar("Mesa Diretora", {}) == "institucional"
