// 集中封装制片助手接口调用，路径和项目 ID 只在调用处出现一次。
import { api } from '../../api/client';

/**
 * 参数：pid 为项目 ID，path 为助手子路径，body 为可选请求体，method 强制指定方法。
 * 返回：接口响应 Promise；无 body 且指定 method 时按该方法请求，DELETE 也支持携带 body。
 */
export const agentApi = (pid, path = '', body, method) =>
  api(`/projects/${pid}/agent${path}`, body, method ? { method } : {});
