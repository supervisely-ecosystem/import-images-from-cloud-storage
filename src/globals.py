import os
import sys
from pathlib import Path

import supervisely as sly

# for debugging, has no effect in production
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/supervisely.env"))
load_dotenv("local.env")

app: sly.AppService = sly.AppService()
app_sources_dir = str(Path(sys.argv[0]).parents[1])

api = sly.Api()

TEAM_ID = int(os.environ["context.teamId"])
WORKSPACE_ID = int(os.environ["context.workspaceId"])

USER_PREVIEW_LIMIT = 100
FILE_SIZE = None
BATCH_SIZE = 10000
