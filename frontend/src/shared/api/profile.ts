import type { Profile, ProfileEnvelope, ProfileInput } from "../types";
import { request } from "./client";

export function getProfile(): Promise<ProfileEnvelope> {
  return request<ProfileEnvelope>("/profile");
}

export function saveProfile(input: ProfileInput): Promise<Profile> {
  return request<Profile>("/profile", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}
