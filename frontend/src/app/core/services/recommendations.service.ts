import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface Recommendation {
  id: string;
  category: string;
  title: string;
  description: string;
  priority: string;
  confidence: number;
  expected_impact: Record<string, unknown> | null;
  action_type: string;
  action_payload: Record<string, unknown> | null;
  reference_id: string | null;
  reference_type: string | null;
  status: string;
  created_at: string;
  expires_at: string;
}

export interface RecommendationListResponse {
  items: Recommendation[];
  total: number;
  by_category: Record<string, number>;
  by_priority: Record<string, number>;
}

export interface ImpactSummary {
  total_pending: number;
  projected_revenue_impact: number;
  projected_cost_savings: number;
  by_category: Record<string, unknown>[];
}

@Injectable({ providedIn: 'root' })
export class RecommendationsService {
  private readonly api = inject(ApiService);

  getAll(params?: Record<string, string>): Observable<RecommendationListResponse> {
    return this.api.get<RecommendationListResponse>('/ai/recommendations', params);
  }

  getById(id: string): Observable<Recommendation> {
    return this.api.get<Recommendation>(`/ai/recommendations/${id}`);
  }

  generate(): Observable<Recommendation[]> {
    return this.api.post<Recommendation[]>('/ai/recommendations/generate', {});
  }

  apply(id: string, notes?: string): Observable<Recommendation> {
    return this.api.post<Recommendation>(`/ai/recommendations/${id}/apply`, { notes });
  }

  dismiss(id: string, reason: string): Observable<Recommendation> {
    return this.api.post<Recommendation>(`/ai/recommendations/${id}/dismiss`, { reason });
  }

  getImpact(): Observable<ImpactSummary> {
    return this.api.get<ImpactSummary>('/ai/recommendations/impact');
  }

  getHistory(limit = 50): Observable<Recommendation[]> {
    return this.api.get<Recommendation[]>('/ai/recommendations/history', {
      limit: String(limit),
    });
  }
}
