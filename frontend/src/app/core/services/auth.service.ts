import { Injectable, signal, inject } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
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

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly TOKEN_KEY = 'modishlog_token';
  private readonly REFRESH_TOKEN_KEY = 'modishlog_refresh_token';

  private readonly _isAuthenticated = signal<boolean>(this.hasStoredToken());

  readonly isAuthenticated = this._isAuthenticated.asReadonly();

  login(credentials: LoginRequest): Observable<AuthTokens> {
    return this.api.post<AuthTokens>('/auth/login', credentials).pipe(
      tap((tokens) => {
        localStorage.setItem(this.TOKEN_KEY, tokens.access_token);
        if (tokens.refresh_token) {
          localStorage.setItem(this.REFRESH_TOKEN_KEY, tokens.refresh_token);
        }
        this._isAuthenticated.set(true);
      }),
    );
  }

  logout(): void {
    const refreshToken = this.getRefreshToken();
    if (refreshToken) {
      // Best-effort server-side revocation; do not block the UI on this
      this.api.post<{ message: string }>('/auth/logout', { refresh_token: refreshToken }).subscribe({
        error: () => {
          // ignore errors -- token will expire naturally
        },
      });
    }
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.REFRESH_TOKEN_KEY);
    this._isAuthenticated.set(false);
    this.router.navigate(['/login']);
  }

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  getRefreshToken(): string | null {
    return localStorage.getItem(this.REFRESH_TOKEN_KEY);
  }

  setToken(token: string): void {
    localStorage.setItem(this.TOKEN_KEY, token);
    this._isAuthenticated.set(true);
  }

  clearTokens(): void {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.REFRESH_TOKEN_KEY);
    this._isAuthenticated.set(false);
  }

  refreshToken(): Observable<AuthTokens> {
    const refreshToken = this.getRefreshToken();
    return this.api.post<AuthTokens>('/auth/refresh', { refresh_token: refreshToken }).pipe(
      tap((tokens) => {
        localStorage.setItem(this.TOKEN_KEY, tokens.access_token);
      }),
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

  private hasStoredToken(): boolean {
    return !!localStorage.getItem(this.TOKEN_KEY);
  }
}
