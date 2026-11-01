import { useEffect, useRef, useState } from 'react';
import { planningApi } from './api';

export default function usePlanning(pid) {
  const [data, setData] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const alive = useRef(false), running = useRef(false), sequence = useRef(0);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; sequence.current += 1; };
  }, [pid]);
  async function run(path = '', body, method) {
    if (running.current) return null;
    running.current = true;
    const token = ++sequence.current;
    setBusy(true); setError('');
    try {
      const result = await planningApi(pid, path, body, method);
      if (!alive.current || token !== sequence.current) return null;
      setData(result); return result;
    } catch (e) {
      if (alive.current && token === sequence.current) setError(e.message);
      return null;
    } finally {
      running.current = false;
      if (alive.current && token === sequence.current) setBusy(false);
    }
  }
  useEffect(() => { run(); }, [pid]);
  return { data, busy, error, setError, run };
}
