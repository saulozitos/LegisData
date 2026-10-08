import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Header from './Header';
import * as api from '@/services/api';
import * as nav from 'next/navigation';

vi.mock('next/navigation', () => ({ usePathname: vi.fn(() => '/') }));
vi.mock('next/link', () => ({
  default: ({ children, href, className, ...rest }: { children: React.ReactNode; href: string; className?: string }) => (
    <a href={href} className={className} {...rest}>{children}</a>
  ),
}));
vi.mock('@/services/api', () => ({ getApiHealth: vi.fn() }));
const getHealth = api.getApiHealth as unknown as ReturnType<typeof vi.fn>;
const usePathname = nav.usePathname as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  getHealth.mockReset();
  usePathname.mockReturnValue('/');
});

describe('Header', () => {
  it('mostra a marca e a navegação principal', async () => {
    getHealth.mockResolvedValue({ status: 'ok' });
    render(<Header />);
    expect(screen.getByText('LegisData')).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Navegação principal' });
    expect(nav).toHaveTextContent('Dashboard');
    expect(nav).toHaveTextContent('Comparador');
    expect(nav).toHaveTextContent('Participe (Votações)');
    await screen.findByText('API Online'); // aguarda o selo assentar (sem atualização fora do act)
  });

  it.each([
    ['/', 'Dashboard'],
    ['/comparador', 'Comparador'],
    ['/cidadania', 'Participe (Votações)'],
  ])('marca %s como página atual (aria-current)', async (path, label) => {
    usePathname.mockReturnValue(path);
    getHealth.mockResolvedValue({ status: 'ok' });
    render(<Header />);
    const current = screen.getAllByRole('link').filter((l) => l.getAttribute('aria-current') === 'page');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent(label);
    await screen.findByText('API Online');
  });

  it('o selo de status reflete a API de verdade: verificando, online, indisponível', async () => {
    getHealth.mockResolvedValueOnce({ status: 'ok' });
    const { unmount } = render(<Header />);
    expect(screen.getByRole('status')).toHaveTextContent('Verificando API...');
    expect(await screen.findByText('API Online')).toBeInTheDocument();
    unmount();

    getHealth.mockRejectedValueOnce(new Error('down'));
    render(<Header />);
    expect(await screen.findByText('API Indisponível')).toBeInTheDocument();
    expect(screen.queryByText('API Online')).not.toBeInTheDocument();
  });

  it('o link externo do GitHub abre com rel seguro', async () => {
    getHealth.mockResolvedValue({ status: 'ok' });
    render(<Header />);
    const link = screen.getByRole('link', { name: /GitHub/ });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    await screen.findByText('API Online');
  });
});
