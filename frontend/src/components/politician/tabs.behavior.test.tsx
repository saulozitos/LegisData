import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { fullDossier, sparseDossier } from '@/test/dossier';
import OverviewTab from './OverviewTab';
import IntelligenceTab from './IntelligenceTab';
import PropositionsTab from './PropositionsTab';
import FinancingTab from './FinancingTab';
import CeapTab from './CeapTab';
import AmendmentsTab from './AmendmentsTab';
import JusticeTab from './JusticeTab';
import AttendanceTab from './AttendanceTab';
import RemunerationTab from './RemunerationTab';
import VotesTab from './VotesTab';
import PoliticianHeaderCard from './PoliticianHeaderCard';
import PoliticianTabNav from './PoliticianTabNav';
import { formatCpfCnpj, formatMoney, getFichaStatus, gradeBadgeClass, riskBadgeClass, compatBadgeClass, orUnavailable, NA_BADGE } from './format';

vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);

describe('format helpers', () => {
  it('formatCpfCnpj mascara documentos e preserva o resto', () => {
    expect(formatCpfCnpj('12345678901')).toBe('***.456.789-**');
    expect(formatCpfCnpj('12345678000190')).toBe('**.345.678/0001-**');
    expect(formatCpfCnpj(null)).toBe('Não informado');
    expect(formatCpfCnpj('***.456.789-**')).toBe('***.456.789-**'); // já mascarado (9 dígitos): preservado
    expect(formatCpfCnpj('abc')).toBe('abc');
  });

  it('formatMoney nunca devolve R$ 0,00 para ausente', () => {
    expect(formatMoney(null)).toBe('Indisponível');
    expect(formatMoney(undefined)).toBe('Indisponível');
    expect(formatMoney(NaN)).toBe('Indisponível');
    expect(formatMoney(0).replace(/\s/g, ' ')).toBe('R$ 0,00'); // zero legítimo é preservado
    expect(formatMoney(1234.5).replace(/\s/g, ' ')).toBe('R$ 1.234,50');
  });

  it('getFichaStatus separa declarado, sem registros e desconhecido', () => {
    const d = fullDossier();
    expect(getFichaStatus(d)).toBe('none');
    d.ficha_limpa!.possui_processos_declarados = true;
    expect(getFichaStatus(d)).toBe('declared');
    d.ficha_limpa = undefined;
    expect(getFichaStatus(d)).toBe('unknown');
    expect(getFichaStatus(sparseDossier())).toBe('unknown');
    const odd = fullDossier();
    (odd.ficha_limpa as unknown as { possui_processos_declarados: unknown }).possui_processos_declarados = undefined;
    expect(getFichaStatus(odd)).toBe('unknown');
  });

  it('selos usam classe neutra quando não há classificação (nunca alarme por padrão)', () => {
    expect(gradeBadgeClass(null)).toBe(NA_BADGE);
    expect(gradeBadgeClass('A+')).toContain('emerald');
    expect(gradeBadgeClass('B')).toContain('cyan');
    expect(gradeBadgeClass('D')).toContain('amber');
    expect(riskBadgeClass(null)).toBe(NA_BADGE);
    expect(riskBadgeClass('BAIXO')).toContain('emerald');
    expect(riskBadgeClass('MODERADO')).toContain('amber');
    expect(riskBadgeClass('ALERTA')).toContain('rose');
    expect(compatBadgeClass(null)).toBe(NA_BADGE);
    expect(compatBadgeClass('COMPATÍVEL')).toContain('emerald');
    expect(compatBadgeClass('MODERADO')).toContain('amber');
    expect(compatBadgeClass('ATÍPICO')).toContain('rose');
    expect(orUnavailable(null)).toBe('Indisponível');
    expect(orUnavailable('X')).toBe('X');
  });
});

describe('IntelligenceTab', () => {
  it('com dados mostra nota, risco, compatibilidade e diagnósticos', () => {
    render(<IntelligenceTab dossier={fullDossier()} />);
    expect(screen.getByText('B+')).toBeInTheDocument();
    expect(screen.getByText('78/100 pontos')).toBeInTheDocument();
    expect(screen.getByText('Risco MODERADO')).toBeInTheDocument();
    expect(screen.getAllByText('COMPATÍVEL').length).toBeGreaterThan(0);
    expect(screen.getByText('ROI diagnóstico.')).toBeInTheDocument();
    expect(screen.getByText('+R$ 400.000,00', { exact: false })).toBeInTheDocument();
  });

  it('com dados insuficientes (null) mostra indisponível sem quebrar nem alarmar', () => {
    render(<IntelligenceTab dossier={sparseDossier()} />);
    expect(screen.getByText('Nota indisponível')).toBeInTheDocument();
    expect(screen.getByText('Risco indisponível')).toBeInTheDocument();
    expect(screen.getAllByText('Indisponível').length).toBeGreaterThan(3);
    expect(screen.queryByText('ATÍPICO')).not.toBeInTheDocument();
    expect(screen.getAllByText('Dados insuficientes.', { selector: 'p' })).toHaveLength(2);
  });

  it('sem o bloco de índices mostra estado vazio', () => {
    const d = fullDossier();
    d.indices_inteligencia = undefined;
    render(<IntelligenceTab dossier={d} />);
    expect(screen.getByText('Inteligência cívica indisponível')).toBeInTheDocument();
  });
});

describe('OverviewTab', () => {
  it('mostra contatos reais com links e navega para a auditoria', () => {
    const onChangeTab = vi.fn();
    render(<OverviewTab dossier={fullDossier()} onChangeTab={onChangeTab} onSelectParty={() => {}} />);
    expect(screen.getByRole('link', { name: /Enviar mensagem/ })).toHaveAttribute('href', 'mailto:dep.ana@camara.leg.br');
    expect(screen.getByRole('link', { name: /Ligar para o gabinete/ })).toHaveAttribute('href', 'tel:6132151234');
    fireEvent.click(screen.getByRole('button', { name: /Auditoria Completa/ }));
    expect(onChangeTab).toHaveBeenCalledWith('inteligencia');
  });

  it('contatos ausentes aparecem como "Dado indisponível" (nunca inventados)', () => {
    render(<OverviewTab dossier={sparseDossier()} onChangeTab={() => {}} onSelectParty={() => {}} />);
    expect(screen.getAllByText('Dado indisponível').length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByRole('link', { name: /Ligar para o gabinete/ })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/@camara\.leg\.br|3215-5000/);
  });

  it('nota do ROI com score nulo não derruba a visão geral', () => {
    render(<OverviewTab dossier={sparseDossier()} onChangeTab={() => {}} />);
    expect(screen.getByText('Nota indisponível')).toBeInTheDocument();
  });
});

describe('PoliticianTabNav', () => {
  it('expõe as 10 abas, marca a ativa e notifica a troca', () => {
    const onChange = vi.fn();
    render(<PoliticianTabNav dossier={fullDossier()} activeTab="ceap" onChange={onChange} />);
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(10);
    expect(screen.getByRole('tab', { name: /Custos do Mandato/ })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('tab', { name: /Votações Nominais/ }));
    expect(onChange).toHaveBeenCalledWith('votacoes');
    expect(screen.getByText('Nota B+')).toBeInTheDocument();
    expect(screen.getByText(/Presenças \(95,0%\)/)).toBeInTheDocument();
  });

  it('com dados ausentes não mostra nota e indica presença "n/d"', () => {
    render(<PoliticianTabNav dossier={sparseDossier()} activeTab="visao_geral" onChange={() => {}} />);
    expect(screen.queryByText(/^Nota /)).not.toBeInTheDocument();
    expect(screen.getByText(/Presenças \(n\/d\)/)).toBeInTheDocument();
    expect(screen.getByText('Indisponível')).toBeInTheDocument(); // selo da aba Justiça
  });
});

describe('PoliticianHeaderCard', () => {
  it('identifica o parlamentar e dispara voltar / abrir justiça', () => {
    const onBack = vi.fn();
    const onChangeTab = vi.fn();
    const onSelectParty = vi.fn();
    render(<PoliticianHeaderCard dossier={fullDossier()} onBack={onBack} onChangeTab={onChangeTab} onSelectParty={onSelectParty} />);
    expect(screen.getByRole('heading', { level: 2, name: 'Ana Silva' })).toBeInTheDocument();
    expect(screen.getByText('Deputado Federal')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Voltar ao Catálogo/ }));
    expect(onBack).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /nenhum processo declarado na base/ }));
    expect(onChangeTab).toHaveBeenCalledWith('justica');
    fireEvent.click(screen.getAllByRole('button', { name: 'PT' })[0]);
    expect(onSelectParty).toHaveBeenCalledWith('PT');
  });

  it('sem dados mostra indisponibilidade em vez de "Nada Consta", 0% ou 100%', () => {
    render(<PoliticianHeaderCard dossier={sparseDossier()} onBack={() => {}} onChangeTab={() => {}} />);
    expect(screen.getByText('Ficha/Certidões: dado indisponível')).toBeInTheDocument();
    expect(screen.getByText('Presença indisponível')).toBeInTheDocument();
    expect(screen.getByText('Senador Federal')).toBeInTheDocument();
    expect(screen.getAllByText('Dado indisponível').length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/Nada Consta/);
    expect(screen.getByText('Taxa de Governismo:').nextElementSibling).toHaveTextContent('Indisponível');
  });

  it('processos declarados destacam os órgãos', () => {
    const d = fullDossier();
    d.ficha_limpa = { ...d.ficha_limpa!, possui_processos_declarados: true, orgaos_declarados: ['STF', 'TSE'] };
    render(<PoliticianHeaderCard dossier={d} onBack={() => {}} onChangeTab={() => {}} />);
    expect(screen.getByText('Ficha/Certidões: Possui Processos Declarados')).toBeInTheDocument();
    expect(screen.getByText('STF, TSE')).toBeInTheDocument();
  });
});

describe('CeapTab', () => {
  it('lista categorias, fornecedores e o gasto por ano', () => {
    render(<CeapTab dossier={fullDossier()} />);
    expect(screen.getByText('120 comprovantes fiscais')).toBeInTheDocument();
    expect(screen.getAllByText('Gráfica Alfa LTDA').length).toBeGreaterThan(0);
    expect(screen.getByText('Gasto da cota por ano')).toBeInTheDocument();
    expect(screen.getByText('2024')).toBeInTheDocument();
    const linha2023 = screen.getByText('2023').closest('tr') as HTMLElement;
    expect(within(linha2023).getByText('R$ 400.000,00')).toBeInTheDocument();
  });

  it('sem dados de CEAP mostra indisponível — nunca "R$ 0,00"', () => {
    render(<CeapTab dossier={sparseDossier()} />);
    expect(screen.getByText('Custos da cota parlamentar indisponíveis')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/R\$ 0,00|0 comprovantes/);
  });

  it('total de notas desconhecido não mostra contador (nunca "0 comprovantes")', () => {
    const d = fullDossier();
    d.custos_ceap.total_notas = null;
    render(<CeapTab dossier={d} />);
    expect(screen.getByText('Gasto da cota por ano')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/comprovantes fiscais/);
  });

  it('total de notas igual a zero é dado válido e aparece', () => {
    const d = fullDossier();
    d.custos_ceap.total_notas = 0;
    render(<CeapTab dossier={d} />);
    expect(screen.getByText('0 comprovantes fiscais')).toBeInTheDocument();
  });

  it('média mensal ausente mostra "Indisponível"', () => {
    const d = fullDossier();
    d.remuneracao.resumo.media_ceap_mensal = null;
    render(<CeapTab dossier={d} />);
    const card = screen.getByText('Média de Gasto Mensal').parentElement as HTMLElement;
    expect(within(card).getByText('Indisponível')).toBeInTheDocument();
  });
});

describe('FinancingTab', () => {
  it('mostra doadores com documento mascarado e filtra a relação de doações', () => {
    render(<FinancingTab dossier={fullDossier()} />);
    expect(screen.getAllByText('Doador Um').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\*\*\*\.456\.789-\*\*/).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain('12345678901');
    fireEvent.change(screen.getByPlaceholderText(/Filtrar por nome/), { target: { value: 'empresa' } });
    expect(screen.getByText('Empresa Dois')).toBeInTheDocument();
    expect(screen.queryAllByRole('cell', { name: 'Doador Um' })).toHaveLength(0); // a linha filtrada sai da tabela
    fireEvent.change(screen.getByPlaceholderText(/Filtrar por nome/), { target: { value: 'zzz' } });
    expect(screen.getByText('Nenhuma doação encontrada para o termo pesquisado.')).toBeInTheDocument();
  });

  it('sem prestação de contas mostra indisponível — nunca "R$ 0,00 arrecadados"', () => {
    render(<FinancingTab dossier={sparseDossier()} />);
    expect(screen.getByText('Financiamento de campanha indisponível')).toBeInTheDocument();
  });
});

describe('AmendmentsTab', () => {
  it('mostra execução e destinos', () => {
    render(<AmendmentsTab dossier={fullDossier()} />);
    expect(screen.getAllByText('Campinas/SP').length).toBeGreaterThan(0);
    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText('1 emendas cadastradas')).toBeInTheDocument();
  });

  it('sem emendas mostra indisponível — nunca "R$ 0,00 pagos"', () => {
    render(<AmendmentsTab dossier={sparseDossier()} />);
    expect(screen.getByText('Emendas parlamentares indisponíveis')).toBeInTheDocument();
  });
});

describe('JusticeTab', () => {
  it('três estados: sem registros, declarado e desconhecido', () => {
    const none = render(<JusticeTab dossier={fullDossier()} />);
    expect(screen.getByText('Nenhum processo declarado na base consultada')).toBeInTheDocument();
    expect(screen.getByText('Não informado')).toBeInTheDocument(); // processo/código ausente
    none.unmount();

    const d = fullDossier();
    d.ficha_limpa = {
      ...d.ficha_limpa!,
      possui_processos_declarados: true,
      orgaos_declarados: ['STF'],
      processos_detalhados: [{ numero_processo: '0001', tribunal: 'STF', data_processo: '2020-01-01', classe_assunto: 'Inquérito', descricao: 'Desc', situacao_juridica: 'Em andamento', link_comprovacao: 'javascript:x', status_resumo: 'x' }],
    };
    const declared = render(<JusticeTab dossier={d} />);
    expect(screen.getByText('Possui Processos Declarados na Justiça')).toBeInTheDocument();
    expect(screen.getByText('Nº 0001')).toBeInTheDocument();
    expect(screen.getByText('1 registro comprovado')).toBeInTheDocument();
    declared.unmount();

    render(<JusticeTab dossier={sparseDossier()} />);
    expect(screen.getByRole('status')).toHaveTextContent('Dado indisponível');
    expect(document.body.textContent).not.toMatch(/Nada Consta|Nenhum processo declarado/);
  });
});

describe('AttendanceTab e RemunerationTab', () => {
  it('assiduidade: valores e amostra de faltas (amostra ≠ total)', () => {
    render(<AttendanceTab dossier={fullDossier()} />);
    expect(screen.getByText('Taxa de Presença: 95,0%')).toBeInTheDocument();
    expect(screen.getByText('Missão oficial')).toBeInTheDocument();
    expect(screen.getByText('Câmara')).toBeInTheDocument();
  });

  it('assiduidade sem sessões: "Dado indisponível" e traços, jamais 100%', () => {
    const d = sparseDossier();
    render(<AttendanceTab dossier={d} />);
    expect(screen.getByText('Taxa de Presença: Dado indisponível')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(3);
    expect(screen.getByText(/A amostra não equivale ao total/)).toBeInTheDocument();
  });

  it('remuneração: formata valores e trata ausência', () => {
    const { unmount } = render(<RemunerationTab dossier={fullDossier()} />);
    expect(screen.getByText('01/2023')).toBeInTheDocument();
    expect(screen.getAllByText('Portal da Transparência').length).toBe(2);
    expect(screen.getByText(/528\.102,24/)).toBeInTheDocument();
    unmount();

    render(<RemunerationTab dossier={sparseDossier()} />);
    expect(screen.getByText('Indisponível')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/R\$\s*<|R\$\s*$/);
  });
});

describe('AttendanceTab e RemunerationTab com dados parciais das fontes oficiais', () => {
  it('assiduidade sem justificativa na fonte: faltas justificadas e não justificadas aparecem como "n/d", com unidade, período e fonte', () => {
    const d = fullDossier();
    d.assiduidade = {
      ...d.assiduidade,
      faltas_justificadas: null,
      faltas_nao_justificadas: null,
      unidade: 'dia com votação nominal em plenário',
      periodo_inicio: '2023-02-01',
      periodo_fim: '2026-09-30',
      fonte: 'Senado Federal — votações nominais de plenário',
    };
    render(<AttendanceTab dossier={d} />);
    expect(screen.getAllByText('n/d')).toHaveLength(2);
    expect(screen.getAllByText('Fonte não informa justificativa neste período')).toHaveLength(2);
    expect(screen.getByText('Unidade: dia com votação nominal em plenário · 2023-02-01 a 2026-09-30')).toBeInTheDocument();
    expect(screen.getByText('Fonte: Senado Federal — votações nominais de plenário')).toBeInTheDocument();
  });

  it('assiduidade da Câmara: faltas não justificadas numéricas e fonte oficial exibida', () => {
    const d = fullDossier();
    d.assiduidade = { ...d.assiduidade, unidade: 'dia com sessão deliberativa', fonte: 'Câmara dos Deputados — Presença em Plenário' };
    render(<AttendanceTab dossier={d} />);
    expect(screen.getByText('Ausências sem protocolo prévio')).toBeInTheDocument();
    expect(screen.queryByText('n/d')).not.toBeInTheDocument();
    expect(screen.getByText('Unidade: dia com sessão deliberativa')).toBeInTheDocument();
    expect(screen.getByText('Fonte: Câmara dos Deputados — Presença em Plenário')).toBeInTheDocument();
  });

  it('cabeçalho: o total de faltas vem da API e as categorias desconhecidas viram "n/d" (nunca soma parcial)', () => {
    const d = fullDossier();
    d.assiduidade = { ...d.assiduidade, faltas_justificadas: null, faltas_nao_justificadas: null, total_faltas: 5 };
    render(<PoliticianHeaderCard dossier={d} onBack={() => {}} onChangeTab={() => {}} />);
    expect(screen.getAllByText('n/d')).toHaveLength(2); // justificadas e não justificadas
    expect(screen.getByText('5')).toBeInTheDocument(); // total de faltas
  });

  it('remuneração: campos que a fonte não informa são "Indisponível", jamais R$ 0,00', () => {
    const d = fullDossier();
    d.remuneracao = {
      ...d.remuneracao,
      historico: [
        { ano: 2025, mes: 3, salario_bruto: 44008.52, salario_liquido: null, cota_ceap: null, auxilio_moradia: null, outros_beneficios: null, fonte: 'Câmara dos Deputados - Portal da Transparência' },
        { ano: 2025, mes: 4, salario_bruto: 44008.52, salario_liquido: 27822.06, cota_ceap: null, auxilio_moradia: null, outros_beneficios: 100, fonte: 'Câmara dos Deputados - Portal da Transparência' },
      ],
    };
    render(<RemunerationTab dossier={d} />);
    const linhaMarco = screen.getByText('03/2025').closest('tr') as HTMLElement;
    expect(within(linhaMarco).getByText(/44\.008,52/)).toBeInTheDocument();
    expect(within(linhaMarco).getAllByText('Indisponível')).toHaveLength(3); // líquido, CEAP, auxílios
    expect(linhaMarco.textContent).not.toMatch(/R\$\s*0,00/);

    const linhaAbril = screen.getByText('04/2025').closest('tr') as HTMLElement;
    expect(within(linhaAbril).getByText(/27\.822,06/)).toBeInTheDocument();
    expect(within(linhaAbril).getByText(/100,00/)).toBeInTheDocument(); // soma parcial dos benefícios informados
    expect(within(linhaAbril).getAllByText('Indisponível')).toHaveLength(1); // só a CEAP
  });
});

describe('VotesTab', () => {
  it('lista votos com rótulos corretos e filtra por texto', () => {
    render(<VotesTab dossier={fullDossier()} />);
    expect(screen.getByText('2 deliberações nominais registradas')).toBeInTheDocument();
    expect(screen.getByText('Sim')).toBeInTheDocument();
    expect(screen.getByText('Obstrução')).toBeInTheDocument();
    expect(screen.queryByText('Ausente')).not.toBeInTheDocument();
    expect(screen.getByText('70,0% a favor')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Pesquisar votos/), { target: { value: 'pec' } });
    expect(screen.queryAllByText('PL 100/2023')).toHaveLength(0);
    expect(screen.getAllByText('PEC 3/2023').length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText(/Pesquisar votos/), { target: { value: 'zzz' } });
    expect(screen.getByText(/Nenhuma deliberação encontrada/)).toBeInTheDocument();
  });

  it('usa o histórico detalhado quando existe e linka só URLs seguras', () => {
    const d = fullDossier();
    d.historico_votos = [
      { proposicao_id: 'x', proposicao_titulo: 'Matéria X', proposicao_numero: 'PL 9/2024', proposicao_tipo: 'PL', tema: 'Saúde', data: '01/01/2024', voto: 'Sim', decisao: 'SIM', sessao_titulo: 'S', sessao_aprovada: true, casa_legislativa: 'SENADO_FEDERAL', url_oficial: 'https://senado.leg.br/x' },
      { proposicao_id: 'y', proposicao_titulo: 'Matéria Y', proposicao_numero: 'PL 10/2024', proposicao_tipo: 'PL', tema: 'Saúde', data: '02/01/2024', voto: 'Não', decisao: 'NAO', sessao_titulo: 'S', sessao_aprovada: true, casa_legislativa: 'SENADO_FEDERAL', url_oficial: 'javascript:alert(1)' },
    ];
    render(<VotesTab dossier={d} />);
    expect(screen.getByText('Matéria X')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Íntegra/ })).toHaveLength(1);
    expect(screen.getAllByText('Senado')).toHaveLength(2);
  });

  it('sem votos mostra mensagem vazia', () => {
    render(<VotesTab dossier={sparseDossier()} />);
    expect(screen.getByText(/Nenhum voto nominal registrado/)).toBeInTheDocument();
  });
});

describe('PropositionsTab', () => {
  it('filtra por relevância e por texto', () => {
    render(<PropositionsTab dossier={fullDossier()} />);
    expect(screen.getAllByText('PL 100/2023').length).toBeGreaterThan(0);
    expect(screen.getAllByText('PL 200/2022').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /^Impacto/ }));
    expect(screen.queryAllByText('PL 200/2022')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: /^Simbólicas/ }));
    expect(screen.getAllByText('PL 200/2022').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /^Todas/ }));
    fireEvent.change(screen.getByPlaceholderText(/Buscar ementa/), { target: { value: 'zzz' } });
    expect(screen.getByText('Nenhuma proposição encontrada para os filtros selecionados.')).toBeInTheDocument();
  });

  it('sem classificação de relevância os contadores mostram "—" e não "0"', () => {
    render(<PropositionsTab dossier={sparseDossier()} />);
    expect(screen.getByRole('button', { name: 'Impacto (—)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Simbólicas (—)' })).toBeInTheDocument();
  });
});
