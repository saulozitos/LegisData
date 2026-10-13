import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, vi, expect, beforeEach } from 'vitest';
import PartiesPanel, { PartyLogoBadge } from './PartiesPanel';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({ getParties: vi.fn() }));
const getParties = api.getParties as unknown as ReturnType<typeof vi.fn>;

const party = (over: Record<string, unknown>) => ({
  id: 'p',
  sigla: 'PT',
  nome_completo: 'Partido dos Trabalhadores',
  numero_eleitoral: 13,
  espectro_politico: 'ESQUERDA',
  ideologia: 'Socialismo democrático',
  lema: 'Lema A',
  logo_url: null,
  total_deputados: 68,
  total_senadores: 9,
  total_parlamentares: 77,
  total_filiados_ativos: 1000,
  cor_hex: '#ff0000',
  ...over,
});

const parties = [
  party({ id: '1' }),
  party({ id: '2', sigla: 'PL', nome_completo: 'Partido Liberal', numero_eleitoral: 22, espectro_politico: 'DIREITA', ideologia: 'Conservadorismo', lema: 'Lema B', total_parlamentares: 90 }),
  party({ id: '3', sigla: 'XX', nome_completo: 'Partido Novo', numero_eleitoral: null, espectro_politico: 'OUTRO' }),
];

beforeEach(() => {
  getParties.mockReset();
});

describe('PartiesPanel', () => {
  it('lista os partidos com bancada e espectro', async () => {
    getParties.mockResolvedValue(parties);
    render(<PartiesPanel />);
    expect(screen.getByText('Carregando partidos...')).toBeInTheDocument();
    expect(await screen.findByText('Partido Liberal')).toBeInTheDocument();
    expect(screen.getByText('Total: 90')).toBeInTheDocument();
    expect(screen.getByText('Nº 13')).toBeInTheDocument();
    expect(screen.getAllByText('Esquerda')).toHaveLength(2); // botão de filtro + selo do partido
    expect(screen.getByText('OUTRO')).toBeInTheDocument();
  });

  it('filtra por busca textual e por espectro', async () => {
    getParties.mockResolvedValue(parties);
    render(<PartiesPanel />);
    await screen.findByText('Partido Liberal');

    fireEvent.change(screen.getByLabelText(/Buscar partido/i), { target: { value: 'conservad' } });
    expect(screen.queryByText('Partido dos Trabalhadores')).not.toBeInTheDocument();
    expect(screen.getByText('Partido Liberal')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Buscar partido/i), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Esquerda' }));
    expect(screen.getByRole('button', { name: 'Esquerda' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText('Partido Liberal')).not.toBeInTheDocument();
    expect(screen.getByText('Partido dos Trabalhadores')).toBeInTheDocument();
  });

  it('mostra mensagem quando a busca não encontra nada', async () => {
    getParties.mockResolvedValue(parties);
    render(<PartiesPanel />);
    await screen.findByText('Partido Liberal');
    fireEvent.change(screen.getByLabelText(/Buscar partido/i), { target: { value: 'zzzz' } });
    expect(screen.getByText(/Nenhum partido encontrado/)).toBeInTheDocument();
  });

  it('abre a bancada pelo botão acessível e destaca o partido-alvo', async () => {
    getParties.mockResolvedValue(parties);
    const onSelect = vi.fn();
    render(<PartiesPanel onSelectParty={onSelect} targetParty="pl" />);
    expect(await screen.findByText('Partido Liberal')).toBeInTheDocument();
    // busca inicial vem do partido-alvo
    expect(screen.queryByText('Partido dos Trabalhadores')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ver bancada do PL' }));
    expect(onSelect).toHaveBeenCalledWith('PL');
  });

  it('sincroniza a busca quando o partido-alvo muda', async () => {
    getParties.mockResolvedValue(parties);
    const { rerender } = render(<PartiesPanel targetParty={null} />);
    await screen.findByText('Partido Liberal');
    rerender(<PartiesPanel targetParty="PT" />);
    expect(screen.getByLabelText(/Buscar partido/i)).toHaveValue('PT');
  });

  it('erro mostra alerta e retry recarrega', async () => {
    getParties.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(parties);
    render(<PartiesPanel />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Partido Liberal')).toBeInTheDocument();
  });

  it('catálogo vazio mostra estado indisponível', async () => {
    getParties.mockResolvedValue([]);
    render(<PartiesPanel />);
    expect(await screen.findByText('Catálogo de partidos indisponível')).toBeInTheDocument();
  });
});

describe('PartyLogoBadge', () => {
  it('usa a sigla quando não há logo ou o logo é inseguro', () => {
    const { rerender } = render(<PartyLogoBadge sigla="PT" logoUrl={null} />);
    expect(screen.getByText('PT')).toBeInTheDocument();
    rerender(<PartyLogoBadge sigla="PT" logoUrl="javascript:alert(1)" />);
    expect(screen.getByText('PT')).toBeInTheDocument();
  });

  it('mostra a imagem e cai para a sigla ao falhar', () => {
    render(<PartyLogoBadge sigla="PL" logoUrl="https://x.org/logo.png" size="lg" />);
    const img = screen.getByAltText('Logo PL');
    expect(img).toHaveAttribute('src', 'https://x.org/logo.png');
    fireEvent.error(img);
    expect(screen.getByText('PL')).toBeInTheDocument();
  });

  it('aceita logo local (/caminho)', () => {
    render(<PartyLogoBadge sigla="PL" logoUrl="/logos/pl.png" size="sm" />);
    expect(screen.getByAltText('Logo PL')).toHaveAttribute('src', '/logos/pl.png');
  });
});
