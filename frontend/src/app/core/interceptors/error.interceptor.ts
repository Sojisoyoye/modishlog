import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      // 401 handling (silent refresh + redirect) is managed by authInterceptor.
      // This interceptor handles other global HTTP error concerns (logging, etc.).
      if (error.status === 402) {
        // Task #240: the paywall gate blocked a write for a read_only
        // business -- distinct from a generic failure so the user
        // understands *why*, not just that something broke.
        (error as any)['userMessage'] =
          'Your subscription is read-only. This action is unavailable until you renew.';
      } else if (error.status !== 401) {
        (error as any)['userMessage'] = 'Something went wrong. Please try again.';
        if (!environment.production) {
          console.warn('HTTP error:', error.status, error.url);
        }
      }
      return throwError(() => error);
    }),
  );
};
