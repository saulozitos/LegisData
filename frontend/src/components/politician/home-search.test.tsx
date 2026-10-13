import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PoliticianHome from './PoliticianHome';
import PoliticianSearchBar from './PoliticianSearchBar';
import * as api from '@/services/api';
import type { PoliticoBuscaItem } from '@/services/api';

vi.mock('@/services/api', () => ({ searchPoliticians: vi.fn(), getParties: vi.fn() }));
const search = api.searchPoliticians as unknown as ReturnType<typeof vi.fn>;
const getParties = api.getParties as unknown as ReturnType<typeof vi.fn>;

const pol = (id: string, nome: string, partido: string, uf: string, cargo = 'DEPUTADO_FEDERAL', foto: string | null = null): PoliticoBuscaItem => ({
  id,
  nome_eleitoral: nome,
  nome_civil: `${nome} Civil`,
  cargo,
  partido_sigla: partido,
  partido_nome: partido,
  uf,
  foto_url: foto,
});

const parties = [
  { id: '1', sigla: 'PT', nome_completo: 'Partido dos Trabalhadores', total_parlamentares: 70, cor_hex: '#f00', ideologia: 'Esquerda democrática', lema: 'Lema PT' },
  { id: '2', sigla: 'PL', nome_completo: 'Partido Liberal', total_parlamentares: 90, cor_hex: '#00f', ideologia: 'Direita', lema: 'Lema PL' },
];

describe('PoliticianHome', () => {
  beforeEach(() => {
    search.mockReset();
    getParties.mockReset();
    getParties.mockResolvedValue(parties);
    search.mockResolvedValue({ politicos: [pol('1', 'Ana', 'PT', 'SP'), pol('2', 'Bia', 'PT', 'RJ', 'SENADOR'), pol('3', 'Caio', 'PL', 'MG', 'DEPUTADO_FEDERAL', 'https://x.org/c.jpg')] });
  });

  it('agrupa por bancada e abre o dossiê ao clicar', async () => {
    const onSelect = vi.fn();
    render(<PoliticianHome onSelectPolitician={onSelect} />);
    expect(screen.getByText('Carregando parlamentares...')).toBeInTheDocument();
    expect(await screen.findByText('Ana')).toBeInTheDocument();
    expect(screen.getByText(/Total exibido:/).textContent).toContain('3');
    expect(search).toHaveBeenCalledWith(undefined, undefined, undefined, undefined, 500, expect.any(AbortSignal));
    fireEvent.click(screen.getByTitle(/Raio-X de Ana/));
    expect(onSelect).toHaveBeenCalledWith('1');
  });

  it('filtra por casa e por partido chamando a API com os parâmetros certos', async () => {
    render(<PoliticianHome onSelectPolitician={() => {}} />);
    await screen.findByText('Ana');
    fireEvent.click(screen.getByRole('button', { name: 'Senadores' }));
    await waitFor(() => expect(search).toHaveBeenLastCalledWith(undefined, 'SENADOR', undefined, undefined, 500, expect.any(AbortSignal)));

    await waitFor(() => expect(within(screen.getByLabelText(/Bancada Partidária/)).getByRole('option', { name: /PL - Partido Liberal/ })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Bancada Partidária/), { target: { value: 'PL' } });
    await waitFor(() => expect(search).toHaveBeenLastCalledWith(undefined, 'SENADOR', 'PL', undefined, 300, expect.any(AbortSignal)));
    expect(await screen.findByText(/Bancada do PL/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Bancada do PL • Partido Liberal');
    expect(screen.getByText('Direita', { selector: 'span' })).toBeInTheDocument();
  });

  it('filtro local por nome/UF e "Limpar Filtros" quando nada confere', async () => {
    render(<PoliticianHome onSelectPolitician={() => {}} />);
    await screen.findByText('Ana');
    fireEvent.change(screen.getByLabelText(/Filtrar Parlamentares/), { target: { value: 'rj' } });
    expect(screen.queryByText('Ana')).not.toBeInTheDocument();
    expect(screen.getByText('Bia')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Filtrar Parlamentares/), { target: { value: 'zzz' } });
    expect(screen.getByText(/Nenhum parlamentar encontrado/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Limpar Filtros da Home' }));
    expect(await screen.findByText('Ana')).toBeInTheDocument();
  });

  it('renderização incremental: mostra 120 por vez com "Mostrar mais"', async () => {
    const many = Array.from({ length: 150 }, (_, i) => pol(`id${i}`, `Parlamentar ${i}`, 'PT', 'SP'));
    search.mockResolvedValue({ politicos: many });
    render(<PoliticianHome onSelectPolitician={() => {}} />);
    await screen.findByText('Parlamentar 0');
    expect(screen.getAllByTitle(/Raio-X de/)).toHaveLength(120);
    fireEvent.click(screen.getByRole('button', { name: /Mostrar mais/ }));
    expect(screen.getAllByTitle(/Raio-X de/)).toHaveLength(150);
  });

  it('erro mostra alerta e retry', async () => {
    search.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce({ politicos: [pol('1', 'Ana', 'PT', 'SP')] });
    render(<PoliticianHome onSelectPolitician={() => {}} />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Ana')).toBeInTheDocument();
  });
});

describe('PoliticianSearchBar', () => {
  const baseProps = {
    searchTerm: '',
    setSearchTerm: () => {},
    officeFilter: 'TODOS',
    setOfficeFilter: () => {},
    searchResults: [pol('1', 'Ana', 'PT', 'SP'), pol('2', 'Bia', 'PL', 'RJ', 'SENADOR', 'javascript:x'), pol('3', 'Pres', 'PT', 'DF', 'PRESIDENTE')],
    isSearching: false,
    onSelect: () => {},
  };

  it('digitar atualiza o termo e abre o combobox com sugestões', () => {
    const setSearchTerm = vi.fn();
    render(<PoliticianSearchBar {...baseProps} setSearchTerm={setSearchTerm} />);
    const input = screen.getByRole('combobox', { name: 'Buscar político pelo nome' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: 'an' } });
    expect(setSearchTerm).toHaveBeenCalledWith('an');
    const list = screen.getByRole('listbox', { name: 'Sugestões de políticos' });
    expect(within(list).getAllByRole('option')).toHaveLength(3);
    expect(input).toHaveAttribute('aria-expanded', 'true');
    expect(within(list).getByText('Senador')).toBeInTheDocument();
    expect(within(list).getByText('Presidente')).toBeInTheDocument();
  });

  it('selecionar uma sugestão notifica e fecha a lista; Esc e clique fora também fecham', () => {
    const onSelect = vi.fn();
    render(<PoliticianSearchBar {...baseProps} onSelect={onSelect} />);
    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.click(screen.getByRole('button', { name: /Ana/ }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: '1' }));
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    fireEvent.focus(input);
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    fireEvent.focus(input);
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('filtros de cargo, consultas rápidas e indicador de busca', () => {
    const setOfficeFilter = vi.fn();
    const setSearchTerm = vi.fn();
    render(<PoliticianSearchBar {...baseProps} isSearching setOfficeFilter={setOfficeFilter} setSearchTerm={setSearchTerm} officeFilter="SENADOR" />);
    expect(screen.getByRole('status')).toHaveTextContent('Buscando...');
    expect(screen.getByRole('button', { name: 'Senadores' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Presidentes' }));
    expect(setOfficeFilter).toHaveBeenCalledWith('PRESIDENTE');
    fireEvent.click(screen.getByRole('button', { name: 'Deputados' }));
    expect(setOfficeFilter).toHaveBeenCalledWith('DEPUTADO_FEDERAL');
    fireEvent.click(screen.getByRole('button', { name: 'Todos' }));
    expect(setOfficeFilter).toHaveBeenCalledWith('TODOS');
    fireEvent.click(screen.getByRole('button', { name: 'Arthur Lira' }));
    expect(setSearchTerm).toHaveBeenCalledWith('Lira');
  });
});
