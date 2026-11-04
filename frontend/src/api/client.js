// 统一封装 JSON 接口调用，向页面传递可读错误及请求编号。
/**
 * 调用相对 /api 的接口。参数：path 为业务路径，body 为可选 JSON 数据，options 为 fetch 选项。
 * 返回：解析后的响应对象 Promise；HTTP 失败时抛出包含服务端 detail 的 Error。
 * 有 body 时默认 POST，并合并 JSON 请求头；无 body 时保留 fetch 默认请求方式。
 */
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
