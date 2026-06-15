import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import path from 'path';

let db = null;

export async function getDb() {
  if (db) return db;
  const dbPath = path.resolve(process.cwd(), '../data/bulk_post_state.db');
  db = await open({
    filename: dbPath,
    driver: sqlite3.Database
  });
  return db;
}

let dedupDb = null;
export async function getDedupDb() {
  if (dedupDb) return dedupDb;
  const dbPath = path.resolve(process.cwd(), '../data/dedup.db');
  dedupDb = await open({
    filename: dbPath,
    driver: sqlite3.Database
  });
  return dedupDb;
}
