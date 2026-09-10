export const SESSION_COOKIE = "sbdc_session";
export const SESSION_TTL_SECONDS = 12 * 60 * 60;

export type AuthConfig = {
  username: string;
  password: string;
  sessionSecret: string;
};

type SessionPayload = {
  version: 1;
  subject: string;
  expiresAt: number;
};

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function getAuthConfig(): AuthConfig | null {
  const username = process.env.SBDC_ADMIN_USERNAME?.trim();
  const password = process.env.SBDC_ADMIN_PASSWORD;
  const sessionSecret = process.env.SBDC_SESSION_SECRET;
  if (!username || !password || password.length < 16 || !sessionSecret || sessionSecret.length < 32) return null;
  return { username, password, sessionSecret };
}

function encodeBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function decodeBase64Url(value: string): Uint8Array<ArrayBuffer> | null {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) return null;
  try {
    const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  } catch {
    return null;
  }
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

async function secureEqual(candidate: string, expected: string, secret: string): Promise<boolean> {
  const key = await hmacKey(secret);
  const expectedTag = await crypto.subtle.sign("HMAC", key, encoder.encode(expected));
  return crypto.subtle.verify("HMAC", key, expectedTag, encoder.encode(candidate));
}

export async function verifyCredentials(
  username: string,
  password: string,
  config: AuthConfig,
): Promise<boolean> {
  if (username.length > 256 || password.length > 1024) return false;
  const [usernameMatches, passwordMatches] = await Promise.all([
    secureEqual(username, config.username, config.sessionSecret),
    secureEqual(password, config.password, config.sessionSecret),
  ]);
  return usernameMatches && passwordMatches;
}

export async function createSessionToken(
  config: AuthConfig,
  now = Date.now(),
): Promise<string> {
  const payload: SessionPayload = {
    version: 1,
    subject: config.username,
    expiresAt: Math.floor(now / 1000) + SESSION_TTL_SECONDS,
  };
  const encodedPayload = encodeBase64Url(encoder.encode(JSON.stringify(payload)));
  const key = await hmacKey(config.sessionSecret);
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(encodedPayload));
  return `${encodedPayload}.${encodeBase64Url(new Uint8Array(signature))}`;
}

export async function verifySessionToken(
  token: string | undefined,
  config: AuthConfig,
  now = Date.now(),
): Promise<boolean> {
  if (!token || token.length > 2048) return false;
  const parts = token.split(".");
  if (parts.length !== 2) return false;
  const [encodedPayload, encodedSignature] = parts;
  const payloadBytes = decodeBase64Url(encodedPayload);
  const signature = decodeBase64Url(encodedSignature);
  if (!payloadBytes || !signature) return false;

  const key = await hmacKey(config.sessionSecret);
  const signatureMatches = await crypto.subtle.verify(
    "HMAC",
    key,
    signature,
    encoder.encode(encodedPayload),
  );
  if (!signatureMatches) return false;

  try {
    const payload = JSON.parse(decoder.decode(payloadBytes)) as Partial<SessionPayload>;
    return payload.version === 1
      && payload.subject === config.username
      && Number.isInteger(payload.expiresAt)
      && Number(payload.expiresAt) > Math.floor(now / 1000);
  } catch {
    return false;
  }
}

export function safeNextPath(value: FormDataEntryValue | string | null | undefined): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return "/workbench";
  try {
    const resolved = new URL(value, "https://sbdc.local");
    if (resolved.origin !== "https://sbdc.local") return "/workbench";
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return "/workbench";
  }
}
