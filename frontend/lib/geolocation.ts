// A fresh GPS fix can take longer than the browser's usual short default,
// especially indoors or immediately after opening the app on a phone.
const LOCATION_TIMEOUT_MS = 30_000;
// A good phone fix is often around this range indoors. Location remains a
// campus/audit signal; QR plus the spoken code is the classroom proof.
const EARLY_ACCEPT_ACCURACY_METERS = 50;

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

export function getBestFreshPosition(earlyAcceptAccuracyMeters = EARLY_ACCEPT_ACCURACY_METERS): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Geolocation is unavailable"));
      return;
    }
    let best: GeolocationPosition | undefined;
    let lastError: GeolocationPositionError | undefined;
    let settled = false;
    let watchId: number | undefined;
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
      finish(best, lastError ?? (timeoutError as unknown as GeolocationPositionError));
    }, LOCATION_TIMEOUT_MS);
    watchId = navigator.geolocation.watchPosition(
      (position) => {
        if (!best || position.coords.accuracy < best.coords.accuracy) best = position;
        if (position.coords.accuracy <= earlyAcceptAccuracyMeters) finish(position);
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) finish(undefined, error);
        else if (best) finish(best);
        // POSITION_UNAVAILABLE is often temporary while the device obtains a
        // first fix. Keep the watcher alive until the overall timeout.
        else lastError = error;
      },
      { enableHighAccuracy: true, maximumAge: 0, timeout: LOCATION_TIMEOUT_MS },
    );
  });
}
