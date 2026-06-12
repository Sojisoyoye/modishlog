import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from '../services/auth.service';

function isJwtExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return typeof payload.exp === 'number' && payload.exp < Date.now() / 1000;
  } catch {
    return true;
  }
}

export const authGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);

  const token = authService.getToken();

  // Fast path: in-memory token present and not expired
  if (token && !isJwtExpired(token)) {
    return true;
  }

  // No in-memory token (e.g. page refresh) — try to restore via HttpOnly cookie.
  return authService.checkSession().pipe(
    map((user) => (user ? true : router.createUrlTree(['/login']))),
    catchError(() => of(router.createUrlTree(['/login']))),
  );
};
