import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { environment } from '../../../../environments/environment';
import {
  ApiCredentials,
  ConfirmationSnapshot,
  ImportEntity,
  MigrationJob,
  MigrationJobListResponse,
  SourceSystem,
  TestConnectionResponse,
} from '../models/import.models';

@Injectable({ providedIn: 'root' })
export class ImportService {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiBaseUrl;

  getAllTemplatesUrl(): string {
    return `${this.baseUrl}/import/templates`;
  }

  getEntityTemplateUrl(entity: ImportEntity): string {
    return `${this.baseUrl}/import/templates/${entity}`;
  }

  testConnection(
    sourceSystem: SourceSystem,
    credentials: ApiCredentials,
  ): Observable<TestConnectionResponse> {
    return this.api.post<TestConnectionResponse>('/import/jobs/test-connection', {
      source_system: sourceSystem,
      api_base_url: credentials.api_base_url,
      username: credentials.username || null,
      password: credentials.password || null,
      access_token: credentials.access_token || null,
    });
  }

  createCsvJob(sourceSystem: SourceSystem, files: Partial<Record<ImportEntity, File>>): Observable<MigrationJob> {
    const formData = new FormData();
    formData.append('source_system', sourceSystem);
    formData.append('extraction_mode', 'csv');
    for (const [entity, file] of Object.entries(files)) {
      if (file) formData.append(entity, file, file.name);
    }
    return this.http.post<MigrationJob>(`${this.baseUrl}/import/jobs`, formData);
  }

  createApiJob(sourceSystem: SourceSystem, credentials: ApiCredentials): Observable<MigrationJob> {
    const formData = new FormData();
    formData.append('source_system', sourceSystem);
    formData.append('extraction_mode', 'api');
    formData.append('api_base_url', credentials.api_base_url);
    if (credentials.username) formData.append('username', credentials.username);
    if (credentials.password) formData.append('password', credentials.password);
    if (credentials.access_token) formData.append('access_token', credentials.access_token);
    return this.http.post<MigrationJob>(`${this.baseUrl}/import/jobs`, formData);
  }

  listJobs(): Observable<MigrationJobListResponse> {
    return this.api.get<MigrationJobListResponse>('/import/jobs');
  }

  getJob(jobId: string): Observable<MigrationJob> {
    return this.api.get<MigrationJob>(`/import/jobs/${jobId}`);
  }

  validateJob(jobId: string): Observable<MigrationJob> {
    return this.api.post<MigrationJob>(`/import/jobs/${jobId}/validate`, {});
  }

  getConfirmationSnapshot(jobId: string): Observable<ConfirmationSnapshot> {
    return this.api.get<ConfirmationSnapshot>(`/import/jobs/${jobId}/confirmation-snapshot`);
  }

  confirmJob(jobId: string, approved: boolean): Observable<MigrationJob> {
    return this.api.post<MigrationJob>(`/import/jobs/${jobId}/confirm`, { approved });
  }

  rollbackJob(jobId: string): Observable<MigrationJob> {
    return this.api.delete<MigrationJob>(`/import/jobs/${jobId}`);
  }
}
