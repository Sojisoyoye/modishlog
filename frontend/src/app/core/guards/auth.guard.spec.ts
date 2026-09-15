import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { authGuard } from './auth.guard';
import { AuthService } from '../services/auth.service';

describe('authGuard', () => {
  let authService: AuthService;
  let router: Router;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'login', component: class {} as any },
          { path: 'dashboard', component: class {} as any, canActivate: [authGuard] },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
  });

  it('should block when not authenticated', () => {
    // No in-memory token -- the guard falls back to checkSession() (GET
    // /auth/me) to see if an HttpOnly cookie session is still valid.
    const result: any = TestBed.runInInjectionContext(() => authGuard({} as any, {} as any));
    expect(typeof result.subscribe).toBe('function');

    let value: any;
    result.subscribe((v: any) => (value = v));
    const req = httpMock.expectOne((r) => r.url.includes('/auth/me'));
    req.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    expect(value).toBeTruthy();
    expect(value.toString()).toContain('login');
  });

  it('should allow when authenticated with a valid in-memory token', () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600;
    const payload = btoa(JSON.stringify({ exp: futureExp }));
    authService.setToken(`header.${payload}.sig`);

    const result = TestBed.runInInjectionContext(() => authGuard({} as any, {} as any));
    expect(result).toBe(true);
  });
});
