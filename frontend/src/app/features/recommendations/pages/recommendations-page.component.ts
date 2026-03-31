import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, DecimalPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import {
  RecommendationsService,
  Recommendation,
  ImpactSummary,
} from '../../../core/services/recommendations.service';

@Component({
  selector: 'app-recommendations-page',
  standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe, Toast, Dialog, StatusBadgeComponent],
  template: `
    <p-toast />
    <div>
      <div class="mb-6 flex items-center justify-between">
        <h2 class="text-xl font-bold text-text">AI Recommendations</h2>
        <div class="flex gap-2">
          <button
            (click)="toggleView()"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm text-muted hover:bg-gray-50"
          >
            {{ showHistory() ? 'Show Active' : 'Show History' }}
          </button>
          <button
            (click)="generateNew()"
            [disabled]="generating()"
            class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
          >
            {{ generating() ? 'Generating...' : 'Generate New' }}
          </button>
        </div>
      </div>

      <!-- Impact Summary -->
      @if (!showHistory() && impact()) {
        <div class="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
          <div class="rounded-lg border border-gray-200 bg-surface p-4">
            <p class="text-sm text-muted">Pending</p>
            <p class="text-2xl font-bold text-text">{{ impact()!.total_pending }}</p>
          </div>
          <div class="rounded-lg border border-gray-200 bg-surface p-4">
            <p class="text-sm text-muted">Revenue Impact</p>
            <p class="text-2xl font-bold text-success">
              {{ impact()!.projected_revenue_impact | number: '1.0-0' }}
            </p>
          </div>
          <div class="rounded-lg border border-gray-200 bg-surface p-4">
            <p class="text-sm text-muted">Cost Savings</p>
            <p class="text-2xl font-bold text-secondary">
              {{ impact()!.projected_cost_savings | number: '1.0-0' }}
            </p>
          </div>
        </div>
      }

      <!-- Category Filter -->
      @if (!showHistory()) {
        <div class="mb-4 flex gap-2">
          @for (cat of categories; track cat) {
            <button
              (click)="filterCategory(cat)"
              class="rounded-full px-3 py-1 text-xs font-medium"
              [class]="activeCategory() === cat ? 'bg-primary text-white' : 'bg-gray-100 text-muted hover:bg-gray-200'"
            >
              {{ cat === 'ALL' ? 'All' : cat }}
            </button>
          }
        </div>
      }

      <!-- Recommendations List -->
      <div class="space-y-4">
        @for (rec of filteredRecs(); track rec.id) {
          <div class="rounded-lg border border-gray-200 bg-surface p-4">
            <div class="flex items-start justify-between">
              <div class="flex-1">
                <div class="mb-2 flex items-center gap-2">
                  <i [class]="categoryIcon(rec.category)"></i>
                  <app-status-badge [label]="rec.priority" [status]="priorityStatus(rec.priority)" />
                  <span class="text-xs text-muted">{{ rec.category }}</span>
                  <span class="text-xs text-muted">&middot;</span>
                  <span class="text-xs text-muted">{{ rec.created_at | date: 'short' }}</span>
                </div>
                <h4 class="text-sm font-semibold text-text">{{ rec.title }}</h4>
                <p class="mt-1 text-sm text-muted">{{ rec.description }}</p>
                @if (rec.expected_impact) {
                  <div class="mt-2 flex gap-4 text-xs text-muted">
                    @for (entry of impactEntries(rec.expected_impact); track entry[0]) {
                      <span>{{ entry[0] }}: <strong>{{ entry[1] }}</strong></span>
                    }
                  </div>
                }
              </div>
              @if (rec.status === 'PENDING') {
                <div class="ml-4 flex gap-2">
                  <button
                    (click)="applyRec(rec.id)"
                    class="rounded bg-success px-3 py-1.5 text-xs font-medium text-white hover:bg-success/90"
                  >
                    Apply
                  </button>
                  <button
                    (click)="openDismiss(rec)"
                    class="rounded border border-gray-300 px-3 py-1.5 text-xs text-muted hover:bg-gray-50"
                  >
                    Dismiss
                  </button>
                </div>
              } @else {
                <app-status-badge
                  [label]="rec.status"
                  [status]="rec.status === 'APPLIED' ? 'success' : 'neutral'"
                />
              }
            </div>
          </div>
        } @empty {
          <p class="text-center text-muted">
            {{ showHistory() ? 'No recommendation history' : 'No pending recommendations' }}
          </p>
        }
      </div>
    </div>

    <!-- Dismiss Dialog -->
    <p-dialog
      header="Dismiss Recommendation"
      [(visible)]="dismissVisible"
      [modal]="true"
      [style]="{ width: '400px' }"
    >
      <div class="space-y-4">
        <p class="text-sm text-muted">Why are you dismissing this recommendation?</p>
        <textarea
          [(ngModel)]="dismissReason"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          rows="3"
          placeholder="Reason for dismissal..."
        ></textarea>
        <button
          (click)="confirmDismiss()"
          [disabled]="!dismissReason"
          class="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
        >
          Dismiss
        </button>
      </div>
    </p-dialog>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecommendationsPageComponent implements OnInit {
  private readonly recsService = inject(RecommendationsService);
  private readonly messageService = inject(MessageService);

  recs = signal<Recommendation[]>([]);
  historyRecs = signal<Recommendation[]>([]);
  impact = signal<ImpactSummary | null>(null);
  showHistory = signal(false);
  generating = signal(false);
  activeCategory = signal('ALL');
  dismissVisible = false;
  dismissReason = '';
  dismissTarget = signal<Recommendation | null>(null);

  readonly categories = ['ALL', 'PRICING', 'INVENTORY', 'FX', 'CASHFLOW', 'ORDERS'];

  ngOnInit(): void {
    this.loadRecs();
    this.recsService.getImpact().subscribe({ next: (i) => this.impact.set(i) });
  }

  private loadRecs(): void {
    this.recsService.getAll().subscribe({
      next: (r) => this.recs.set(r.items),
    });
  }

  filteredRecs(): Recommendation[] {
    if (this.showHistory()) return this.historyRecs();
    const cat = this.activeCategory();
    const items = this.recs();
    if (cat === 'ALL') return items.filter((r) => r.status === 'PENDING');
    return items.filter((r) => r.status === 'PENDING' && r.category === cat);
  }

  toggleView(): void {
    this.showHistory.update((v) => !v);
    if (this.showHistory() && this.historyRecs().length === 0) {
      this.recsService.getHistory().subscribe({
        next: (h) => this.historyRecs.set(h),
      });
    }
  }

  filterCategory(cat: string): void {
    this.activeCategory.set(cat);
  }

  generateNew(): void {
    this.generating.set(true);
    this.recsService.generate().subscribe({
      next: (newRecs) => {
        this.recs.update((existing) => [...newRecs, ...existing]);
        this.generating.set(false);
        this.messageService.add({
          severity: 'success',
          summary: 'Generated',
          detail: `${newRecs.length} new recommendations`,
        });
      },
      error: () => {
        this.generating.set(false);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to generate recommendations',
        });
      },
    });
  }

  applyRec(id: string): void {
    this.recsService.apply(id).subscribe({
      next: () => {
        this.recs.update((recs) => recs.filter((r) => r.id !== id));
        this.messageService.add({
          severity: 'success',
          summary: 'Applied',
          detail: 'Recommendation applied',
        });
      },
    });
  }

  openDismiss(rec: Recommendation): void {
    this.dismissTarget.set(rec);
    this.dismissReason = '';
    this.dismissVisible = true;
  }

  confirmDismiss(): void {
    const target = this.dismissTarget();
    if (!target || !this.dismissReason) return;
    this.recsService.dismiss(target.id, this.dismissReason).subscribe({
      next: () => {
        this.recs.update((recs) => recs.filter((r) => r.id !== target.id));
        this.dismissVisible = false;
        this.messageService.add({
          severity: 'info',
          summary: 'Dismissed',
          detail: 'Recommendation dismissed',
        });
      },
    });
  }

  categoryIcon(cat: string): string {
    const icons: Record<string, string> = {
      PRICING: 'pi pi-tag text-secondary',
      INVENTORY: 'pi pi-box text-warning',
      FX: 'pi pi-money-bill text-success',
      CASHFLOW: 'pi pi-chart-line text-primary',
      ORDERS: 'pi pi-truck text-muted',
    };
    return icons[cat] ?? 'pi pi-sparkles text-muted';
  }

  priorityStatus(p: string): 'danger' | 'warning' | 'info' {
    if (p === 'HIGH') return 'danger';
    if (p === 'MEDIUM') return 'warning';
    return 'info';
  }

  impactEntries(impact: Record<string, unknown>): [string, unknown][] {
    return Object.entries(impact);
  }
}
