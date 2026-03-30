import { Component, ChangeDetectionStrategy, input } from '@angular/core';

interface TableColumn {
  key: string;
  header: string;
  sortable?: boolean;
}

@Component({
  selector: 'app-data-table',
  standalone: true,
  imports: [],
  template: `
    <div class="overflow-x-auto rounded-lg border border-gray-200 bg-surface">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            @for (col of columns(); track col.key) {
              <th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
                {{ col.header }}
              </th>
            }
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          @for (row of data(); track $index) {
            <tr class="hover:bg-gray-50" [class.bg-gray-50]="$index % 2 === 1">
              @for (col of columns(); track col.key) {
                <td class="whitespace-nowrap px-4 py-3 text-sm text-text">
                  {{ row[col.key] }}
                </td>
              }
            </tr>
          } @empty {
            <tr>
              <td [attr.colspan]="columns().length" class="px-4 py-8 text-center text-sm text-muted">
                No data available
              </td>
            </tr>
          }
        </tbody>
      </table>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DataTableComponent {
  columns = input.required<TableColumn[]>();
  data = input.required<Record<string, unknown>[]>();
}
