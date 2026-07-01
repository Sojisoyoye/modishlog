import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface UserListItem {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface UserListResponse {
  items: UserListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface UserInvite {
  email: string;
  full_name: string;
  role: string;
  password: string;
}

export interface UserUpdate {
  full_name?: string;
  role?: string;
  is_active?: boolean;
}

@Injectable({ providedIn: 'root' })
export class UsersService {
  private readonly api = inject(ApiService);

  listUsers(page = 1, pageSize = 20, search?: string): Observable<UserListResponse> {
    const params: Record<string, string> = {
      page: String(page),
      page_size: String(pageSize),
    };
    if (search) params['search'] = search;
    return this.api.get<UserListResponse>('/auth/admin/users', params);
  }

  getUser(id: string): Observable<UserListItem> {
    return this.api.get<UserListItem>(`/auth/admin/users/${id}`);
  }

  inviteUser(data: UserInvite): Observable<UserListItem> {
    return this.api.post<UserListItem>('/auth/admin/users/invite', data);
  }

  updateUser(id: string, data: UserUpdate): Observable<UserListItem> {
    return this.api.patch<UserListItem>(`/auth/admin/users/${id}`, data);
  }

  deactivateUser(id: string): Observable<{ message: string }> {
    return this.api.post<{ message: string }>(`/auth/admin/users/${id}/deactivate`, {});
  }

  activateUser(id: string): Observable<{ message: string }> {
    return this.api.post<{ message: string }>(`/auth/admin/users/${id}/activate`, {});
  }

  resetPassword(id: string): Observable<{ message: string; token: string }> {
    return this.api.post<{ message: string; token: string }>(
      `/auth/admin/users/${id}/reset-password`,
      {},
    );
  }
}
