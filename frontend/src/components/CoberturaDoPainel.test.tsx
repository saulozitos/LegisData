import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CoberturaDoPainel, { CoberturaView } from './CoberturaDoPainel';
import type { CoberturaPainel } from '@/services/api';

const votacoes: CoberturaPainel = {
  painel: 'votacoes',
  titulo: 'Votações nominais',
  fonte: 'Dados Abertos da Câmara dos Deputados e do Senado Federal',
  periodo_inicio: '2019-02-12',
  periodo_fim: '2026-10-14',
  registros: 3567,
  unidade: 'votações',
  atualizado_em: '2026-11-09T08:57:14+00:00',
  situacao: 'PARCIAL',
  nota: 'Base parcial: tem dados de votações nominais a partir de 2019.',
};

vi.mock('@/services/api', () => ({
  fetchCobertura: vi.fn(async () => [votacoes]),
}));

describe('CoberturaDoPainel', () => {
  it('mostra fonte, período, última atualização e que a base é parcial', async () => {
    render(<CoberturaView cobertura={votacoes} />);
    expect(screen.getByText('Base parcial')).toBeInTheDocument();
    expect(screen.getByText(/Dados Abertos da Câmara/)).toBeInTheDocument();
    expect(screen.getByText('12 fev 2019 a 14 out 2026')).toBeInTheDocument();
    expect(screen.getByText('9 nov 2026')).toBeInTheDocument();
    expect(screen.getByText(/3\.567 votações cadastrados/)).toBeInTheDocument();
  });

  it('busca a cobertura e mostra a do painel pedido', async () => {
    render(<CoberturaDoPainel painel="votacoes" />);
    expect(await screen.findByLabelText('Cobertura dos dados: Votações nominais')).toBeInTheDocument();
  });

  it('não mostra nada para um painel sem cobertura registrada', async () => {
    const { container } = render(<CoberturaDoPainel painel="inexistente" />);
    await new Promise((r) => setTimeout(r, 20));
    expect(container).toBeEmptyDOMElement();
  });
});
