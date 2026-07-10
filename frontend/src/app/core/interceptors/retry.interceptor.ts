import { HttpContextToken, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { throwError, timer } from 'rxjs';
import { catchError, retry, switchMap } from 'rxjs/operators';

const MAX_RETRIES = 3;
const BACKOFF_MS = [1000, 2000, 4000];

/**
 * Set to true on a request's HttpContext to opt out of automatic retries —
 * for calls that aren't safely re-playable (e.g. they mutate state and
 * aren't idempotent), where a lost response + blind retry could resubmit
 * a request whose first attempt actually already succeeded.
 */
export const NO_RETRY = new HttpContextToken<boolean>(() => false);

function isRetryable(error: HttpErrorResponse): boolean {
  return error.status === 0 || error.status === 503 || error.status === 502;
}

export const retryInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    retry({
      count: MAX_RETRIES,
      delay: (error: unknown, attempt: number) => {
        if (!req.context.get(NO_RETRY) && error instanceof HttpErrorResponse && isRetryable(error)) {
          return timer(BACKOFF_MS[attempt - 1] ?? 4000);
        }
        return throwError(() => error);
      },
    }),
    catchError((error: unknown) => throwError(() => error)),
  );
