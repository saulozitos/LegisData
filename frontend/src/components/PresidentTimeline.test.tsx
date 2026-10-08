import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, vi, expect } from 'vitest';
import PresidentTimeline, { getPresidentPhotoUrl } from './PresidentTimeline';
import type { PresidenteHistorico } from '@/services/api';

const president = (over: Partial<PresidenteHistorico>): PresidenteHistorico => ({
  id_referencia: 'fhc-1995',
  nome_civil: 'Fernando Henrique Cardoso',
  nome_eleitoral: 'Fernando Henrique',
  partido_sigla: 'PSDB',
  partido_nome: 'PSDB',
  mandato_numero: 1,
  ano_eleicao: 1994,
  data_inicio: '1995-01-01',
  data_fim: '1998-12-31',
  status_mandato: 'CONCLUIDO',
  ministros_fazenda_chave: [],
  marcos_economicos: [],
  ...over,
});

const presidents = [
  president({}),
  president({ id_referencia: 'dilma-2015', nome_eleitoral: 'Dilma', partido_sigla: 'PT', data_inicio: '2015-01-01', data_fim: '2016-08-31', status_mandato: 'IMPEACHMENT' }),
  president({ id_referencia: 'lula-2023', nome_eleitoral: 'Lula', partido_sigla: 'PT', data_inicio: '2023-01-01', data_fim: null, status_mandato: 'EM_EXERCICIO' }),
];

describe('getPresidentPhotoUrl', () => {
  it('prefere a foto local e mapeia por id de referência', () => {
    expect(getPresidentPhotoUrl('x', '/presidents/a.jpg')).toBe('/presidents/a.jpg');
    expect(getPresidentPhotoUrl('itamar-1992')).toBe('/presidents/itamar-franco.jpg');
    expect(getPresidentPhotoUrl('fhc-1995')).toBe('/presidents/fhc.jpg');
    expect(getPresidentPhotoUrl('lula-2023')).toBe('/presidents/lula.jpg');
    expect(getPresidentPhotoUrl('dilma-2015')).toBe('/presidents/dilma.jpg');
    expect(getPresidentPhotoUrl('temer-2016')).toBe('/presidents/temer.jpg');
    expect(getPresidentPhotoUrl('bolsonaro-2019')).toBe('/presidents/bolsonaro.jpg');
  });

  it('usa a URL informada quando não há mapeamento e undefined sem nada', () => {
    expect(getPresidentPhotoUrl('outro', 'https://x.org/a.jpg')).toBe('https://x.org/a.jpg');
    expect(getPresidentPhotoUrl('outro')).toBeUndefined();
    expect(getPresidentPhotoUrl()).toBeUndefined();
  });
});

describe('PresidentTimeline', () => {
  it('sem seleção mostra visão histórica e o botão do presidente atual', () => {
    render(<PresidentTimeline presidents={presidents} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText(/Visão Histórica Completa/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Presidente Atual \(Lula\)/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ver todos' })).not.toBeInTheDocument();
    expect(screen.getByText('2023 - Em Exercício')).toBeInTheDocument();
    expect(screen.getByText('1995 - 1998')).toBeInTheDocument();
  });

  it('o presidente em exercício é o de status ativo, não o último da lista (impeachment não conta)', () => {
    render(<PresidentTimeline presidents={[presidents[2], presidents[1]]} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByRole('button', { name: /Presidente Atual \(Lula\)/ })).toBeInTheDocument();
    expect(screen.getAllByText('Atual')).toHaveLength(1);
  });

  it('sem presidente ativo cai para o último da lista', () => {
    render(<PresidentTimeline presidents={presidents.slice(0, 2)} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByRole('button', { name: /Presidente Atual \(Dilma\)/ })).toBeInTheDocument();
  });

  it('selecionar um presidente notifica e marca aria-pressed', () => {
    const onSelect = vi.fn();
    const { rerender } = render(<PresidentTimeline presidents={presidents} selectedId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: /Dilma/ }));
    expect(onSelect).toHaveBeenCalledWith('dilma-2015');

    rerender(<PresidentTimeline presidents={presidents} selectedId="dilma-2015" onSelect={onSelect} />);
    expect(screen.getByText('Filtrando: Dilma')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Dilma/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('desmarcar um histórico restaura o atual; desmarcar o atual vai para visão geral', () => {
    const onSelect = vi.fn();
    const { rerender } = render(<PresidentTimeline presidents={presidents} selectedId="dilma-2015" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: /Dilma/, pressed: true }));
    expect(onSelect).toHaveBeenLastCalledWith('lula-2023');

    rerender(<PresidentTimeline presidents={presidents} selectedId="lula-2023" onSelect={onSelect} />);
    expect(screen.getByText('Presidente Atual (Padrão): Lula')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Lula/, pressed: true }));
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it('"Ver todos" e "Visão Geral" limpam o filtro', () => {
    const onSelect = vi.fn();
    render(<PresidentTimeline presidents={presidents} selectedId="fhc-1995" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: 'Ver todos' }));
    fireEvent.click(screen.getByRole('button', { name: /Visão Geral/ }));
    expect(onSelect).toHaveBeenCalledTimes(2);
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it('botão do presidente atual restaura o padrão', () => {
    const onSelect = vi.fn();
    render(<PresidentTimeline presidents={presidents} selectedId="fhc-1995" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: /Presidente Atual \(Lula\)/ }));
    expect(onSelect).toHaveBeenCalledWith('lula-2023');
  });

  it('lista vazia não quebra e o erro de imagem cai para a sigla', () => {
    const { container, rerender } = render(<PresidentTimeline presidents={[]} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText('Visão Geral')).toBeInTheDocument();
    rerender(<PresidentTimeline presidents={[president({ foto_url: 'https://x.org/a.jpg' })]} selectedId={null} onSelect={() => {}} />);
    const img = container.querySelector('img') as HTMLImageElement;
    fireEvent.error(img); // troca para a foto local
    expect(img.src).toContain('/presidents/fhc.jpg');
    fireEvent.error(img); // já local: esconde
    expect(img.style.display).toBe('none');
    expect(screen.getByText('PS')).toBeInTheDocument();
  });
});
