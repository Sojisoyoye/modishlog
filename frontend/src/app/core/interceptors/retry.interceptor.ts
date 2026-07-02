import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { throwError, timer } from 'rxjs';
import { catchError, retry, switchMap } from 'rxjs/operators';

const MAX_RETRIES = 3;
const BACKOFF_MS = [1000, 2000, 4000];

function isRetryable(error: HttpErrorResponse): boolean {
  return error.status === 0 || error.status === 503 || error.status === 502;
}

export const retryInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    retry({
      count: MAX_RETRIES,
      delay: (error: unknown, attempt: number) => {
        if (error instanceof HttpErrorResponse && isRetryable(error)) {
          return timer(BACKOFF_MS[attempt - 1] ?? 4000);
        }
        return throwError(() => error);
      },
    }),
    catchError((error: unknown) => throwError(() => error)),
  );
