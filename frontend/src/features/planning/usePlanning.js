// 管理项目日程快照及串行接口操作，防止过期请求回写页面。
import { useEffect, useRef, useState } from 'react';
import { planningApi } from './api';

/**
 * 参数：pid 为当前项目 ID。返回 data、busy、error、setError 和 run。
 * 挂载或项目变化时读取日程；卸载时推进请求序号，使未完成响应失效。
 */
export default function usePlanning(pid) {
  const [data, setData] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const alive = useRef(false), running = useRef(false), sequence = useRef(0);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; sequence.current += 1; };
  }, [pid]);
  /**
   * 调用日程接口并安装最新快照；参数 path/body/method 对应接口路径、载荷和请求方法。
   * 返回结果 Promise；已有请求执行中、请求过期或失败时返回 null，失败消息写入 error。
   */
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
