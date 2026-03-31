import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MetricCardComponent } from './metric-card.component';

describe('MetricCardComponent', () => {
  let fixture: ComponentFixture<MetricCardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MetricCardComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(MetricCardComponent);
    fixture.componentRef.setInput('title', 'Revenue');
    fixture.componentRef.setInput('value', '$10,000');
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('displays title and value', () => {
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Revenue');
    expect(el.textContent).toContain('$10,000');
  });

  it('shows up arrow for up trend', () => {
    fixture.componentRef.setInput('trend', 'up');
    fixture.componentRef.setInput('trendLabel', '+5%');
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('+5%');
  });

  it('applies danger border for danger severity', () => {
    fixture.componentRef.setInput('severity', 'danger');
    fixture.detectChanges();
    expect(fixture.componentInstance.borderClass()).toContain('danger');
  });
});
