import os
import posixpath

import supervisely as sly

import globals as g
import ui

import workflow as wf
import time


@g.app.callback("refresh_tree_viewer")
@sly.timeit
def refresh_tree_viewer(api: sly.Api, task_id, context, state, app_logger):
    new_path = state["viewerPath"]
    g.FILE_SIZE = {}

    path = f"{state['provider']}://{new_path.strip('/')}"
    try:
        files = api.remote_storage.list(path, recursive=False, limit=g.USER_PREVIEW_LIMIT + 1, team_id=g.TEAM_ID)
    except Exception as e:
        sly.logger.warn(repr(e))
        g.app.show_modal_window(
            "Can not find bucket or permission denied. Please, check if provider / bucket name are "
            "correct or contact tech support",
            level="warning",
        )
        fields = [
            {"field": "data.tree", "payload": None},
            {"field": "data.connecting", "payload": False},
            {"field": "state.viewerLoading", "payload": False},
        ]
        api.task.set_fields(task_id, fields)
        return

    files = [f for f in files if f["type"] == "folder" or (f["type"] == "file" and f["size"] > 0)]

    if len(files) > g.USER_PREVIEW_LIMIT:
        files.pop()
        g.app.show_modal_window(
            f"Found too many files. Showing the first {g.USER_PREVIEW_LIMIT} files"
        )

    tree_items = []
    for file in files:
        bucket_name = state["bucketName"].split("/")[0]
        path = os.path.join(f"/{bucket_name}", file["prefix"], file["name"])
        tree_items.append({"path": path, "size": file["size"], "type": file["type"]})
        g.FILE_SIZE[path] = file["size"]

    fields = [
        {"field": "data.tree", "payload": tree_items},
        {"field": "state.viewerLoading", "payload": False},
    ]
    api.task.set_fields(task_id, fields)


@g.app.callback("preview")
@sly.timeit
def preview(api: sly.Api, task_id, context, state, app_logger):
    g.FILE_SIZE = {}

    path = f"{state['provider']}://{state['bucketName']}"
    try:
        files = api.remote_storage.list(path, recursive=False, limit=g.USER_PREVIEW_LIMIT + 1, team_id=g.TEAM_ID)
    except Exception as e:
        sly.logger.warn(repr(e))
        g.app.show_modal_window(
            "Can not find bucket or permission denied. Please, check if provider / bucket name are "
            "correct or contact tech support",
            level="warning",
        )
        fields = [
            {"field": "data.tree", "payload": None},
            {"field": "data.connecting", "payload": False},
        ]
        api.task.set_fields(task_id, fields)
        return

    files = [f for f in files if f["type"] == "folder" or (f["type"] == "file" and f["size"] > 0)]

    if len(files) > g.USER_PREVIEW_LIMIT:
        files.pop()
        g.app.show_modal_window(
            f"Found too many files. Showing the first {g.USER_PREVIEW_LIMIT} files"
        )

    tree_items = []
    for file in files:
        path = os.path.join(
            f"/{state['bucketName']}", file["name"]
        )  # file["prefix"], file["name"])
        tree_items.append({"path": path, "size": file["size"], "type": file["type"]})
        g.FILE_SIZE[path] = file["size"]

    fields = [
        {"field": "data.tree", "payload": tree_items},
        {"field": "data.connecting", "payload": False},
    ]
    api.task.set_fields(task_id, fields)


@g.app.callback("process")
@sly.timeit
def process(api: sly.Api, task_id, context, state, app_logger):
    start_time = time.time()
    paths = state["selected"]
    remote_paths = []
    widget_paths = []
    local_paths = []

    added_paths = set()
    skipped_unsupported = []
    # "Bucket name" may be a path that starts with the bucket name ("bucket/sub/dir"), while
    # listed objects have a prefix relative to the bucket root.
    bucket_name = state["bucketName"].strip("/").split("/")[0]

    def _add_to_processing_list(path):
        nonlocal remote_paths, local_paths
        if path in added_paths:  # a file selected both directly and inside a selected folder
            return
        added_paths.add(path)
        if sly.image.has_valid_ext(path) is False:
            sly.logger.warning(f"Unsupported image extension for path: {path}")
            skipped_unsupported.append(path)
            return
        full_remote_path = f"{state['provider']}://{path.lstrip('/')}"
        remote_paths.append(full_remote_path)
        widget_paths.append(path)
        # Bucket keys may contain "..", or be longer than a local file name may be:
        # the local copy gets a name of its own inside the app temp dir.
        local_path = safe_local_path(g.app.data_dir, len(local_paths), path)
        local_paths.append(local_path)

    # find selected dirs
    selected_dirs = []
    not_found = []  # selected items that can not be imported: (path, reason)
    for path in paths:
        if path["type"] == "folder":
            if "/" not in path["path"].strip("/"):
                # A folder with an empty name (keys that start with "/") is shown as
                # "/<bucket>/"; listing it would list - and import - the whole bucket.
                sly.logger.warning(f"Folder with an empty name is skipped: {path['path']!r}")
                not_found.append((path["path"], "a folder with an empty name can not be listed"))
                continue
            # path to directory
            selected_dirs.append(path["path"])

    # get all files from selected dirs
    if len(selected_dirs) > 0:
        g.FILE_SIZE = {}
        for dir_path in selected_dirs:
            full_dir_path = f"{state['provider']}://{dir_path.strip('/')}"
            files_cnt = 0

            for file in list_objects(api, full_dir_path):
                if file["size"] <= 0:
                    continue

                path = posixpath.join(f"/{bucket_name}", file["prefix"], file["name"])
                g.FILE_SIZE[path] = file["size"]
                files_cnt += 1
                if files_cnt % 10000 == 0:
                    sly.logger.info(f"Listing files from remote storage {files_cnt}")

        for path in g.FILE_SIZE.keys():
            if path in selected_dirs:
                continue
            if path.startswith(tuple(selected_dirs)):
                _add_to_processing_list(path)

    # get other selected files
    if g.FILE_SIZE is None:
        g.FILE_SIZE = {}
    for path in paths:
        if path["type"] == "file":
            full_remote_path = f"{state['provider']}://{path['path'].lstrip('/')}"
            try:
                file = api.remote_storage.get_file_info_by_path(path=full_remote_path, team_id=g.TEAM_ID)
            except Exception as e:  # the SDK raises IndexError when nothing is found
                sly.logger.warn(f"Couldn't process file path: '{full_remote_path}'. Error: {e}")
                not_found.append((path["path"], "not found in the storage"))
                continue
            g.FILE_SIZE[path["path"]] = file["size"]
            _add_to_processing_list(path["path"])

    if len(local_paths) == 0:
        g.app.show_modal_window("There are no images to import", "warning")
        sly.logger.warn("nothing to download")
        api.app.set_field(task_id, "data.processing", False)
        return

    project, dataset, created = None, None, []
    try:
        project, dataset, created = get_destination(api, state)
    finally:
        if dataset is None:
            api.app.set_field(task_id, "data.processing", False)
    if dataset is None:
        return

    if state["dstDatasetMode"] == "existingDataset":
        all_images_names = {
            img_info.name
            for img_info in api.image.get_list(
                dataset_id=dataset.id, force_metadata_for_links=False
            )
        }
    else:
        all_images_names = set()

    if state["addMode"] == "copyData":
        g.BATCH_SIZE = 50

    progress_items_cb = ui.get_progress_cb(api, task_id, 1, "Finished", len(remote_paths))

    imported = 0
    failed = list(not_found)  # (path shown in the viewer, reason)
    planned = len(remote_paths) + len(not_found)
    free_name_time = 0
    for batch_remote_paths, batch_temp_paths, batch_local_paths in zip(
        sly.batched(remote_paths, batch_size=g.BATCH_SIZE),
        sly.batched(widget_paths, batch_size=g.BATCH_SIZE),
        sly.batched(local_paths, batch_size=g.BATCH_SIZE),
    ):
        start_name_generation = time.time()
        images_names = [
            free_name(all_images_names, posixpath.basename(temp_path))
            for temp_path in batch_temp_paths
        ]
        free_name_time += time.time() - start_name_generation

        if state["addMode"] == "addByLink":
            imported += upload_with_fallback(
                lambda names, links: api.image.upload_links(
                    dataset.id,
                    names=names,
                    links=links,
                    batch_size=g.BATCH_SIZE,
                    force_metadata_for_links=state["forceMetadata"],
                    skip_validation=True,
                ),
                images_names,
                batch_remote_paths,
                batch_temp_paths,
                failed,
            )
        elif state["addMode"] == "copyData":
            ready = []  # (name, local path, viewer path) of downloaded files
            try:
                for name, remote_path, temp_path, local_path in zip(
                    images_names, batch_remote_paths, batch_temp_paths, batch_local_paths
                ):
                    progress_file_cb = ui.get_progress_cb(
                        api,
                        task_id,
                        2,
                        "Downloading to temp dir: {!r} ".format(temp_path),
                        g.FILE_SIZE[temp_path],
                        is_size=True,
                    )
                    try:
                        api.remote_storage.download_path(
                            remote_path, local_path, progress_file_cb, team_id=g.TEAM_ID
                        )
                    except Exception as e:
                        sly.logger.warning(f"Failed to download {temp_path!r}: {e!r}")
                        failed.append((temp_path, f"download failed: {e!r}"))
                        continue
                    ready.append((name, local_path, temp_path))
                    temp_cb = ui.get_progress_cb(
                        api,
                        task_id,
                        2,
                        "Processing: {!r} ".format(temp_path),
                        1,
                        is_size=False,
                        func=ui.set_progress,
                    )
                    temp_cb(1)
                if ready:
                    imported += upload_with_fallback(
                        lambda names, paths: api.image.upload_paths(
                            dataset.id, names=names, paths=paths
                        ),
                        [r[0] for r in ready],
                        [r[1] for r in ready],
                        [r[2] for r in ready],
                        failed,
                    )
            finally:
                for local_path in batch_local_paths:
                    sly.fs.silent_remove(local_path)
        progress_items_cb(len(images_names))

    ui.reset_progress(api, task_id, 1)
    ui.reset_progress(api, task_id, 2)
    sly.logger.info(f"Name generation time --- {free_name_time} seconds ---")
    sly.logger.info(f"Total time --- {time.time() - start_time} seconds ---")
    sly.logger.info(
        "Import summary",
        extra={"planned": planned, "imported": imported, "failed": len(failed),
               "skipped_unsupported": len(skipped_unsupported)},
    )

    if imported == 0:
        remove_if_empty(api, created)
        message = (
            f"No images were imported: all {planned} selected images failed. "
            + describe_failures(failed)
        )
        g.app.show_modal_window(message, "error")
        raise RuntimeError(message)

    api.task.set_output_project(task_id, project.id, project.name)
    # -------------------------------------- Add Workflow Output ------------------------------------- #
    workflow = wf.Workflow(api)
    workflow.add_output(project.id)
    # ----------------------------------------------- - ---------------------------------------------- #

    if failed:
        message = (
            f"Import is incomplete: {len(failed)} of {planned} images failed, "
            f'{imported} were imported to the project "{project.name}", dataset "{dataset.name}". '
            + describe_failures(failed)
        )
        g.app.show_modal_window(message, "error")
        raise RuntimeError(message)

    skipped_note = ""
    if skipped_unsupported:
        skipped_note = (
            f" {len(skipped_unsupported)} file(s) skipped: not a supported image extension"
            f" (see the app log)."
        )
    g.app.show_modal_window(
        f'{imported} images has been successfully imported to the project "{project.name}"'
        f', dataset "{dataset.name}".{skipped_note} You can continue importing other images to the '
        f"same or new project. If you've finished with the app, stop it manually."
    )
    api.app.set_field(task_id, "data.processing", False)


def get_destination(api: sly.Api, state: dict):
    """Returns (project, dataset, created) for the GUI choice; `created` lists what this run created
    as ("project" | "dataset", id). Shows an error and returns dataset None if the choice is gone."""
    created = []
    project = None
    if state["dstProjectMode"] == "newProject":
        project = api.project.create(
            g.WORKSPACE_ID,
            state["dstProjectName"],
            sly.ProjectType.IMAGES,
            change_name_if_conflict=True,
        )
        created.append(("project", project.id))
    elif state["dstProjectMode"] == "existingProject":
        project = api.project.get_info_by_id(state["dstProjectId"])
    if project is None:
        message = f"Result project (id {state.get('dstProjectId')}) is not found. Select another project."
        sly.logger.error(message)
        g.app.show_modal_window(message, "error")
        return None, None, created

    dataset = None
    if state["dstDatasetMode"] == "newDataset":
        dataset = api.dataset.create(
            project.id, state["dstDatasetName"], change_name_if_conflict=True
        )
        created.append(("dataset", dataset.id))
    elif state["dstDatasetMode"] == "existingDataset":
        name = state["selectedDatasetName"]
        dataset = api.dataset.get_info_by_name(project.id, name)
        if dataset is None:  # a nested dataset: look in the whole tree, use it if the name is unique
            matches = [
                ds
                for ds in api.dataset.get_list(
                    project.id, filters=[{"field": "name", "operator": "=", "value": name}],
                    recursive=True,
                )
                if ds.name == name
            ]
            dataset = matches[0] if len(matches) == 1 else None
    if dataset is None:
        message = (
            f'Result dataset "{state.get("selectedDatasetName")}" is not found (or its name is not '
            f'unique) in the project "{project.name}". Select another dataset.'
        )
        sly.logger.error(message)
        g.app.show_modal_window(message, "error")
        remove_if_empty(api, created)
        return project, None, created
    return project, dataset, created


def upload_with_fallback(upload, names, sources, paths, failed) -> int:
    """Uploads one batch; if the batch fails, uploads its halves separately (down to single items)
    so that one bad file does not fail the others. Records failures in `failed`; returns the number
    of uploaded items."""
    try:
        upload(names, sources)
        return len(names)
    except Exception as e:
        if len(names) == 1:
            sly.logger.warning(f"Failed to import {paths[0]!r}: {e!r}")
            failed.append((paths[0], repr(e)))
            return 0
        sly.logger.warning(f"Batch of {len(names)} images failed ({e!r}), retrying in parts")
    half = len(names) // 2
    return upload_with_fallback(
        upload, names[:half], sources[:half], paths[:half], failed
    ) + upload_with_fallback(upload, names[half:], sources[half:], paths[half:], failed)


def describe_failures(failed, limit: int = 5) -> str:
    shown = "; ".join(f"{path}: {reason}" for path, reason in failed[:limit])
    more = f"; and {len(failed) - limit} more (see the app log)" if len(failed) > limit else ""
    return f"Failed: {shown}{more}."


def remove_if_empty(api: sly.Api, created) -> None:
    """Removes what this run created (the project, else the dataset), only if the server reports
    it empty. Projects and datasets the user selected are never removed."""
    kinds = dict(created)
    kind = "project" if "project" in kinds else "dataset" if "dataset" in kinds else None
    if kind is None:
        return
    module = api.project if kind == "project" else api.dataset
    try:
        info = module.get_info_by_id(kinds[kind])
        if info is not None and info.items_count == 0:
            module.remove(kinds[kind])
            sly.logger.info(f"Removed the empty {kind} {kinds[kind]} created by this import")
    except Exception as e:
        sly.logger.warning(f"Could not remove the empty {kind} {kinds[kind]}: {e!r}")


# TODO
# large folder
# non recursive import
# SDK version
# limit list
# list with pagination


def safe_local_path(data_dir: str, index: int, remote_path: str) -> str:
    """Local download path for a remote file: always directly inside `data_dir/downloads`."""
    ext = sly.fs.get_file_ext(posixpath.basename(remote_path))
    if len(ext) > 16 or "/" in ext or "\\" in ext:
        ext = ""
    local_path = os.path.join(data_dir, "downloads", f"{index:08d}{ext}")
    sly.fs.ensure_base_path(local_path)
    return local_path


def free_name(used_names: set, name: str) -> str:
    """`name`, or `name_01.ext`, `name_02.ext`, ... if taken; adds the result to `used_names`.

    Same names as sly.utils.generate_free_name(with_ext=True), without copying the set on every
    check (that made name generation quadratic for large imports).
    """
    res = name
    suffix = 1
    stem, ext = sly.fs.get_file_name(name), sly.fs.get_file_ext(name)
    while res in used_names:
        res = f"{stem}_{suffix:02d}{ext}"
        suffix += 1
    used_names.add(res)
    return res


def list_objects(api, full_dir_path):
    start_after = None
    last_obj = None
    while True:
        remote_objs = api.remote_storage.list(
            path=full_dir_path,
            files=True,
            folders=False,
            recursive=True,
            start_after=start_after,
            team_id=g.TEAM_ID,
        )
        if len(remote_objs) == 0:
            break
        if last_obj is not None:
            if remote_objs[-1] == last_obj:
                break
        last_obj = remote_objs[-1]
        start_after = f'{last_obj["prefix"]}/{last_obj["name"]}'
        yield from remote_objs


def main():
    data = {}
    state = {}

    ui.init_context(data, g.TEAM_ID, g.WORKSPACE_ID)
    ui.init_connection(data, state)
    ui.init_options(data, state)
    ui.init_progress(data, state)

    g.app.run(data=data, state=state)


if __name__ == "__main__":
    sly.main_wrapper("main", main)
