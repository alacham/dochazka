-- schema.sql

-- Table to store employee information
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 -- 1 for active, 0 for disabled
);

-- Table to store attendance records
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    status TEXT NOT NULL, -- "Enter" or "Leave"
    timestamp TEXT NOT NULL, -- Stored as ISO 8601 string
    FOREIGN KEY (employee_id) REFERENCES employees (id)
);

-- Table to store authentication tokens
CREATE TABLE IF NOT EXISTS auth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);
