export type SourceSystem = 'ultimatepos' | 'quickbooks' | 'shopify' | 'generic';

export const SOURCE_LABELS: Record<SourceSystem, string> = {
  ultimatepos: 'UltimatePOS',
  quickbooks: 'QuickBooks',
  shopify: 'Shopify',
  generic: 'Generic CSV',
};

/** Humanizes a snake_case entity/status key for display, e.g. "business_locations" -> "Business locations". */
export function humanizeKey(key: string): string {
  return key.replace(/_/g, ' ');
}

/** Sums a MigrationJob's per-entity row counts into a single total. */
export function sumRowCounts(rowCounts: Record<string, number>): number {
  return Object.values(rowCounts).reduce((sum, n) => sum + n, 0);
}

export type ExtractionMode = 'csv' | 'api';

export type MigrationJobStatus =
  | 'pending'
  | 'extracting'
  | 'transforming'
  | 'awaiting_confirmation'
  | 'importing'
  | 'recomputing'
  | 'done'
  | 'failed'
  | 'cancelled'
  | 'rolled_back';

export const IMPORTABLE_ENTITIES = [
  'product_categories',
  'products',
  'product_variants',
  'suppliers',
  'customers',
  'business_locations',
  'sales',
] as const;

export type ImportEntity = (typeof IMPORTABLE_ENTITIES)[number];

export const REQUIRED_ENTITIES: ReadonlySet<ImportEntity> = new Set(['products']);

export const ENTITY_LABELS: Record<ImportEntity, string> = {
  product_categories: 'Product Categories',
  products: 'Products',
  product_variants: 'Product Variants',
  suppliers: 'Suppliers',
  customers: 'Customers',
  business_locations: 'Business Locations',
  sales: 'Sales',
};

export interface ValidationIssue {
  entity: string;
  row: number;
  field: string | null;
  severity: 'error' | 'warning';
  message: string;
}

export interface MigrationJob {
  id: string;
  business_id: string;
  status: MigrationJobStatus;
  source_system: SourceSystem;
  extraction_mode: ExtractionMode;
  row_counts: Record<string, number>;
  validation_errors: ValidationIssue[];
  validation_warnings: ValidationIssue[];
  created_at: string;
  completed_at: string | null;
}

export interface MigrationJobListResponse {
  items: MigrationJob[];
}

export interface TestConnectionDateRange {
  earliest: string | null;
  latest: string | null;
}

export interface TestConnectionResponse {
  connected: boolean;
  source_system: SourceSystem;
  counts: Record<string, number>;
  date_range: TestConnectionDateRange | null;
}

export interface SnapshotEntity {
  name: string;
  count: number;
  sample_rows: Record<string, string>[];
  date_range: TestConnectionDateRange | null;
}

export interface ConfirmationSnapshot {
  job_id: string;
  extraction_mode: ExtractionMode;
  source_system: SourceSystem;
  status: MigrationJobStatus;
  entities: SnapshotEntity[];
  warnings: ValidationIssue[];
  ghost_records: Record<string, number>;
  total_rows: number;
}

export interface ApiCredentials {
  api_base_url: string;
  username?: string;
  password?: string;
  access_token?: string;
}
