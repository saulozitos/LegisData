import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import LoadingSkeleton from './LoadingSkeleton';

describe('LoadingSkeleton component', () => {
  it('renders correctly', () => {
    const { container } = render(<LoadingSkeleton />);
    
    // Testa se o componente renderizou verificando as classes de skeleton
    const skeletonElements = container.querySelectorAll('.animate-pulse');
    expect(skeletonElements.length).toBeGreaterThan(0);
    
    // KPI Cards: deve renderizar 4 cards de KPI (filhos do grid)
    // Procuramos o grid e verificamos os filhos
    const grids = container.querySelectorAll('.grid');
    expect(grids.length).toBe(1);
    expect(grids[0].children.length).toBe(4);
  });
});
