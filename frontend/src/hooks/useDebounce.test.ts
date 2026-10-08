import { renderHook, act } from '@testing-library/react';
import { useDebounce } from './useDebounce';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

describe('useDebounce hook', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should return the initial value immediately', () => {
    const { result } = renderHook(() => useDebounce('initial', 500));
    expect(result.current).toBe('initial');
  });

  it('should update the value after the specified delay', () => {
    const { result, rerender } = renderHook(
      ({ value, delay }) => useDebounce(value, delay),
      { initialProps: { value: 'initial', delay: 500 } }
    );

    expect(result.current).toBe('initial');

    // Update the value
    rerender({ value: 'updated', delay: 500 });
    
    // Value should still be 'initial' immediately after update
    expect(result.current).toBe('initial');

    // Fast-forward time by 499ms
    act(() => {
      vi.advanceTimersByTime(499);
    });
    
    // Value should still be 'initial'
    expect(result.current).toBe('initial');

    // Fast-forward time to reach 500ms total
    act(() => {
      vi.advanceTimersByTime(1);
    });

    // Value should now be 'updated'
    expect(result.current).toBe('updated');
  });

  it('should cancel the previous timer if value changes again before delay', () => {
    const { result, rerender } = renderHook(
      ({ value, delay }) => useDebounce(value, delay),
      { initialProps: { value: 'initial', delay: 500 } }
    );

    rerender({ value: 'updated1', delay: 500 });

    act(() => {
      vi.advanceTimersByTime(300);
    });

    rerender({ value: 'updated2', delay: 500 });

    act(() => {
      // 300ms + 300ms = 600ms total from first change
      // But only 300ms since the second change
      vi.advanceTimersByTime(300);
    });

    // Still 'initial' because the 500ms timer restarted on 'updated2'
    expect(result.current).toBe('initial');

    act(() => {
      vi.advanceTimersByTime(200);
    });

    // Now 500ms have passed since 'updated2'
    expect(result.current).toBe('updated2');
  });
});
