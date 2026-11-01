import { api } from '../../api/client';

const root = pid => `/projects/${pid}/script-workspace`;
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
