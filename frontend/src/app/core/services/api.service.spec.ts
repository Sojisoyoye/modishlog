import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ApiService } from './api.service';

describe('ApiService', () => {
  let service: ApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('get makes GET request to baseUrl + path', () => {
    service.get('/test').subscribe();
    const req = httpMock.expectOne((r) => r.url.includes('/test') && r.method === 'GET');
    req.flush({ data: 'ok' });
  });

  it('get passes query params', () => {
    service.get('/test', { foo: 'bar' }).subscribe();
    const req = httpMock.expectOne((r) => r.url.includes('/test') && r.params.get('foo') === 'bar');
    req.flush({});
  });

  it('post makes POST request', () => {
    service.post('/test', { key: 'val' }).subscribe();
    const req = httpMock.expectOne((r) => r.url.includes('/test') && r.method === 'POST');
    expect(req.request.body).toEqual({ key: 'val' });
    req.flush({});
  });

  it('put makes PUT request', () => {
    service.put('/test', { key: 'val' }).subscribe();
    const req = httpMock.expectOne((r) => r.url.includes('/test') && r.method === 'PUT');
    req.flush({});
  });

  it('delete makes DELETE request', () => {
    service.delete('/test').subscribe();
    const req = httpMock.expectOne((r) => r.url.includes('/test') && r.method === 'DELETE');
    req.flush({});
  });
});
