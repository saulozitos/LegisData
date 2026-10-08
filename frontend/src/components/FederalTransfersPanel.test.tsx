import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import FederalTransfersPanel from './FederalTransfersPanel';

vi.mock('@/services/api', () => ({
  getFederalTransfers: vi.fn().mockResolvedValue([])
}));

describe('FederalTransfersPanel', () => {
  it('renders without crashing', () => {
    render(<FederalTransfersPanel mandateId="bolsonaro-2019" regionFilter="TODAS" areaFilter="TODAS" searchTerm="" />);
  });
});
