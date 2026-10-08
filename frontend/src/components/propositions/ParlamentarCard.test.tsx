import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ParlamentarCard from './ParlamentarCard';

const parl = { politico_id: 'p1', foto_url: 'https://x.org/a.jpg', nome_eleitoral: 'Ana Silva', partido_sigla: 'PT', uf: 'SP' };

describe('ParlamentarCard', () => {
  it('sem callbacks é apenas informativo (sem botões)', () => {
    render(<ParlamentarCard parl={parl} borderColor="border-x" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('Ana Silva')).toBeInTheDocument();
    expect(screen.getByText('PT')).toBeInTheDocument();
    expect(screen.getByText('SP')).toBeInTheDocument();
  });

  it('fecha o modal e abre o Raio-X ao clicar no nome', () => {
    const order: string[] = [];
    const onSelectPolitician = vi.fn(() => order.push('select'));
    const onCloseModal = vi.fn(() => order.push('close'));
    render(<ParlamentarCard parl={parl} borderColor="b" onSelectPolitician={onSelectPolitician} onCloseModal={onCloseModal} />);
    fireEvent.click(screen.getByRole('button', { name: 'Ana Silva' }));
    expect(onSelectPolitician).toHaveBeenCalledWith('p1');
    expect(order).toEqual(['close', 'select']);
  });

  it('sem politico_id o nome não é clicável mesmo com callback', () => {
    render(<ParlamentarCard parl={{ ...parl, politico_id: '' }} borderColor="b" onSelectPolitician={() => {}} />);
    expect(screen.queryByRole('button', { name: 'Ana Silva' })).not.toBeInTheDocument();
  });

  it('a sigla do partido fecha o modal e notifica', () => {
    const onSelectParty = vi.fn();
    const onCloseModal = vi.fn();
    render(<ParlamentarCard parl={parl} borderColor="b" onSelectParty={onSelectParty} onCloseModal={onCloseModal} />);
    fireEvent.click(screen.getByRole('button', { name: 'PT' }));
    expect(onCloseModal).toHaveBeenCalledTimes(1);
    expect(onSelectParty).toHaveBeenCalledWith('PT');
  });

  it('usa iniciais quando a foto é ausente ou insegura e esconde a imagem quebrada', () => {
    const { container, rerender } = render(<ParlamentarCard parl={{ ...parl, foto_url: 'javascript:alert(1)' }} borderColor="b" />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('AN')).toBeInTheDocument();

    rerender(<ParlamentarCard parl={{ ...parl, foto_url: null }} borderColor="b" />);
    expect(screen.getByText('AN')).toBeInTheDocument();

    rerender(<ParlamentarCard parl={parl} borderColor="b" />);
    const img = container.querySelector('img') as HTMLImageElement;
    expect(img).toHaveAttribute('src', 'https://x.org/a.jpg');
    fireEvent.error(img);
    expect(img.style.display).toBe('none');
  });
});
