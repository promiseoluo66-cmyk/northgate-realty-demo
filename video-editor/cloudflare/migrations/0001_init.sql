CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('queued','running','completed','failed')),
  message TEXT NOT NULL DEFAULT '',
  instruction TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  skill_json TEXT NOT NULL,
  release_id INTEGER NOT NULL,
  release_tag TEXT NOT NULL,
  input_asset_id INTEGER NOT NULL,
  input_filename TEXT NOT NULL,
  output_asset_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  run_url TEXT,
  artifact_url TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS skills (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1,
  skill_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO skills (id,name,description,version,skill_json,created_at,updated_at)
VALUES ('clean-shorts','Clean Shorts','A clean vertical short-video starting style.',1,
'{"id":"clean-shorts","version":1,"name":"Clean Shorts","description":"A clean vertical short-video starting style.","default_settings":{"aspect":"9:16","width":720,"height":1280,"speed":1},"operations":["trim","speed","reframe"]}',
CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
