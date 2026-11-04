// 集中封装剧本版本、文件草稿、自定义字段和逐场解析接口地址。
import { api } from '../../api/client';

const root = pid => `/projects/${pid}/script-workspace`;
/**
 * 剧本接口集合：pid 为项目 ID，sid 为剧本版本 ID，revision 为文件编辑版本。
 * 读写方法返回 JSON 响应 Promise；eventsUrl/exportUrl 仅返回 SSE 或下载地址。
 * 解析、重试和恢复携带 revision；确认携带草稿 revision 和人工接受选项，正式 base_revision 由服务端草稿维护。
 */
export const scriptApi = {
  fields: pid => api(`${root(pid)}/fields`),
  saveFields: (pid, data) => api(`${root(pid)}/fields`, data, { method: 'PUT' }),
  list: pid => api(root(pid)),
  get: (pid, sid) => api(`${root(pid)}/${sid}`),
  create: (pid, data) => api(root(pid), data),
  parse: (pid, sid, revision) => api(`${root(pid)}/${sid}/parse`, { revision }),
  eventsUrl: (pid, sid, after = 0) => `/api${root(pid)}/${sid}/events?after=${after}`,
  retry: (pid, sid, sceneId, revision) => api(`${root(pid)}/${sid}/scenes/${sceneId}/retry`, { revision }),
  recover: (pid, sid, revision) => api(`${root(pid)}/${sid}/recover`, { revision }),
  save: (pid, sid, data) => api(`${root(pid)}/${sid}`, data, { method: 'PUT' }),
  confirm: (pid, sid, data) => api(`${root(pid)}/${sid}/confirm`, data),
  exportUrl: (pid, sid) => `/api${root(pid)}/${sid}/export`,
};
