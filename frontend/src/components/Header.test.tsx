import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import Header from './Header';

// Mock do next/navigation e next/link
vi.mock('next/navigation', () => ({
  usePathname: vi.fn(() => '/'),
}));

// Evitar erros no next/link simulando-o como tag anchor comum para testes
vi.mock('next/link', () => ({
  default: ({ children, href, className }: { children: React.ReactNode, href: string, className: string }) => (
    <a href={href} className={className}>{children}</a>
  )
}));

describe('Header component', () => {
  it('renders the branding title', () => {
    render(<Header />);
    expect(screen.getByText('LegisData')).toBeInTheDocument();
  });

  it('renders the navigation links', () => {
    render(<Header />);
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Comparador')).toBeInTheDocument();
    expect(screen.getByText('Participe (Votações)')).toBeInTheDocument();
  });

  it('renders external GitHub link', () => {
    render(<Header />);
  });
});
