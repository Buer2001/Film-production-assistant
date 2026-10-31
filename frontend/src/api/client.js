export async function api(path, body, options = {}) {
  const response = await fetch('/api' + path, {
    ...options,
    ...(body === undefined ? {} : {
      method: options.method || 'POST', headers: { 'Content-Type': 'application/json', ...options.headers },
      body: JSON.stringify(body),
    }),
  });
  const result = await response.json();
  if (!response.ok) {
    const message = typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail);
    const requestId = response.headers.get('x-request-id');
    throw new Error(requestId ? `${message}（请求编号：${requestId}）` : message);
  }
  return result;
}
