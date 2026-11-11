import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Page, { linhasDaComparacao } from './page';
import * as api from '@/services/api';
import { fullDossier, sparseDossier } from '@/test/dossier';

let parametrosDaUrl = new URLSearchParams('');
vi.mock('next/navigation', () => ({ useSearchParams: () => parametrosDaUrl }));
vi.mock('@/components/Header', () => ({ default: () => <div data-testid="mock-header" /> }));
vi.mock('@/services/api', () => ({
  getPoliticianDossier: vi.fn(),
  searchPoliticians: vi.fn(),
}));
const dossie = api.getPoliticianDossier as unknown as ReturnType<typeof vi.fn>;
const busca = api.searchPoliticians as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  dossie.mockReset();
  busca.mockReset();
  parametrosDaUrl = new URLSearchParams('');
  window.history.replaceState(null, '', '/comparar-politicos');
});

describe('Comparar parlamentares', () => {
  it('sem seleção pede ao menos dois e não chama o dossiê', () => {
    render(<Page />);
    expect(screen.getByText(/Escolha ao menos dois/)).toBeInTheDocument();
    expect(dossie).not.toHaveBeenCalled();
  });

  it('busca pelo nome, adiciona e remove, e mantém os ids na URL', async () => {
    busca.mockResolvedValue({
      total: 1,
      limit: 8,
      offset: 0,
      politicos: [{ id: 'p1', nome_eleitoral: 'Fulano', nome_civil: 'Fulano', cargo: 'DEPUTADO_FEDERAL', partido_sigla: 'PT', partido_nome: 'PT', uf: 'SP', foto_url: null }],
    });
    dossie.mockResolvedValue(fullDossier());
    render(<Page />);
    fireEvent.change(screen.getByLabelText(/Adicionar parlamentar/), { target: { value: 'Ful' } });
    fireEvent.click(await screen.findByText('Fulano', { exact: false }, { timeout: 2000 }));
    await waitFor(() => expect(dossie).toHaveBeenCalledWith('p1', expect.anything()));
    expect(window.location.search).toBe('?ids=p1');
    fireEvent.click(await screen.findByRole('button', { name: /Remover .* da comparação/ }));
    await waitFor(() => expect(window.location.search).toBe(''));
  });

  it('abre direto pelo link com ids e limita a 5', async () => {
    dossie.mockResolvedValue(fullDossier());
    parametrosDaUrl = new URLSearchParams('ids=a,b,c,d,e,f,g');
    render(<Page />);
    await waitFor(() => expect(dossie).toHaveBeenCalledTimes(5));
  });

  it('dado ausente aparece como indisponível, nunca como zero', () => {
    const linhas = Object.fromEntries(linhasDaComparacao(sparseDossier()));
    expect(linhas['Presença nas sessões']).toBe('indisponível');
    expect(linhas['Alinhamento ao Governo']).toMatch(/sem índice/);
    expect(linhas['Votos registrados']).toBe('indisponível');
  });

  it('falha ao carregar uma coluna mostra o erro com nova tentativa', async () => {
    dossie.mockRejectedValue(new Error('falhou'));
    parametrosDaUrl = new URLSearchParams('ids=x');
    render(<Page />);
    expect((await screen.findAllByText(/Não foi possível carregar/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /tentar/i })).toBeInTheDocument();
  });
});
