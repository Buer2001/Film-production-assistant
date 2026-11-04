// 文件职责：加载拍摄工作区、串行保存、保留失败输入；卸载后的迟到结果不安装到其他页面。
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';

export default function useShooting(pid, onChanged) {
  const [data, setData] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const alive = useRef(true), pending = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  // ref 防止同一帧双击重复提交；失败只显示错误，不清除调用方表单。
  const run = useCallback(async fn => {
    if (pending.current) return false;
    pending.current = true; setBusy(true); setError('');
    try { await fn(); return true; }
    catch (e) { if (alive.current) setError(e.message); return false; }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  }, []);
  const refresh = useCallback(() => run(async () => {
    const value = await api(`/projects/${pid}/shooting`);
    if (alive.current) setData(value);
  }), [pid, run]);
  useEffect(() => { refresh(); }, [refresh]);
  async function save(type, id, value) {
    return run(async () => {
      const result = await api(`/projects/${pid}/shooting/${type}${id ? '/' + id : ''}`,
        { revision: data.revision, [type === 'items' ? 'item' : 'log']: value }, { method: id ? 'PUT' : 'POST' });
      if (alive.current) setData(result);
      // 业务已保存成功；概览刷新失败不能让用户误以为本次写入失败而重复新增。
      onChanged?.().catch(() => {});
    });
  }
  return { data, busy, error, setError, refresh, save };
}
