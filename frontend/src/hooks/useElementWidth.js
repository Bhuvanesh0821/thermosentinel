import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Measured content width of an element (charts lay out in real pixels, never stretched).
 * Returns a callback ref, so elements that mount later are still observed.
 */
export function useElementWidth() {
  const [width, setWidth] = useState(0);
  const observer = useRef(null);

  const ref = useCallback((node) => {
    observer.current?.disconnect();
    observer.current = null;
    if (node) {
      // Measure immediately (ResizeObserver callbacks only arrive with rendering frames).
      setWidth(Math.floor(node.getBoundingClientRect().width));
      const ro = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
      ro.observe(node);
      observer.current = ro;
    }
  }, []);

  useEffect(() => () => observer.current?.disconnect(), []);
  return [ref, width];
}
