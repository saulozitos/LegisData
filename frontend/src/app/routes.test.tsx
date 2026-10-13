import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import RouteError from './error';
import GlobalError from './global-error';
import NotFound from './not-found';
import Loading from './loading';

vi.mock('@/components/Header', () => ({ default: () => <div data-testid="Header" /> }));
vi.mock('next/link', () => ({ default: ({ children, href, className }: { children: React.ReactNode; href: string; className?: string }) => <a href={href} className={className}>{children}</a> }));

describe('error.tsx', () => {
  it('mostra alerta, registra o erro e tenta de novo pelo retry', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const retry = vi.fn();
    const error = Object.assign(new Error('falhou'), { digest: 'abc' });
    render(<RouteError error={error} retry={retry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Algo deu errado');
    expect(spy).toHaveBeenCalledWith(error);
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(retry).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });
});

describe('global-error.tsx', () => {
  it('renderiza o documento completo com alerta e retry', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const retry = vi.fn();
    // <html> dentro do container de teste gera aviso de aninhamento; é esperado para o global-error.
    const { container } = render(<GlobalError error={new Error('x')} retry={retry} />, { container: document.documentElement });
    expect(container.querySelector('[role="alert"]')).toHaveTextContent('erro inesperado');
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(retry).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });
});

describe('not-found.tsx', () => {
  it('informa que a página não existe e oferece voltar ao painel', () => {
    render(<NotFound />);
    expect(screen.getByRole('heading', { level: 1, name: 'Página não encontrada' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Voltar ao painel' })).toHaveAttribute('href', '/');
    expect(screen.getByTestId('Header')).toBeInTheDocument();
  });
});

describe('loading.tsx', () => {
  it('mostra o esqueleto de carregamento', () => {
    const { container } = render(<Loading />);
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });
});
