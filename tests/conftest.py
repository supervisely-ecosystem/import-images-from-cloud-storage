"""Offline test harness: runs the `process` callback of src/main.py against small in-memory fakes.

No Supervisely server, agent or cloud storage is contacted. `sly.AppService` is replaced by a
fake that records modal windows; `sly.Api.from_env` returns `FakeApi`. Run from the repo root:
    python -m pytest tests
with the SDK version from dev_requirements.txt installed (plus pytest).
"""

import importlib
import os
import posixpath
import sys
from types import SimpleNamespace

import pytest

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
APP_MODULES = ("globals", "main", "ui", "workflow")


class FakeAppService:
    def __init__(self, *args, **kwargs):
        self.data_dir = os.environ["FAKE_APP_DATA_DIR"]
        os.makedirs(self.data_dir, exist_ok=True)
        self.modals = []  # (message, level)

    def callback(self, name):
        return lambda f: f

    def show_modal_window(self, message, level="info", log_message=True):
        self.modals.append((message, level))


class FakeRemoteStorage:
    """A bucket as {"<bucket>/<key>": size}. Listing pages are `page_size` long (the SDK default is 10000)."""

    def __init__(self, objects, page_size=10000, download_fails=()):
        self.objects = dict(objects)
        self.page_size = page_size
        self.download_fails = set(download_fails)
        self.list_calls = 0
        self.downloads = []  # local paths written

    @staticmethod
    def _split(path):
        provider, rest = path.split("://", 1)
        return provider, rest

    def _info(self, provider, full_key):
        bucket, key = full_key.split("/", 1)
        return {
            "type": "file",
            "name": posixpath.basename(key),
            "prefix": posixpath.dirname(key),
            "path": f"{provider}://{full_key}",
            "size": self.objects[full_key],
        }

    def list(self, path, recursive=True, files=True, folders=True, limit=10000,
             start_after="", team_id=None):
        self.list_calls += 1
        provider, rest = self._split(path.rstrip("/") + "/")
        bucket = rest.split("/", 1)[0]
        keys = sorted(k for k in self.objects if k.startswith(rest))
        result = []
        seen_folders = set()
        for full_key in keys:
            key = full_key.split("/", 1)[1]
            if start_after and key <= start_after:
                continue
            rel = full_key[len(rest):]
            if not recursive and "/" in rel:
                folder = rel.split("/", 1)[0]
                if folders and folder not in seen_folders:
                    seen_folders.add(folder)
                    result.append({"type": "folder", "name": folder,
                                   "prefix": posixpath.dirname(key[: len(key) - len(rel)] + folder),
                                   "path": f"{provider}://{rest}{folder}", "size": 0})
                continue
            if files:
                result.append(self._info(provider, full_key))
        return result[: min(limit, self.page_size)]

    def get_file_info_by_path(self, path, team_id=None):
        provider, rest = self._split(path.rstrip("/"))
        matches = sorted(k for k in self.objects if k.startswith(rest))
        return [self._info(provider, k) for k in matches][0]  # IndexError like the SDK

    def download_path(self, remote_path, save_path, progress_cb=None, team_id=None):
        provider, rest = self._split(remote_path)
        if rest in self.download_fails:
            raise OSError(f"[Errno 28] No space left on device: {save_path}")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(b"x" * self.objects[rest])
        self.downloads.append(save_path)
        if progress_cb is not None:
            progress_cb(self.objects[rest])


class FakeImageApi:
    def __init__(self, datasets, rejects=()):
        self.datasets = datasets  # dataset_id -> list of names
        self.rejects = set(rejects)  # names the server refuses
        self.calls = []

    def _add(self, dataset_id, names):
        existing = self.datasets[dataset_id]
        if len(set(names)) != len(names) or any(n in existing for n in names):
            raise RuntimeError("409: image with this name already exists")
        bad = [n for n in names if n in self.rejects]
        if bad:
            raise RuntimeError(f"400: can not process {bad}")
        existing.extend(names)
        return [SimpleNamespace(id=i, name=n) for i, n in enumerate(names)]

    def upload_paths(self, dataset_id, names, paths, progress_cb=None, **kwargs):
        self.calls.append(("paths", list(names)))
        for p in paths:
            assert os.path.isfile(p), p
        return self._add(dataset_id, names)

    def upload_links(self, dataset_id, names, links, progress_cb=None, **kwargs):
        self.calls.append(("links", list(names), list(links)))
        return self._add(dataset_id, names)

    def get_list(self, dataset_id, **kwargs):
        return [SimpleNamespace(name=n) for n in self.datasets[dataset_id]]


class FakeApi:
    def __init__(self, objects, page_size=10000, download_fails=(), rejects=(),
                 existing_project=None):
        self.remote_storage = FakeRemoteStorage(objects, page_size, download_fails)
        self.datasets = {}  # id -> names
        self.dataset_names = {}  # id -> (project_id, name, parent_id)
        self.projects = {}  # id -> name
        self.created_projects, self.removed_projects = [], []
        self.created_datasets, self.removed_datasets = [], []
        self.image = FakeImageApi(self.datasets, rejects)
        if existing_project:
            pid, ds = existing_project
            self.projects[pid] = f"project {pid}"
            for ds_id, (name, parent, items) in ds.items():
                self.datasets[ds_id] = list(items)
                self.dataset_names[ds_id] = (pid, name, parent)
        self.output_project = None
        self.fields = {}
        self.project = SimpleNamespace(create=self._create_project, get_info_by_id=self._project_info,
                                       remove=self._remove_project)
        self.dataset = SimpleNamespace(create=self._create_dataset, get_info_by_name=self._ds_by_name,
                                       get_info_by_id=self._ds_info, get_list=self._ds_list,
                                       remove=self._remove_dataset)
        self.task = SimpleNamespace(set_fields=self._set_fields, set_output_project=self._set_output)
        self.app = SimpleNamespace(
            set_field=lambda task_id, field, payload: self.fields.__setitem__(field, payload),
            workflow=SimpleNamespace(add_output_project=lambda pid: None,
                                     add_output_dataset=lambda did: None),
        )
        self.is_version_supported = lambda v: True
        self.instance_version = "6.17.22"

    # projects
    def _create_project(self, workspace_id, name, type=None, change_name_if_conflict=False):
        pid = 100 + len(self.created_projects)
        self.projects[pid] = name
        self.created_projects.append(pid)
        return SimpleNamespace(id=pid, name=name)

    def _project_info(self, id):
        if id not in self.projects:
            return None
        items = sum(len(self.datasets[d]) for d, (p, _, _) in self.dataset_names.items() if p == id)
        return SimpleNamespace(id=id, name=self.projects[id], items_count=items)

    def _remove_project(self, id):
        self.projects.pop(id)
        self.removed_projects.append(id)

    # datasets
    def _create_dataset(self, project_id, name, change_name_if_conflict=False, parent_id=None, **kw):
        did = 1000 + len(self.dataset_names)
        self.datasets[did] = []
        self.dataset_names[did] = (project_id, name, parent_id)
        self.created_datasets.append(did)
        return SimpleNamespace(id=did, name=name, project_id=project_id)

    def _ds_info(self, id):
        p, name, parent = self.dataset_names[id]
        return SimpleNamespace(id=id, name=name, project_id=p, parent_id=parent,
                               items_count=len(self.datasets[id]))

    def _ds_list(self, project_id, filters=None, recursive=False, parent_id=None, **kw):
        res = []
        for d, (p, name, parent) in self.dataset_names.items():
            if p != project_id or (not recursive and parent != parent_id):
                continue
            if filters and any(f["field"] == "name" and f["value"] != name for f in filters):
                continue
            res.append(self._ds_info(d))
        return res

    def _ds_by_name(self, project_id, name, fields=None, parent_id=None):
        res = self._ds_list(project_id, [{"field": "name", "value": name}], parent_id=parent_id)
        return res[0] if len(res) == 1 else None

    def _remove_dataset(self, id):
        self.dataset_names.pop(id)
        self.datasets.pop(id)
        self.removed_datasets.append(id)

    def _set_fields(self, task_id, fields):
        for f in fields:
            self.fields[f["field"]] = f["payload"]

    def _set_output(self, task_id, project_id, project_name=None):
        self.output_project = project_id


def make_state(selected, bucket="bkt", add_mode="copyData", project_id=None, dataset_name=None):
    """GUI state as the template sends it; `selected` are viewer items (path, type)."""
    state = {
        "provider": "s3",
        "bucketName": bucket,
        "selected": [{"path": p, "type": t} for p, t in selected],
        "addMode": add_mode,
        "forceMetadata": True,
        "dstProjectMode": "newProject",
        "dstProjectName": "my_images",
        "dstProjectId": None,
        "dstDatasetMode": "newDataset",
        "dstDatasetName": "my_dataset",
        "selectedDatasetName": None,
    }
    if project_id is not None:
        state.update(dstProjectMode="existingProject", dstProjectId=project_id)
    if dataset_name is not None:
        state.update(dstDatasetMode="existingDataset", selectedDatasetName=dataset_name)
    return state


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Import the app with fakes; returns run(api, state) -> (main, g, error-or-None)."""
    import supervisely as sly

    monkeypatch.setenv("FAKE_APP_DATA_DIR", str(tmp_path / "app_data"))
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("TASK_ID", "1")
    monkeypatch.setenv("context.teamId", "8")
    monkeypatch.setenv("context.workspaceId", "9")
    monkeypatch.setattr(sly, "AppService", FakeAppService)
    holder = {}
    monkeypatch.setattr(sly.Api, "from_env", classmethod(lambda cls, *a, **k: holder["api"]))
    monkeypatch.syspath_prepend(SRC_DIR)

    def run(api, state):
        holder["api"] = api
        for mod in APP_MODULES:
            sys.modules.pop(mod, None)
        main = importlib.import_module("main")
        g = importlib.import_module("globals")
        error = None
        try:
            main.process(api, 1, {}, state, sly.logger)
        except Exception as e:  # the real AppService shows it and stops the task with an error
            error = e
        return main, g, error

    yield run
    for mod in APP_MODULES:
        sys.modules.pop(mod, None)
