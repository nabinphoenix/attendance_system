const LOCATION_TIMEOUT_MS = 12_000;
const EARLY_ACCEPT_ACCURACY_METERS = 30;

export type LocationFailureReason = "LOCATION_DENIED" | "LOCATION_TIMEOUT" | "LOCATION_UNAVAILABLE";

export function hasSecureDeviceContext() {
  return typeof window !== "undefined" && window.isSecureContext;
}

export function locationFailureReason(error: unknown): LocationFailureReason {
  if (typeof navigator === "undefined" || !navigator.geolocation) return "LOCATION_UNAVAILABLE";
  const code = (error as GeolocationPositionError | undefined)?.code;
  if (code === 1) return "LOCATION_DENIED";
  if (code === 3) return "LOCATION_TIMEOUT";
  return "LOCATION_UNAVAILABLE";
}

export function getBestFreshPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Geolocation is unavailable"));
      return;
    }
    let best: GeolocationPosition | undefined;
    let settled = false;
    let watchId: number;
    const finish = (position?: GeolocationPosition, error?: GeolocationPositionError) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      if (watchId !== undefined) navigator.geolocation.clearWatch(watchId);
      if (position) resolve(position);
      else reject(error ?? new Error("No fresh location was available"));
    };
    const timer = window.setTimeout(() => {
      const timeoutError = Object.assign(new Error("Location request timed out"), { code: 3 });
      finish(best, timeoutError as unknown as GeolocationPositionError);
    }, LOCATION_TIMEOUT_MS);
    watchId = navigator.geolocation.watchPosition(
      (position) => {
        if (!best || position.coords.accuracy < best.coords.accuracy) best = position;
        if (position.coords.accuracy <= EARLY_ACCEPT_ACCURACY_METERS) finish(position);
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) finish(undefined, error);
        else if (best) finish(best);
        else finish(undefined, error);
      },
      { enableHighAccuracy: true, maximumAge: 0, timeout: LOCATION_TIMEOUT_MS },
    );
  });
}
