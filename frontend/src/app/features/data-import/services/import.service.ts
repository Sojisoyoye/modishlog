import { Injectable, inject } from '@angular/core';
import { HttpContext } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { NO_RETRY } from '../../../core/interceptors/retry.interceptor';
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
  private readonly baseUrl = environment.apiBaseUrl;
  // Mutating calls that aren't safely re-playable — a lost response +
  // blind retry could resubmit a request whose first attempt actually
  // already succeeded (e.g. double-confirm an import, double-create a job).
  private readonly noRetry = new HttpContext().set(NO_RETRY, true);

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
    return this.api.post<MigrationJob>('/import/jobs', formData, this.noRetry);
  }

  createApiJob(sourceSystem: SourceSystem, credentials: ApiCredentials): Observable<MigrationJob> {
    const formData = new FormData();
    formData.append('source_system', sourceSystem);
    formData.append('extraction_mode', 'api');
    formData.append('api_base_url', credentials.api_base_url);
    if (credentials.username) formData.append('username', credentials.username);
    if (credentials.password) formData.append('password', credentials.password);
    if (credentials.access_token) formData.append('access_token', credentials.access_token);
    return this.api.post<MigrationJob>('/import/jobs', formData, this.noRetry);
  }

  listJobs(): Observable<MigrationJobListResponse> {
    return this.api.get<MigrationJobListResponse>('/import/jobs');
  }

  getJob(jobId: string): Observable<MigrationJob> {
    return this.api.get<MigrationJob>(`/import/jobs/${jobId}`);
  }

  validateJob(jobId: string): Observable<MigrationJob> {
    return this.api.post<MigrationJob>(`/import/jobs/${jobId}/validate`, {}, this.noRetry);
  }

  getConfirmationSnapshot(jobId: string): Observable<ConfirmationSnapshot> {
    return this.api.get<ConfirmationSnapshot>(`/import/jobs/${jobId}/confirmation-snapshot`);
  }

  confirmJob(jobId: string, approved: boolean): Observable<MigrationJob> {
    return this.api.post<MigrationJob>(`/import/jobs/${jobId}/confirm`, { approved }, this.noRetry);
  }

  rollbackJob(jobId: string): Observable<MigrationJob> {
    return this.api.delete<MigrationJob>(`/import/jobs/${jobId}`, this.noRetry);
  }
}
