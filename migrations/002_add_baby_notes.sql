-- Migration: Add notes column to babies table
-- Purpose: Allow parents to add health info (allergies, conditions) for AI context
-- Date: 2026-01-15

-- Add notes column if it doesn't exist
ALTER TABLE "Nappi"."babies" 
ADD COLUMN IF NOT EXISTS notes TEXT;

-- Add comment for documentation
COMMENT ON COLUMN "Nappi"."babies".notes IS 
  'Parent notes about baby: allergies, conditions, health info for AI context. Max 2000 chars.';
