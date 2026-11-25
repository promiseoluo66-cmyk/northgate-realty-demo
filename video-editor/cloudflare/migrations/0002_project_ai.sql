ALTER TABLE jobs ADD COLUMN project_json TEXT;
ALTER TABLE jobs ADD COLUMN project_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN ai_status TEXT NOT NULL DEFAULT 'idle';
ALTER TABLE jobs ADD COLUMN pending_plan_json TEXT;
ALTER TABLE jobs ADD COLUMN confirmed_tools_json TEXT NOT NULL DEFAULT '[]';
CREATE INDEX IF NOT EXISTS idx_jobs_project_revision ON jobs(project_revision);
ALTER TABLE jobs ADD COLUMN history_state_json TEXT NOT NULL DEFAULT '{"undo":[],"redo":[]}';
