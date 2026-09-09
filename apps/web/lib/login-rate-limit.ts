const WINDOW_MS = 10 * 60 * 1000;
const MAX_FAILURES = 10;
const MAX_TRACKED_CLIENTS = 5000;
type FailureWindow = {
  count: number;
  resetAt: number;
};

const failures = new Map<string, FailureWindow>();

export function loginClientKey(headers: Headers): string {
  const address = headers.get("cf-connecting-ip")?.trim();
  return address && address.length <= 64 && /^[0-9a-f:.]+$/i.test(address) ? address : "local";
}

function activeWindow(key: string, now: number): FailureWindow | null {
  const current = failures.get(key);
  if (!current || current.resetAt <= now) {
    failures.delete(key);
    return null;
  }
  return current;
}

export function retryAfterSeconds(key: string, now = Date.now()): number {
  const current = activeWindow(key, now);
  return current && current.count >= MAX_FAILURES
    ? Math.max(1, Math.ceil((current.resetAt - now) / 1000))
    : 0;
}

export function recordLoginFailure(key: string, now = Date.now()): void {
  const current = activeWindow(key, now);
  if (current) {
    current.count += 1;
    return;
  }
  if (failures.size >= MAX_TRACKED_CLIENTS) {
    const oldestKey = failures.keys().next().value;
    if (oldestKey) failures.delete(oldestKey);
  }
  failures.set(key, { count: 1, resetAt: now + WINDOW_MS });
}

export function clearLoginFailures(key: string): void {
  failures.delete(key);
}
