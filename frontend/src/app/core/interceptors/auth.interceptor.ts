import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../services/auth.service';

const API_BASE = environment.apiBaseUrl;

function isSameOrigin(url: string): boolean {
  return url.startsWith('/') || url.startsWith(API_BASE);
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  // Only attach credentials (Authorization header + cookies) to same-origin
  // API requests — never to third-party URLs.
  if (!isSameOrigin(req.url)) {
    return next(req);
  }

  const token = authService.getToken();
  const authedReq = req.clone({
    // Send cookies (including the HttpOnly access_token cookie) on every API call.
    withCredentials: true,
    ...(token ? { setHeaders: { Authorization: `Bearer ${token}` } } : {}),
  });

  return next(authedReq).pipe(
    catchError((error: HttpErrorResponse) => {
      // Only attempt silent refresh for 401 errors on non-auth endpoints.
      // Avoid infinite loops by not retrying refresh/login/logout calls.
      const isAuthEndpoint =
        req.url.includes('/auth/refresh') ||
        req.url.includes('/auth/login') ||
        req.url.includes('/auth/logout');

      if (error.status === 401 && !isAuthEndpoint && authService.getRefreshToken()) {
        return authService.refreshToken().pipe(
          switchMap((tokens) => {
            const retried = req.clone({
              withCredentials: true,
              setHeaders: { Authorization: `Bearer ${tokens.access_token}` },
            });
            return next(retried);
          }),
          catchError((refreshError: HttpErrorResponse) => {
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
