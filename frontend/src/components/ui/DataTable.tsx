import type { ReactNode } from "react";
import clsx from "clsx";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  numeric?: boolean;
}

/** st.dataframe equivalent: static, scrolls horizontally on narrow screens. */
export function DataTable<T>({
  columns, rows, caption,
}: { columns: Column<T>[]; rows: T[]; caption: string }) {
  return (
    <div className="overflow-x-auto rounded-[var(--radius-control)] border border-line bg-surface">
      <table className="w-full min-w-max text-[14px] leading-5">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line bg-page text-left text-[12px] leading-4 text-ink-2">
            {columns.map((c) => (
              <th key={c.key} scope="col" className={clsx("px-3.5 py-2.5 font-medium", c.numeric && "text-right")}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              {columns.map((c) => (
                <td key={c.key} className={clsx("px-3.5 py-2.5", c.numeric && "num text-right")}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
