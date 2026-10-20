import type { AuthInput, User } from "../types";
import { request } from "./client";

export function getMe(): Promise<User> {
  return request<User>("/auth/me");
}

export function login(input: AuthInput): Promise<User> {
  return request<User>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function register(input: AuthInput): Promise<User> {
  return request<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" });
}
