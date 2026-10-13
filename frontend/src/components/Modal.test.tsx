import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import Modal from './Modal';
import { EmptyState, ErrorState, LoadingState } from './StateViews';

describe('Modal', () => {
  it('não renderiza fechado', () => {
    render(
      <Modal isOpen={false} onClose={() => {}} ariaLabel="x">
        <button>a</button>
      </Modal>
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('expõe role=dialog, aria-modal e foca o primeiro elemento', () => {
    render(
      <Modal isOpen onClose={() => {}} ariaLabel="Detalhes">
        <button>primeiro</button>
        <button>segundo</button>
      </Modal>
    );
    const dialog = screen.getByRole('dialog', { name: 'Detalhes' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByText('primeiro')).toHaveFocus();
  });

  it('usa aria-labelledby quando há titleId', () => {
    render(
      <Modal isOpen onClose={() => {}} titleId="t">
        <h2 id="t">Título</h2>
      </Modal>
    );
    expect(screen.getByRole('dialog', { name: 'Título' })).toBeInTheDocument();
  });

  it('fecha com Esc e clique no fundo, mas não ao clicar no conteúdo', () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal isOpen onClose={onClose} ariaLabel="x">
        <button>conteudo</button>
      </Modal>
    );
    fireEvent.mouseDown(screen.getByText('conteudo'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.mouseDown(container.firstChild as Element);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('mantém o Tab dentro do diálogo (trap de foco)', () => {
    render(
      <Modal isOpen onClose={() => {}} ariaLabel="x">
        <button>um</button>
        <button>dois</button>
      </Modal>
    );
    const um = screen.getByText('um');
    const dois = screen.getByText('dois');
    dois.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(um).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(dois).toHaveFocus();
  });

  it('Tab sem itens focáveis é bloqueado', () => {
    render(
      <Modal isOpen onClose={() => {}} ariaLabel="x">
        <p>só texto</p>
      </Modal>
    );
    const ev = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true, bubbles: true });
    document.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
  });

  it('devolve o foco ao elemento anterior ao fechar', () => {
    const Host = ({ open }: { open: boolean }) => (
      <div>
        <button>abrir</button>
        <Modal isOpen={open} onClose={() => {}} ariaLabel="x">
          <button>dentro</button>
        </Modal>
      </div>
    );
    const { rerender } = render(<Host open={false} />);
    screen.getByText('abrir').focus();
    rerender(<Host open />);
    expect(screen.getByText('dentro')).toHaveFocus();
    rerender(<Host open={false} />);
    expect(screen.getByText('abrir')).toHaveFocus();
  });
});

describe('StateViews', () => {
  it('ErrorState mostra alerta e dispara retry', () => {
    const onRetry = vi.fn();
    render(<ErrorState onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(onRetry).toHaveBeenCalled();
  });

  it('ErrorState sem retry não mostra botão', () => {
    render(<ErrorState title="Falhou" message="msg" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('Falhou')).toBeInTheDocument();
  });

  it('EmptyState e LoadingState têm role=status', () => {
    render(
      <>
        <EmptyState />
        <LoadingState label="Carregando X" />
      </>
    );
    expect(screen.getByText('Dado indisponível')).toBeInTheDocument();
    expect(screen.getByText('Carregando X')).toBeInTheDocument();
    expect(screen.getAllByRole('status')).toHaveLength(2);
  });
});
