import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import PartiesPanel from './PartiesPanel';

vi.mock('@/services/api', () => ({
  getPartiesRanking: vi.fn().mockResolvedValue([])
}));

describe('PartiesPanel', () => {
  it('renders without crashing', () => {
    render(<PartiesPanel onSelectParty={() => {}} />);
  });
});
