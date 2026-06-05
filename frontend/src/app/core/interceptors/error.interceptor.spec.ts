import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import {
  provideHttpClient,
  withInterceptors,
  HttpClient,
  HttpErrorResponse,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { errorInterceptor } from './error.interceptor';

describe('errorInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('propagates 401 errors (silent refresh is handled by authInterceptor)', () => {
    let receivedError: HttpErrorResponse | null = null;
    http.get('/api/test').subscribe({
      error: (err) => (receivedError = err),
    });
    const req = httpMock.expectOne('/api/test');
    req.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    expect(receivedError).toBeTruthy();
    expect(receivedError!.status).toBe(401);
  });

  it('passes through non-401 errors', () => {
    let receivedError: HttpErrorResponse | null = null;
    http.get('/api/test').subscribe({
      error: (err) => (receivedError = err),
    });
    const req = httpMock.expectOne('/api/test');
    req.flush('Server Error', { status: 500, statusText: 'Internal Server Error' });

    expect(receivedError).toBeTruthy();
    expect(receivedError!.status).toBe(500);
  });
});
