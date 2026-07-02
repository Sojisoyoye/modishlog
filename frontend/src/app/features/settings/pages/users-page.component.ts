import {
  Component,
  ChangeDetectionStrategy,
  inject,
  signal,
  computed,
  OnInit,
  OnDestroy,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { UsersService, UserListItem, UserInvite } from '../../../core/services/users.service';

@Component({
  selector: 'app-users-page',
  standalone: true,
  imports: [DatePipe, FormsModule, Toast],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />

    <!-- Header -->
    <div class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
          <i class="pi pi-users text-lg"></i>
        </div>
        <div>
          <h2 class="text-2xl font-bold text-text">Users</h2>
          <p class="mt-0.5 text-sm text-muted">Manage team members and roles</p>
        </div>
      </div>
      <button
        (click)="showInviteDialog.set(true)"
        class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 min-h-[40px]"
      >
        <i class="pi pi-user-plus text-sm"></i> Invite User
      </button>
    </div>

    <!-- Search -->
    <div class="mb-4 flex gap-3">
      <div class="relative flex-1 max-w-sm">
        <i class="pi pi-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm"></i>
        <input
          type="text"
          [(ngModel)]="searchTerm"
          (ngModelChange)="onSearchChange($event)"
          placeholder="Search users..."
          class="w-full rounded-lg border border-gray-300 pl-9 pr-3 py-2 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[40px]"
        />
      </div>
    </div>

    <!-- Users Table -->
    <div class="rounded-xl border border-gray-100 bg-white shadow-sm overflow-hidden">
      @if (loading()) {
        <div class="flex items-center justify-center py-16 text-gray-400">
          <i class="pi pi-spin pi-spinner text-2xl"></i>
        </div>
      } @else if (users().length === 0) {
        <div class="py-16 text-center text-muted">
          <i class="pi pi-users text-4xl mb-3 text-gray-300"></i>
          <p class="text-sm">No users found</p>
        </div>
      } @else {
        <table class="w-full text-sm">
          <thead class="border-b border-gray-100 bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Name</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Email</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Role</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Joined</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            @for (user of users(); track user.id) {
              <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-4 py-3 font-medium text-text">{{ user.full_name }}</td>
                <td class="px-4 py-3 text-muted">{{ user.email }}</td>
                <td class="px-4 py-3">
                  <span
                    class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                    [class]="user.role === 'admin'
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-blue-50 text-blue-700'"
                  >
                    {{ user.role === 'admin' ? 'Admin' : 'Sales Manager' }}
                  </span>
                </td>
                <td class="px-4 py-3">
                  <span
                    class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                    [class]="user.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'"
                  >
                    {{ user.is_active ? 'Active' : 'Inactive' }}
                  </span>
                </td>
                <td class="px-4 py-3 text-muted">{{ user.created_at | date: 'dd MMM yyyy' }}</td>
                <td class="px-4 py-3 text-right">
                  <div class="flex justify-end gap-1">
                    <button
                      (click)="openEdit(user)"
                      title="Edit user"
                      class="rounded-lg px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-100 min-h-[32px]"
                    >
                      <i class="pi pi-pencil"></i>
                    </button>
                    @if (user.is_active) {
                      <button
                        (click)="confirmDeactivate(user)"
                        title="Deactivate user"
                        class="rounded-lg px-2 py-1.5 text-xs text-red-600 hover:bg-red-50 min-h-[32px]"
                      >
                        <i class="pi pi-ban"></i>
                      </button>
                    } @else {
                      <button
                        (click)="doActivate(user)"
                        title="Activate user"
                        class="rounded-lg px-2 py-1.5 text-xs text-emerald-600 hover:bg-emerald-50 min-h-[32px]"
                      >
                        <i class="pi pi-check-circle"></i>
                      </button>
                    }
                    <button
                      (click)="doResetPassword(user)"
                      title="Reset password"
                      class="rounded-lg px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-100 min-h-[32px]"
                    >
                      <i class="pi pi-key"></i>
                    </button>
                  </div>
                </td>
              </tr>
            }
          </tbody>
        </table>
      }
    </div>

    <!-- Pagination -->
    @if (total() > pageSize()) {
      <div class="mt-4 flex items-center justify-between text-sm text-muted">
        <span>{{ total() }} users total</span>
        <div class="flex gap-2">
          <button
            (click)="changePage(page() - 1)"
            [disabled]="page() === 1"
            class="rounded-lg border border-gray-300 px-3 py-1.5 text-xs disabled:opacity-40 hover:bg-gray-50 min-h-[32px]"
          >
            <i class="pi pi-chevron-left"></i>
          </button>
          <span class="px-2 py-1.5 text-xs">{{ page() }} / {{ totalPages() }}</span>
          <button
            (click)="changePage(page() + 1)"
            [disabled]="page() >= totalPages()"
            class="rounded-lg border border-gray-300 px-3 py-1.5 text-xs disabled:opacity-40 hover:bg-gray-50 min-h-[32px]"
          >
            <i class="pi pi-chevron-right"></i>
          </button>
        </div>
      </div>
    }

    <!-- Invite User Dialog -->
    @if (showInviteDialog()) {
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
        <div class="w-full max-w-md rounded-2xl bg-white shadow-2xl">
          <div class="flex items-center justify-between border-b border-gray-100 px-6 py-4">
            <h3 class="text-base font-semibold text-text">Invite User</h3>
            <button (click)="showInviteDialog.set(false)" class="text-gray-400 hover:text-text min-h-[32px] min-w-[32px]">
              <i class="pi pi-times"></i>
            </button>
          </div>
          <div class="space-y-4 px-6 py-5">
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Full Name</label>
              <input
                type="text"
                [(ngModel)]="inviteForm.full_name"
                placeholder="Jane Smith"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[40px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Email</label>
              <input
                type="email"
                [(ngModel)]="inviteForm.email"
                placeholder="jane@example.com"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[40px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Role</label>
              <select
                [(ngModel)]="inviteForm.role"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[40px]"
              >
                <option value="sales_manager">Sales Manager</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Temporary Password</label>
              <input
                type="password"
                [(ngModel)]="inviteForm.password"
                placeholder="Min 12 chars, upper, lower, digit, special"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[40px]"
              />
            </div>
          </div>
          <div class="flex justify-end gap-2 border-t border-gray-100 px-6 py-4">
            <button
              (click)="showInviteDialog.set(false)"
              class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]"
            >
              Cancel
            </button>
            <button
              (click)="doInvite()"
              [disabled]="inviteSaving()"
              class="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50 min-h-[40px]"
            >
              <i class="pi pi-user-plus text-sm"></i>
              {{ inviteSaving() ? 'Inviting...' : 'Invite' }}
            </button>
          </div>
        </div>
      </div>
    }

    <!-- Edit User Dialog -->
    @if (showEditDialog() && editingUser()) {
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
        <div class="w-full max-w-md rounded-2xl bg-white shadow-2xl">
          <div class="flex items-center justify-between border-b border-gray-100 px-6 py-4">
            <h3 class="text-base font-semibold text-text">Edit User</h3>
            <button (click)="showEditDialog.set(false)" class="text-gray-400 hover:text-text min-h-[32px] min-w-[32px]">
              <i class="pi pi-times"></i>
            </button>
          </div>
          <div class="space-y-4 px-6 py-5">
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Full Name</label>
              <input
                type="text"
                [(ngModel)]="editForm.full_name"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[40px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Role</label>
              <select
                [(ngModel)]="editForm.role"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[40px]"
              >
                <option value="sales_manager">Sales Manager</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <div class="flex justify-end gap-2 border-t border-gray-100 px-6 py-4">
            <button
              (click)="showEditDialog.set(false)"
              class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]"
            >
              Cancel
            </button>
            <button
              (click)="doUpdate()"
              [disabled]="editSaving()"
              class="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50 min-h-[40px]"
            >
              <i class="pi pi-save text-sm"></i>
              {{ editSaving() ? 'Saving...' : 'Save' }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class UsersPageComponent implements OnInit, OnDestroy {
  private readonly usersService = inject(UsersService);
  private readonly toast = inject(MessageService);

  readonly users = signal<UserListItem[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(20);
  readonly loading = signal(false);
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.pageSize())));

  searchTerm = '';
  private searchTimeout: ReturnType<typeof setTimeout> | null = null;

  readonly showInviteDialog = signal(false);
  readonly inviteSaving = signal(false);
  inviteForm: UserInvite = { email: '', full_name: '', role: 'sales_manager', password: '' };

  readonly showEditDialog = signal(false);
  readonly editSaving = signal(false);
  readonly editingUser = signal<UserListItem | null>(null);
  editForm: { full_name: string; role: string } = { full_name: '', role: '' };

  ngOnInit(): void {
    this.loadUsers();
  }

  ngOnDestroy(): void {
    if (this.searchTimeout) clearTimeout(this.searchTimeout);
  }

  private loadUsers(): void {
    this.loading.set(true);
    this.usersService
      .listUsers(this.page(), this.pageSize(), this.searchTerm || undefined)
      .subscribe({
        next: (res) => {
          this.users.set(res.items);
          this.total.set(res.total);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to load users' });
        },
      });
  }

  onSearchChange(_value: string): void {
    if (this.searchTimeout) clearTimeout(this.searchTimeout);
    this.searchTimeout = setTimeout(() => {
      this.page.set(1);
      this.loadUsers();
    }, 300);
  }

  changePage(p: number): void {
    this.page.set(p);
    this.loadUsers();
  }

  openEdit(user: UserListItem): void {
    this.editingUser.set(user);
    this.editForm = { full_name: user.full_name, role: user.role };
    this.showEditDialog.set(true);
  }

  doInvite(): void {
    if (!this.inviteForm.email || !this.inviteForm.full_name || !this.inviteForm.password) {
      this.toast.add({ severity: 'warn', summary: 'Validation', detail: 'All fields are required' });
      return;
    }
    this.inviteSaving.set(true);
    this.usersService.inviteUser(this.inviteForm).subscribe({
      next: () => {
        this.inviteSaving.set(false);
        this.showInviteDialog.set(false);
        this.inviteForm = { email: '', full_name: '', role: 'sales_manager', password: '' };
        this.loadUsers();
        this.toast.add({ severity: 'success', summary: 'Invited', detail: 'User created successfully' });
      },
      error: (err) => {
        this.inviteSaving.set(false);
        const detail = err?.error?.detail ?? 'Failed to invite user';
        this.toast.add({ severity: 'error', summary: 'Error', detail });
      },
    });
  }

  doUpdate(): void {
    const user = this.editingUser();
    if (!user) return;
    this.editSaving.set(true);
    this.usersService.updateUser(user.id, this.editForm).subscribe({
      next: (updated) => {
        this.editSaving.set(false);
        this.showEditDialog.set(false);
        this.users.update((list) => list.map((u) => (u.id === updated.id ? updated : u)));
        this.toast.add({ severity: 'success', summary: 'Saved', detail: 'User updated' });
      },
      error: (err) => {
        this.editSaving.set(false);
        const detail = err?.error?.detail ?? 'Failed to update user';
        this.toast.add({ severity: 'error', summary: 'Error', detail });
      },
    });
  }

  confirmDeactivate(user: UserListItem): void {
    if (!confirm(`Deactivate ${user.full_name}? They will be signed out immediately.`)) return;
    this.usersService.deactivateUser(user.id).subscribe({
      next: () => {
        this.users.update((list) =>
          list.map((u) => (u.id === user.id ? { ...u, is_active: false } : u)),
        );
        this.toast.add({ severity: 'success', summary: 'Deactivated', detail: `${user.full_name} deactivated` });
      },
      error: (err) => {
        const detail = err?.error?.detail ?? 'Failed to deactivate user';
        this.toast.add({ severity: 'error', summary: 'Error', detail });
      },
    });
  }

  doActivate(user: UserListItem): void {
    this.usersService.activateUser(user.id).subscribe({
      next: () => {
        this.users.update((list) =>
          list.map((u) => (u.id === user.id ? { ...u, is_active: true } : u)),
        );
        this.toast.add({ severity: 'success', summary: 'Activated', detail: `${user.full_name} activated` });
      },
      error: () => {
        this.toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to activate user' });
      },
    });
  }

  doResetPassword(user: UserListItem): void {
    if (!confirm(`Generate a password reset token for ${user.full_name}?`)) return;
    this.usersService.resetPassword(user.id).subscribe({
      next: (res) => {
        this.toast.add({
          severity: 'info',
          summary: 'Reset Token',
          detail: `Token: ${res.token}`,
          life: 15000,
        });
      },
      error: () => {
        this.toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to reset password' });
      },
    });
  }
}
