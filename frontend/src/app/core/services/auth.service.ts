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
  business_deletion_requested_at?: string | null;
  business_purge_at?: string | null;
  business_name?: string | null;
}

export interface BusinessDeletionResponse {
  message: string;
  purge_at: string | null;
}

export interface RegisterRequest {
  full_name: string;
  email: string;
  password: string;
  business_name: string;
  currency: string;
  timezone: string;
  country?: string;
  state?: string;
  city?: string;
  phone?: string;
  tax_number?: string;
  fiscal_year_start_month: number;
  ndpr_consent: boolean;
}

export interface RegisterResponse {
  message: string;
  user_id: string;
  business_id: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  private static readonly REFRESH_KEY = 'ml_rt';

  private _accessToken: string | null = null;
  // Refresh token is kept in sessionStorage so it survives forced full-page
  // reloads (cross-site staging: SameSite=Lax cookie won't travel, so the
  // interceptor must use the refresh token to re-issue the access token).
  private _refreshToken: string | null =
    typeof sessionStorage !== 'undefined'
      ? sessionStorage.getItem(AuthService.REFRESH_KEY)
      : null;

  private readonly _isAuthenticated = signal<boolean>(false);
  readonly isAuthenticated = this._isAuthenticated.asReadonly();

  private readonly _currentUser = signal<UserProfile | null>(null);
  readonly currentUser = this._currentUser.asReadonly();

  login(credentials: LoginRequest): Observable<AuthTokens> {
    return this.api.post<AuthTokens>('/auth/login', credentials).pipe(
      tap((tokens) => {
        this._accessToken = tokens.access_token;
        this._refreshToken = tokens.refresh_token ?? null;
        if (this._refreshToken) {
          sessionStorage.setItem(AuthService.REFRESH_KEY, this._refreshToken);
        }
        this._isAuthenticated.set(true);
      }),
    );
  }

  register(data: RegisterRequest): Observable<RegisterResponse> {
    // Onboarding no longer establishes a session — the new owner must
    // verify their email before their first login.
    return this.api.post<RegisterResponse>('/auth/onboard', data);
  }

  logout(): void {
    const refreshToken = this._refreshToken;
    sessionStorage.removeItem(AuthService.REFRESH_KEY);
    if (refreshToken) {
      this.api.post<{ message: string }>('/auth/logout', { refresh_token: refreshToken }).subscribe({
        error: () => {},
      });
    } else {
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
    sessionStorage.removeItem(AuthService.REFRESH_KEY);
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
          this._currentUser.set(user);
        }
      }),
      catchError(() => of(null)),
    );
  }

  /** Schedule self-service deletion for the caller's business. Owner only (task #252). */
  closeBusiness(): Observable<BusinessDeletionResponse> {
    return this.api.post<BusinessDeletionResponse>('/auth/business/close', {}).pipe(
      tap((res) => {
        const user = this._currentUser();
        if (user) {
          this._currentUser.set({ ...user, business_purge_at: res.purge_at });
        }
      }),
    );
  }

  /** Cancel a pending self-service business deletion within the grace period. Owner only. */
  cancelBusinessDeletion(): Observable<BusinessDeletionResponse> {
    return this.api.post<BusinessDeletionResponse>('/auth/business/cancel-deletion', {}).pipe(
      tap(() => {
        const user = this._currentUser();
        if (user) {
          this._currentUser.set({ ...user, business_deletion_requested_at: null, business_purge_at: null });
        }
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

  verifyEmail(token: string): Observable<{ message: string }> {
    return this.api.post<{ message: string }>('/auth/verify-email', { token });
  }

  resendVerification(email: string): Observable<{ message: string }> {
    return this.api.post<{ message: string }>('/auth/resend-verification', { email });
  }
}
