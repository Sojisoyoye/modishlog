import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
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
      <!-- Page Header -->
      <div class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-50">
            <i class="pi pi-sparkles text-lg text-emerald-700"></i>
          </div>
          <div>
            <h2 class="text-2xl font-bold text-gray-900">AI Recommendations</h2>
            <p class="mt-0.5 text-sm text-gray-500">AI-powered insights to optimize your business</p>
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <!-- Active / History toggle button -->
          <button
            (click)="toggleView()"
            class="flex min-h-[44px] items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            @if (showHistory()) {
              <i class="pi pi-list text-sm"></i> Show Active
            } @else {
              <i class="pi pi-history text-sm"></i> Show History
            }
          </button>
          <button
            (click)="generateNew()"
            [disabled]="generating()"
            class="flex min-h-[44px] items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md disabled:opacity-50"
          >
            @if (generating()) {
              <i class="pi pi-spinner pi-spin text-sm"></i> Generating...
            } @else {
              <i class="pi pi-sparkles text-sm"></i> Generate New
            }
          </button>
        </div>
      </div>

      <!-- Impact Summary Cards -->
      @if (!showHistory() && impact()) {
        <div class="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
          <!-- Pending -->
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div class="flex items-center gap-3">
              <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-50">
                <i class="pi pi-clock text-sm text-amber-700"></i>
              </div>
              <p class="text-sm font-medium text-gray-500">Pending</p>
            </div>
            <p class="mt-3 text-2xl font-bold text-gray-900">{{ impact()!.total_pending }}</p>
          </div>
          <!-- Implemented / Revenue Impact -->
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div class="flex items-center gap-3">
              <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50">
                <i class="pi pi-arrow-up text-sm text-emerald-700"></i>
              </div>
              <p class="text-sm font-medium text-gray-500">Revenue Impact</p>
            </div>
            <p class="mt-3 text-2xl font-bold text-gray-900">
              {{ impact()!.projected_revenue_impact | number: '1.0-0' }}
            </p>
          </div>
          <!-- Total Impact / Cost Savings -->
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div class="flex items-center gap-3">
              <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50">
                <i class="pi pi-wallet text-sm text-blue-700"></i>
              </div>
              <p class="text-sm font-medium text-gray-500">Cost Savings</p>
            </div>
            <p class="mt-3 text-2xl font-bold text-gray-900">
              {{ impact()!.projected_cost_savings | number: '1.0-0' }}
            </p>
          </div>
        </div>
      }

      <!-- Category Filter -->
      @if (!showHistory()) {
        <div class="mb-5 flex flex-wrap gap-2">
          @for (cat of categories; track cat) {
            <button
              (click)="filterCategory(cat)"
              class="rounded-full px-4 py-1.5 text-xs font-semibold transition-all"
              [class]="
                activeCategory() === cat
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-700'
              "
            >
              {{ cat === 'ALL' ? 'All' : cat }}
            </button>
          }
        </div>
      }

      <!-- Recommendations List -->
      @if (loading()) {
        <div class="space-y-4 p-4">
          @for (i of [1,2,3]; track i) {
            <div class="animate-pulse border border-gray-200 rounded-xl bg-white p-5">
              <div class="mb-2 flex items-center gap-2">
                <div class="h-4 bg-gray-200 rounded w-16"></div>
                <div class="h-4 bg-gray-200 rounded w-12"></div>
              </div>
              <div class="h-5 bg-gray-200 rounded w-48 mb-3"></div>
              <div class="h-4 bg-gray-200 rounded w-full mb-2"></div>
              <div class="h-4 bg-gray-200 rounded w-3/4 mb-4"></div>
              <div class="flex gap-3">
                <div class="h-8 bg-gray-200 rounded w-36"></div>
                <div class="h-8 bg-gray-200 rounded w-24"></div>
              </div>
            </div>
          }
        </div>
      } @else {
      <div class="space-y-3">
        @for (rec of filteredRecs(); track rec.id) {
          <div
            data-testid="rec-card"
            class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="flex-1 min-w-0">
                <!-- Category + priority row -->
                <div class="mb-2 flex flex-wrap items-center gap-2">
                  <i [class]="categoryIcon(rec.category)"></i>
                  <span class="text-xs font-semibold uppercase tracking-wider text-gray-400">{{ rec.category }}</span>
                  <app-status-badge
                    [label]="rec.priority"
                    [status]="priorityStatus(rec.priority)"
                  />
                  @if (!rec.confidence_reliable) {
                    <span class="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full font-medium">Low confidence</span>
                  }
                  @if (rec.requires_human_review) {
                    <span class="text-xs bg-orange-100 text-orange-800 px-2 py-0.5 rounded-full font-medium">Review required</span>
                  }
                  <span class="text-xs text-gray-300">&middot;</span>
                  <span class="text-xs text-gray-500">{{ rec.created_at | date: 'short' }}</span>
                </div>
                <h4 class="text-base font-semibold text-gray-900">{{ rec.title }}</h4>
                <p class="mt-1 text-sm leading-relaxed text-gray-600">{{ rec.description }}</p>
                <!-- Expected impact chips -->
                @if (rec.expected_impact) {
                  <div class="mt-3 flex flex-wrap gap-3 text-xs">
                    @for (entry of impactEntries(rec.expected_impact); track entry[0]) {
                      <span class="rounded-lg bg-gray-50 px-2 py-1 text-gray-500">
                        {{ entry[0] }}: <strong class="text-gray-900">{{ entry[1] }}</strong>
                      </span>
                    }
                  </div>
                }
              </div>
              <!-- Actions -->
              @if (rec.status === 'PENDING') {
                <div class="flex shrink-0 flex-col gap-2 sm:flex-row">
                  <button
                    (click)="applyRec(rec)"
                    class="flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-emerald-700"
                  >
                    <i class="pi pi-check text-xs"></i> Mark Implemented
                  </button>
                  <button
                    (click)="openDismiss(rec)"
                    class="flex min-h-[44px] items-center justify-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900"
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
          <!-- Empty state -->
          <div class="rounded-xl border border-gray-100 bg-white py-20 text-center shadow-sm">
            <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50">
              <i class="pi pi-sparkles text-3xl text-emerald-700"></i>
            </div>
            <p class="text-base font-semibold text-gray-900">No recommendations yet</p>
            <p class="mt-1 text-sm text-gray-500">
              {{ showHistory() ? 'No recommendation history found.' : 'Generate AI-powered insights to get started.' }}
            </p>
            @if (!showHistory()) {
              <button
                (click)="generateNew()"
                [disabled]="generating()"
                class="mt-5 inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 disabled:opacity-50"
              >
                <i class="pi pi-sparkles text-sm"></i> Generate New
              </button>
            }
          </div>
        }
      </div>
      }
    </div>

    <!-- Dismiss Dialog -->
    <p-dialog
      header="Dismiss Recommendation"
      [(visible)]="dismissVisible"
      [modal]="true"
      [style]="{ width: '400px' }"
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
    >
      <div class="space-y-4">
        <p class="text-sm text-gray-500">Why are you dismissing this recommendation?</p>
        <textarea
          [(ngModel)]="dismissReason"
          class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          rows="3"
          placeholder="Reason for dismissal..."
        ></textarea>
        <button
          (click)="confirmDismiss()"
          [disabled]="!dismissReason"
          class="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 disabled:opacity-50"
        >
          <i class="pi pi-check text-sm"></i> Dismiss
        </button>
      </div>
    </p-dialog>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecommendationsPageComponent implements OnInit, OnDestroy {
  private readonly recsService = inject(RecommendationsService);
  private readonly messageService = inject(MessageService);

  private historySubscription: Subscription | null = null;

  recs = signal<Recommendation[]>([]);
  historyRecs = signal<Recommendation[]>([]);
  impact = signal<ImpactSummary | null>(null);
  showHistory = signal(false);
  loading = signal(false);
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
    this.loading.set(true);
    this.recsService.getAll().subscribe({
      next: (r) => {
        this.recs.set(r.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
      },
    });
  }

  readonly filteredRecs = computed(() => {
    if (this.showHistory()) return this.historyRecs();
    const cat = this.activeCategory();
    const items = this.recs();
    if (cat === 'ALL') return items.filter((r) => r.status === 'PENDING');
    return items.filter((r) => r.status === 'PENDING' && r.category === cat);
  });

  showActive(): void {
    this.historySubscription?.unsubscribe();
    this.historySubscription = null;
    this.showHistory.set(false);
    this.loading.set(false);
  }

  ngOnDestroy(): void {
    this.historySubscription?.unsubscribe();
  }

  toggleView(): void {
    this.showHistory.update((v) => !v);
    if (this.showHistory() && this.historyRecs().length === 0) {
      this.loading.set(true);
      this.historySubscription = this.recsService.getHistory().subscribe({
        next: (h) => {
          this.historyRecs.set(h);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
        },
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

  applyRec(rec: Recommendation): void {
    if (rec.requires_human_review) {
      const reason = rec.human_review_reason ?? 'This recommendation requires human review before applying.';
      const confirmed = window.confirm(`Human review required:\n\n${reason}\n\nDo you want to proceed?`);
      if (!confirmed) return;
      this.recsService.apply(rec.id, undefined, true).subscribe({
        next: () => {
          this.recs.update((recs) => recs.filter((r) => r.id !== rec.id));
          this.historyRecs.set([]);
          this.messageService.add({
            severity: 'success',
            summary: 'Applied',
            detail: 'Recommendation applied',
          });
        },
      });
    } else {
      this.recsService.apply(rec.id).subscribe({
        next: () => {
          this.recs.update((recs) => recs.filter((r) => r.id !== rec.id));
          this.historyRecs.set([]);
          this.messageService.add({
            severity: 'success',
            summary: 'Applied',
            detail: 'Recommendation applied',
          });
        },
      });
    }
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
        this.historyRecs.set([]);
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
