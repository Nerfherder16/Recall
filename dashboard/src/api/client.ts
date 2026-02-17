const API_BASE = "";

function getHeaders(): HeadersInit {
  const headers: HeadersInit = { "Content-Type": "application/json" };
  const key = localStorage.getItem("recall_api_key");
  if (key) headers["Authorization"] = `Bearer ${key}`;
  return headers;
}

function getAuthHeaders(): HeadersInit {
  const headers: HeadersInit = {};
  const key = localStorage.getItem("recall_api_key");
  if (key) headers["Authorization"] = `Bearer ${key}`;
  return headers;
}

export async function api<T>(
  endpoint: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const opts: RequestInit = { method, headers: getHeaders() };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API_BASE}${endpoint}`, opts);
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function apiUpload<T>(
  endpoint: string,
  formData: FormData,
): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: formData,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}
