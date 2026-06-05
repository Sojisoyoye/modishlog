import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      // 401 handling (silent refresh + redirect) is managed by authInterceptor.
      // This interceptor handles other global HTTP error concerns (logging, etc.).
      return throwError(() => error);
    }),
  );
};
