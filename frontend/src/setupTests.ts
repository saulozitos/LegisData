import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll, vi } from 'vitest';

// O mock leve de recharts renderiza <defs>/<linearGradient>/<stop> dentro de <div> (jsdom): o React avisa
// que são "tags desconhecidas". É ruído do ambiente de teste, não do app; todo o resto continua visível.
const SVG_IN_DOM_NOISE = /is unrecognized in this browser|is using incorrect casing/;

beforeAll(() => {
  const original = console.error.bind(console);
  vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
    if (typeof args[0] === 'string' && SVG_IN_DOM_NOISE.test(args[0])) return;
    original(...args);
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
