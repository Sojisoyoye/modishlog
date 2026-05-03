import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { MessageService } from 'primeng/api';
import { ProductsPageComponent } from './products-page.component';

describe('ProductsPageComponent — executeDeleteCategory()', () => {
  let fixture: ComponentFixture<ProductsPageComponent>;
  let component: ProductsPageComponent;
  let httpMock: HttpTestingController;
  let messageService: MessageService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProductsPageComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        MessageService,
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ProductsPageComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    messageService = TestBed.inject(MessageService);

    // Flush initial data-loading requests so the component stabilises
    fixture.detectChanges();
    httpMock.match(() => true).forEach((r) => r.flush([]));
    fixture.detectChanges();
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('shows warn toast with product count when backend returns 409', () => {
    vi.spyOn(messageService, 'add');

    // Seed a pending-delete category
    component.categoryPendingDelete.set({ id: 'cat-1', name: 'Edge Tape', description: undefined });
    component.executeDeleteCategory();

    const req = httpMock.expectOne((r) => r.url.includes('/products/categories/cat-1'));
    req.flush(
      { detail: 'Category cat-1 has 3 linked products' },
      { status: 409, statusText: 'Conflict' },
    );

    expect(messageService.add).toHaveBeenCalledWith(
      expect.objectContaining({
        severity: 'warn',
        detail: expect.stringContaining('3'),
      }),
    );
    expect(messageService.add).toHaveBeenCalledWith(
      expect.objectContaining({ detail: expect.stringContaining('Edge Tape') }),
    );
  });

  it('shows generic warn toast when 409 detail does not contain a parseable count', () => {
    vi.spyOn(messageService, 'add');

    component.categoryPendingDelete.set({ id: 'cat-2', name: 'Panels', description: undefined });
    component.executeDeleteCategory();

    const req = httpMock.expectOne((r) => r.url.includes('/products/categories/cat-2'));
    req.flush({ detail: 'unexpected error format' }, { status: 409, statusText: 'Conflict' });

    expect(messageService.add).toHaveBeenCalledWith(
      expect.objectContaining({ severity: 'warn' }),
    );
    // Still names the category
    expect(messageService.add).toHaveBeenCalledWith(
      expect.objectContaining({ detail: expect.stringContaining('Panels') }),
    );
  });

  it('shows error toast for non-409 failures', () => {
    vi.spyOn(messageService, 'add');

    component.categoryPendingDelete.set({ id: 'cat-3', name: 'Wood', description: undefined });
    component.executeDeleteCategory();

    const req = httpMock.expectOne((r) => r.url.includes('/products/categories/cat-3'));
    req.flush('Server error', { status: 500, statusText: 'Internal Server Error' });

    expect(messageService.add).toHaveBeenCalledWith(
      expect.objectContaining({ severity: 'error' }),
    );
  });
});
