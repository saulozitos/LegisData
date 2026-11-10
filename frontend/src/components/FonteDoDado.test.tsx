import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import FonteDoDado from './FonteDoDado';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({ fetchCobertura: vi.fn() }));
const cobertura = api.fetchCobertura as unknown as ReturnType<typeof vi.fn>;

const item = (painel: string, atualizado_em: string | null) => ({
  painel,
  titulo: painel,
  fonte: 'Câmara e Senado — Dados Abertos',
  situacao: 'COMPLETA',
  periodo_inicio: null,
  periodo_fim: null,
  atualizado_em,
  registros: 1,
  unidade: 'itens',
  nota: '',
});

beforeEach(() => cobertura.mockReset());

describe('FonteDoDado', () => {
  it('mostra a fonte e a data de atualização do painel', async () => {
    cobertura.mockResolvedValue([item('votacoes', '2026-11-10T06:30:00Z')]);
    render(<FonteDoDado painel="votacoes" />);
    expect(await screen.findByTestId('fonte-votacoes')).toHaveTextContent(
      'Fonte: Câmara e Senado — Dados Abertos · atualizado em 10 nov 2026',
    );
  });

  it('sem data de atualização mostra só a fonte', async () => {
    cobertura.mockResolvedValue([item('gastos', null)]);
    render(<FonteDoDado painel="gastos" />);
    expect(await screen.findByTestId('fonte-gastos')).not.toHaveTextContent('atualizado em');
  });

  it('painel inexistente não mostra nada', async () => {
    cobertura.mockResolvedValue([item('gastos', null)]);
    const { container } = render(<FonteDoDado painel="presenca" />);
    await waitFor(() => expect(cobertura).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('lista de cobertura vazia não mostra nada', async () => {
    cobertura.mockResolvedValue([]);
    const { container } = render(<FonteDoDado painel="gastos" />);
    await waitFor(() => expect(cobertura).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
