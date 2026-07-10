-- Initialize the database with proper settings
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Set timezone
SET timezone = 'UTC';

-- Pre-create alembic_version with wider column to accommodate long migration IDs
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(64) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);