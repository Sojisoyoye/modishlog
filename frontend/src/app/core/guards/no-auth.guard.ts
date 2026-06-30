import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

function isJwtExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return typeof payload.exp === 'number' && payload.exp < Date.now() / 1000;
  } catch {
    return true;
  }
}

/** Redirects already-authenticated users to /dashboard, allowing others through. */
export const noAuthGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const token = authService.getToken();
  if (token && !isJwtExpired(token)) {
    return router.createUrlTree(['/dashboard']);
  }
  return true;
};
