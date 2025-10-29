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
