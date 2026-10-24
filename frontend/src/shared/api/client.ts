import type { Profile } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly current?: Profile | null;

  constructor(
    message: string,
    status: number,
    code?: string,
    current?: Profile | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.current = current;
  }
}

const FALLBACK_MESSAGE = "Something went wrong. Please try again.";

function readError(payload: unknown): {
  message: string;
  code?: string;
  current?: Profile | null;
} {
  if (!payload || typeof payload !== "object") {
    return { message: FALLBACK_MESSAGE };
  }

  const detail = (payload as { detail?: unknown }).detail;

  if (typeof detail === "string") {
    return { message: detail };
  }

  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    return { message: first?.msg ?? FALLBACK_MESSAGE };
  }

  if (detail && typeof detail === "object") {
    const parsed = detail as {
      code?: string;
      message?: string;
      current?: Profile | null;
    };
    return {
      message: parsed.message ?? FALLBACK_MESSAGE,
      code: parsed.code,
      current: parsed.current ?? null,
    };
  }

  return { message: FALLBACK_MESSAGE };
}

export async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
    headers,
  });

  const text = await response.text();
  let payload: unknown = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const info = readError(payload);
    throw new ApiError(
      info.message,
      response.status,
      info.code,
      info.current,
    );
  }

  return payload as T;
}
