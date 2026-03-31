import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DataTableComponent } from './data-table.component';

describe('DataTableComponent', () => {
  let fixture: ComponentFixture<DataTableComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DataTableComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(DataTableComponent);
    fixture.componentRef.setInput('columns', [
      { key: 'name', header: 'Name' },
      { key: 'qty', header: 'Quantity' },
    ]);
    fixture.componentRef.setInput('data', [
      { name: 'Widget', qty: 10 },
      { name: 'Gadget', qty: 25 },
    ]);
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('renders column headers', () => {
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Name');
    expect(el.textContent).toContain('Quantity');
  });

  it('renders data rows', () => {
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Widget');
    expect(el.textContent).toContain('25');
  });

  it('shows empty message when no data', () => {
    fixture.componentRef.setInput('data', []);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('No data available');
  });
});
