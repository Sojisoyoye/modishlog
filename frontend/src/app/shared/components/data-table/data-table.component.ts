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
    <div class="overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table class="min-w-full divide-y divide-gray-200">
        <thead>
          <tr class="bg-gray-50/80">
            @for (col of columns(); track col.key) {
              <th
                class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted"
              >
                {{ col.header }}
              </th>
            }
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          @for (row of data(); track $index) {
            <tr class="transition-colors hover:bg-gray-50/50">
              @for (col of columns(); track col.key) {
                <td class="whitespace-nowrap px-4 py-3 text-sm text-text">
                  {{ row[col.key] }}
                </td>
              }
            </tr>
          } @empty {
            <tr>
              <td
                [attr.colspan]="columns().length"
                class="px-4 py-12 text-center text-sm text-muted"
              >
                <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
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
