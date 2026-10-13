import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const schemaPath = join(dirname(fileURLToPath(import.meta.url)), '..', 'schema.sql');

export function newD1() {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(schemaPath, 'utf8'));
  return {
    prepare(sql) {
      const stmt = db.prepare(sql);
      return {
        bind(...args) {
          return {
            run() {
              const info = stmt.run(...args);
              return { meta: { changes: info.changes } };
            },
            first() {
              return stmt.get(...args) ?? null;
            },
            all() {
              return { results: stmt.all(...args) };
            },
          };
        },
      };
    },
  };
}
