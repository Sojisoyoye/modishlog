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

      // /auth/me is how public pages (e.g. the landing page) quietly probe
      // "am I logged in?" via AuthService.checkSession() -- its own 401
      // must never force-navigate the visitor away from whatever public
      // page they're on. It still goes through the normal silent-refresh
      // attempt below (so a reload with an expired access token but a
      // valid refresh token still transparently restores the session, same
      // as any other call) -- only the "give up and redirect" paths are
      // skipped for it.
      const isSessionProbe = req.url.includes('/auth/me');

      if (error.status === 401 && !isAuthEndpoint) {
        if (authService.getRefreshToken()) {
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
              if (!isSessionProbe) {
                router.navigate(['/login']);
              }
              return throwError(() => refreshError);
            }),
          );
        }
        // No refresh token (e.g. after page reload with an expired cookie) —
        // session is unrecoverable; send the user to login.
        authService.clearTokens();
        if (!isSessionProbe) {
          router.navigate(['/login']);
        }
      }

      return throwError(() => error);
    }),
  );
};
