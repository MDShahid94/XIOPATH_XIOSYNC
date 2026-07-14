import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

/**
 * Renders children into a portal at the root of the document body.
 * This guarantees that `position: fixed` works perfectly relative to the viewport,
 * escaping any parent containers that have `transform`, `filter`, or `perspective` applied.
 */
export default function ModalPortal({ children }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  if (!mounted) return null;

  return createPortal(children, document.body);
}
