import { Injectable, signal, inject } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, map, of, tap } from 'rxjs';
import { ApiService } from './api.service';

interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

interface LoginRequest {
  email: string;
  password: string;
}

interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  role: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  // In-memory only — not persisted to localStorage/sessionStorage.
  // XSS cannot reach this; the HttpOnly cookie is the durable credential.
  private _accessToken: string | null = null;
  private _refreshToken: string | null = null;

  private readonly _isAuthenticated = signal<boolean>(false);
  readonly isAuthenticated = this._isAuthenticated.asReadonly();

  login(credentials: LoginRequest): Observable<AuthTokens> {
    return this.api.post<AuthTokens>('/auth/login', credentials).pipe(
      tap((tokens) => {
        this._accessToken = tokens.access_token;
        this._refreshToken = tokens.refresh_token ?? null;
        this._isAuthenticated.set(true);
      }),
    );
  }

  logout(): void {
    const refreshToken = this._refreshToken;
    if (refreshToken) {
      // Best-effort server-side revocation; do not block the UI on this
      this.api.post<{ message: string }>('/auth/logout', { refresh_token: refreshToken }).subscribe({
        error: () => {
          // ignore errors -- token will expire naturally
        },
      });
    } else {
      // No refresh token in memory; still tell server to clear the cookie
      this.api.post<{ message: string }>('/auth/logout', {}).subscribe({
        error: () => {},
      });
    }
    this._accessToken = null;
    this._refreshToken = null;
    this._isAuthenticated.set(false);
    this.router.navigate(['/login']);
  }

  getToken(): string | null {
    return this._accessToken;
  }

  getRefreshToken(): string | null {
    return this._refreshToken;
  }

  setToken(token: string): void {
    this._accessToken = token;
    this._isAuthenticated.set(true);
  }

  clearTokens(): void {
    this._accessToken = null;
    this._refreshToken = null;
    this._isAuthenticated.set(false);
  }

  refreshToken(): Observable<AuthTokens> {
    return this.api.post<AuthTokens>('/auth/refresh', { refresh_token: this._refreshToken }).pipe(
      tap((tokens) => {
        this._accessToken = tokens.access_token;
      }),
    );
  }

  /** Check if the HttpOnly cookie session is still valid by calling /auth/me. */
  checkSession(): Observable<UserProfile | null> {
    return this.api.get<UserProfile>('/auth/me').pipe(
      tap((user) => {
        if (user) {
          this._isAuthenticated.set(true);
        }
      }),
      catchError(() => of(null)),
    );
  }

  forgotPassword(email: string): Observable<{ message: string }> {
    return this.api.post<{ message: string }>('/auth/forgot-password', { email });
  }

  resetPassword(token: string, newPassword: string): Observable<{ message: string }> {
    return this.api.post<{ message: string }>('/auth/reset-password', {
      token,
      new_password: newPassword,
    });
  }
}
