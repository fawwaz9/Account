import { get, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";

/**
 * Push notifications on this device: Phase 0 item 5.
 *
 * The server pushes due reminders to every device its owner turned this on
 * for; this file is the browser's half -- permission, the service worker, the
 * subscription -- and nothing here runs until someone presses the button.
 */

export interface PushStatus {
  available: boolean;
  public_key: string | null;
  devices: number;
}

export function pushStatus(userId: string) {
  return get<PushStatus>(endpoints.push.status(userId));
}

/** A test to this device alone: pressed on the laptop, it arrives on the laptop. */
export async function sendTestPush(userId: string) {
  const subscription = await currentSubscription();
  return post<{ sent: number }>(endpoints.push.test(userId), { endpoint: subscription?.endpoint ?? null });
}

/** Whether this browser can do push at all, before asking anything. */
export function pushSupported(): boolean {
  return typeof window !== "undefined"
    && "serviceWorker" in navigator
    && "PushManager" in window
    && "Notification" in window;
}

/**
 * An iPhone or iPad browsing in a tab rather than from the home screen. Apple
 * only allows push for a site added to the home screen, so this needs saying
 * before anything is pressed.
 */
export function needsHomeScreen(): boolean {
  if (typeof navigator === "undefined") return false;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return ios && !standalone;
}

function keyBytes(base64url: string): Uint8Array {
  const padded = (base64url + "===".slice((base64url.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration();
  return (await registration?.pushManager.getSubscription()) ?? null;
}

/** Whether this browser is the one receiving pushes for its signed-in user. */
export async function thisDeviceIsOn(): Promise<boolean> {
  if (!pushSupported()) return false;
  try {
    return (await currentSubscription()) !== null && Notification.permission === "granted";
  } catch {
    return false;
  }
}

export class PermissionRefused extends Error {}

export async function turnOn(userId: string, publicKey: string): Promise<void> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new PermissionRefused("Notifications are blocked for this site");

  const registration = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const subscription = (await registration.pushManager.getSubscription())
    ?? await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(publicKey) as BufferSource,
    });
  await post(endpoints.push.subscriptions(userId), subscription.toJSON());
}

export async function turnOff(userId: string): Promise<void> {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await post(endpoints.push.remove(userId), { endpoint: subscription.endpoint });
  await subscription.unsubscribe();
}

/**
 * On sign-out: stop this browser receiving anything, at once and offline.
 *
 * The browser's own unsubscribe, not a request to the server -- it needs no
 * token and no network, so signing out stays instant. The server learns the
 * next time it tries this device: the push service answers 410 and the row
 * is deleted. Until then nothing can arrive here, which is the point on a
 * shared computer.
 */
export function forgetThisDevice(): void {
  if (!pushSupported()) return;
  currentSubscription()
    .then((subscription) => subscription?.unsubscribe())
    .catch(() => {});
}
