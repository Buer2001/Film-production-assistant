import React, { useEffect, useRef } from 'react';

/** 原生模态侧栏负责焦点约束和关闭后归位；保存期间不允许关闭，未保存输入由父层保留。 */
export default function TaskDrawer({ title, busy = false, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    ref.current.showModal();
    return () => { previous?.focus?.(); };
  }, []);
  return <dialog ref={ref} className="task-drawer" aria-label={title} onCancel={e => { e.preventDefault(); if (!busy) onClose(); }}>
    <header className="plan-toolbar"><h2>{title}</h2><button type="button" disabled={busy} onClick={onClose}>关闭</button></header>
    {children}
  </dialog>;
}
