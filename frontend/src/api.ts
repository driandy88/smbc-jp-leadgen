const TOKEN_KEY = "hexline.token";
const BILLING_KEY = "hexline.billing";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function read(key: string, store: Storage = localStorage): string {
  try {
    return store.getItem(key) || "";
  } catch {
    return "";
  }
}

function write(key: string, value: string, store: Storage = localStorage) {
  try {
    if (value) store.setItem(key, value);
    else store.removeItem(key);
  } catch {
    /* storage unavailable: session lasts until reload */
  }
}

let memToken = read(TOKEN_KEY);
let memBilling = read(BILLING_KEY, sessionStorage);

export const session = {
  get token() {
    return memToken;
  },
  set(token: string) {
    memToken = token;
    write(TOKEN_KEY, token);
  },
  clear() {
    memToken = "";
    memBilling = "";
    write(TOKEN_KEY, "");
    write(BILLING_KEY, "", sessionStorage);
  },
  get billing() {
    return memBilling;
  },
  setBilling(token: string) {
    memBilling = token;
    write(BILLING_KEY, token, sessionStorage);
  },
};

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; billing?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (memToken) headers.Authorization = `Bearer ${memToken}`;
  if (opts.billing && memBilling) headers["X-Billing-Token"] = memBilling;
  const res = await fetch(path, {
    method: opts.method || (opts.body !== undefined ? "POST" : "GET"),
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) {
    session.clear();
    window.dispatchEvent(new Event("hexline-logout"));
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export async function download(path: string, filename: string) {
  const res = await fetch(path, { headers: { Authorization: `Bearer ${memToken}` } });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
