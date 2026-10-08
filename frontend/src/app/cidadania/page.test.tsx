import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import CidadaniaPage from './page';

vi.mock('@/components/Header', () => ({
  default: () => <div />
}));

vi.mock('@/components/SocialClassesExplainer', () => ({
  default: () => <div />
}));

vi.mock('@/services/api', () => ({
  getCidadaniaData: vi.fn().mockResolvedValue(null)
}));

describe('CidadaniaPage', () => {
  it('renders without crashing', () => {
    render(<CidadaniaPage />);
  });
});
