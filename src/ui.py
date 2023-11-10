from functools import partial
import supervisely as sly
import globals as g


# def get_available_providers_list():
# available_providers = g.api.remote_storage.get_list_available_providers()


def init_context(data, team_id, workspace_id):
    data["teamId"] = team_id
    data["workspaceId"] = workspace_id


def init_connection(data, state):
    all_providers_info = g.api.remote_storage.get_list_supported_providers()

    providers_info = g.api.remote_storage.get_list_available_providers()
    providers = [provider["defaultProtocol"].rstrip(":") for provider in providers_info]

    provider_items = []
    disabled_items = []
    disabled_items_names = []
    for provider in all_providers_info:
        if provider["defaultProtocol"].rstrip(":") in providers:
            item = {
                "value": provider["defaultProtocol"].rstrip(":"),
                "label": provider["name"],
                "disabled": False,
            }
            provider_items.append(item)
        else:
            item = {
                "value": provider["defaultProtocol"].rstrip(":"),
                "label": provider["name"],
                "disabled": True,
            }
            disabled_items.append(item)
            disabled_items_names.append(item["label"])

    provider_items.extend(disabled_items)

    state["availableProviders"] = provider_items
    state["unavailableProviders"] = disabled_items
    state["unavailableProvidersNames"] = disabled_items_names

    data["availableBuckets"] = {
        provider["defaultProtocol"].rstrip(":"): provider["buckets"] for provider in providers_info
    }

    if len(providers) == 0:
        state["provider"] = ""
        state["buckets"] = []
    else:
        state["provider"] = providers[0]  # s3 google azure fs
        state["buckets"] = data["availableBuckets"][providers[0]]

    state["bucketName"] = ""  # "bucket-test-export" "remote-img-test"
    state["selected"] = ""
    state["viewerLoading"] = False
    data["tree"] = None
    data["connecting"] = False
    state["viewerPath"] = ""

    data["notificationBox"] = {
        "options": {"type": "info", "showIcon": False, "colorize": False, "hideBorder": True}
    }
    if len(provider_items) == 0:
        data["notificationMessage"] = {
            "title": "Cloud Storage Connection Required",
            "description1": (
                "No cloud storage providers are configured. Set up a provider in the instance settings to proceed. "
                "Please connect a provider to your instance using this "
            ),
            "description2": (
                "You can connect Amazon S3, Microsoft Azure, Google Cloud Storage or any S3 compatible providers. "
                "If you have any questions, please contact tech support."
            ),
            "box_type": "info",
        }

    elif len(disabled_items) > 0:
        data["notificationMessage"] = {
            "title": "Configure Cloud Storage provider in the instance settings",
            "description1": (
                "You can set up a new provider in the instance settings. "
                "To connect a new provider to your instance follow this "
            ),
            "description2": (
                f"You can connect {', '.join(disabled_items_names)} or any S3 compatible providers. "
                "If you have any questions, please contact tech support."
            ),
            "box_type": "info",
        }
    else:
        data["notificationMessage"] = None


def init_options(data, state):
    state["addMode"] = "copyData"  # "addByLink"
    state["forceMetadata"] = True

    state["dstProjectMode"] = "newProject"
    state["dstProjectName"] = "my_images"
    state["dstProjectId"] = None

    state["dstDatasetMode"] = "newDataset"
    state["dstDatasetName"] = "my_dataset"
    state["selectedDatasetName"] = None

    data["processing"] = False


def init_progress(data, state):
    data["progressName1"] = None
    data["currentProgressLabel1"] = 0
    data["totalProgressLabel1"] = 0
    data["currentProgress1"] = 0
    data["totalProgress1"] = 0


def reset_progress(api, task_id, index):
    _set_progress(index, api, task_id, None, 0, 0, 0, 0)


def _set_progress(index, api, task_id, message, current_label, total_label, current, total):
    fields = [
        {"field": f"data.progressName{index}", "payload": message},
        {"field": f"data.currentProgressLabel{index}", "payload": current_label},
        {"field": f"data.totalProgressLabel{index}", "payload": total_label},
        {"field": f"data.currentProgress{index}", "payload": current},
        {"field": f"data.totalProgress{index}", "payload": total},
    ]
    api.task.set_fields(task_id, fields)


def _update_progress_ui(api, task_id, progress: sly.Progress, index):
    _set_progress(
        index,
        api,
        task_id,
        progress.message,
        progress.current_label,
        progress.total_label,
        progress.current,
        progress.total,
    )


def update_progress(count, index, api: sly.Api, task_id, progress: sly.Progress):
    # hack slight inaccuracies in size convertion
    count = min(count, progress.total - progress.current)
    progress.iters_done(count)
    if progress.need_report():
        progress.report_progress()
        _update_progress_ui(api, task_id, progress, index)


def set_progress(current, index, api: sly.Api, task_id, progress: sly.Progress):
    # if current > progress.total:
    #    current = progress.total
    old_value = progress.current
    delta = current - old_value
    update_progress(delta, index, api, task_id, progress)


def get_progress_cb(api, task_id, index, message, total, is_size=False, func=update_progress):
    progress = sly.Progress(message, total, is_size=is_size)
    progress_cb = partial(func, index=index, api=api, task_id=task_id, progress=progress)
    progress_cb(0)
    return progress_cb
