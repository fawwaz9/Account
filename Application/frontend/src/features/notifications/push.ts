import { get, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";

/** This browser's half of push notifications: permission, service worker and subscription. */

/** Whether the server can push, its public key, and how many devices are on. */
export interface PushStatus {
  /** The server has push keys configured. */
  available: boolean;
  /** VAPID public key for subscribing; null when unavailable. */
  public_key: string | null;
  /** Devices this account has turned notifications on for. */
  devices: number;
}

/** Fetch the user's push status. */
export function pushStatus(userId: string) {
  return get<PushStatus>(endpoints.push.status(userId));
}

/** Send a test push to this device alone. */
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

/** An iPhone or iPad in a browser tab: Apple allows push only from the home screen. */
export function needsHomeScreen(): boolean {
  if (typeof navigator === "undefined") return false;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return ios && !standalone;
}

/** Decode a base64url VAPID key to bytes. */
function keyBytes(base64url: string): Uint8Array {
  const padded = (base64url + "===".slice((base64url.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

/** This browser's push subscription, if any. */
async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration();
  return (await registration?.pushManager.getSubscription()) ?? null;
}

/** Whether this browser is subscribed and allowed to show notifications. */
export async function thisDeviceIsOn(): Promise<boolean> {
  if (!pushSupported()) return false;
  try {
    return (await currentSubscription()) !== null && Notification.permission === "granted";
  } catch {
    return false;
  }
}

/** Thrown when the user blocks notifications. */
export class PermissionRefused extends Error {}

/** Ask permission, register the service worker, subscribe, and register this device. */
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

/** Unregister this device on the server, then unsubscribe the browser. */
export async function turnOff(userId: string): Promise<void> {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await post(endpoints.push.remove(userId), { endpoint: subscription.endpoint });
  await subscription.unsubscribe();
}

/**
 * On sign-out: unsubscribe this browser at once, offline, with no request.
 * The server drops its row when the push service next answers 410.
 */
export function forgetThisDevice(): void {
  if (!pushSupported()) return;
  currentSubscription()
    .then((subscription) => subscription?.unsubscribe())
    .catch(() => {});
}
