import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const token = authService.getToken();

  const authedReq = token
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(authedReq).pipe(
    catchError((error: HttpErrorResponse) => {
      // Only attempt silent refresh for 401 errors on non-auth endpoints.
      // Avoid infinite loops by not retrying refresh/login/logout calls.
      const isAuthEndpoint = req.url.includes('/auth/refresh') ||
        req.url.includes('/auth/login') ||
        req.url.includes('/auth/logout');

      if (error.status === 401 && !isAuthEndpoint && authService.getRefreshToken()) {
        return authService.refreshToken().pipe(
          switchMap((tokens) => {
            // Retry the original request with the new access token
            const retried = req.clone({
              setHeaders: { Authorization: `Bearer ${tokens.access_token}` },
            });
            return next(retried);
          }),
          catchError((refreshError: HttpErrorResponse) => {
            // Refresh also failed -- clear tokens and redirect to login
            authService.clearTokens();
            router.navigate(['/login']);
            return throwError(() => refreshError);
          }),
        );
      }

      return throwError(() => error);
    }),
  );
};
