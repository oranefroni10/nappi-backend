-- Migration 003: Remove anomalies column from daily_summary
-- The anomalies column was never populated (always NULL). Removing dead code.

ALTER TABLE "Nappi"."daily_summary" DROP COLUMN IF EXISTS anomalies;
