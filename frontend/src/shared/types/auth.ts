export interface User {
  id: number;
  username: string;
  role: "user" | "admin";
  created_at: string;
}

export interface AuthInput {
  username: string;
  password: string;
}

export const USERNAME_PATTERN = /^[a-zA-Z0-9._-]{3,32}$/;
