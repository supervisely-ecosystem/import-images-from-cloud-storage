import os
import sys
from pathlib import Path

import supervisely as sly

# for debugging, has no effect in production
from dotenv import load_dotenv

if sly.is_development():
    load_dotenv(os.path.expanduser("~/supervisely.env"))
    load_dotenv("local.env")

app: sly.AppService = sly.AppService()
app_sources_dir = str(Path(sys.argv[0]).parents[1])

api = sly.Api.from_env()

TEAM_ID = sly.env.team_id()
WORKSPACE_ID = sly.env.workspace_id()

USER_PREVIEW_LIMIT = 100
FILE_SIZE = None
BATCH_SIZE = 10000
