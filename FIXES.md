# import-images-from-cloud-storage: fixes 2026-10

Branch `ecosystem-fixes-2026-10` from `master` (b26e24c, released as v1.5.2). Legacy GUI app
(`AppService` + `gui_template`): targeted fixes and the image move only, no rewrite.

## Behaviour contract

- **Started from:** Ecosystem / app list, in a workspace (`context.teamId`, `context.workspaceId`).
  Long-running GUI session; the user stops it.
- **GUI state keys (unchanged):** `provider` (`s3`, `google`, `azure`, `fs`, ... - only providers
  connected to the instance), `bucketName` (a bucket, or a path that starts with the bucket name),
  `selected` (file viewer items: `{path: "/<bucket>/<key>", type: file|folder}`), `addMode`
  (`copyData` | `addByLink`), `forceMetadata` (link mode: server downloads each image once for
  hash/size/mimetype), `dstProjectMode` (`newProject` | `existingProject`), `dstProjectName`,
  `dstProjectId`, `dstDatasetMode` (`newDataset` | `existingDataset`), `dstDatasetName`,
  `selectedDatasetName`.
- **Commands:** `preview` (Connect: lists up to 100 items of the bucket / sub-path),
  `refresh_tree_viewer` (open a folder), `process` (Start import).
- **Import:** a selected folder imports every file with a supported image extension under it
  (recursive, listed page by page); selected files are imported as they are. All go into one
  dataset; names are the key's base name, made unique (`1.jpg`, `1_01.jpg`).
  - `copyData`: download to the agent, upload in batches of 50, delete the local copies.
  - `addByLink`: `images.bulk.add` with `s3://bucket/key` links, batches of 10,000.
- **Output:** the project as the task output project and workflow output; a modal with the count.
  The app never writes to, moves or deletes anything in the cloud storage. Credentials stay on the
  instance: the app only sees provider names, protocols and bucket names, and logs none of it.
- **Result:** all imported -> info modal, session stays open for more imports. Some or all failed
  -> error modal and the task ends with an error (see below).

## Fixed

| Commit | Problem | Tests old -> new |
|---|---|---|
| ca62fea | Copy mode wrote the local copy to `data_dir/<bucket>/<key>`: keys with `..` escaped the data dir (overwrite any image-extension file in the container), file names > 255 bytes crashed with `OSError`, downloaded files were never deleted (disk filled by large imports); name generation was quadratic. | 3 of 4 fail -> 4/4 |
| c1dc9b8 | With a sub-path in the bucket field (`bkt/sub`), files of selected folders were built as `/bkt/sub/sub/...` and silently dropped ("no images to import", or success with only the selected files). A file selected twice was imported twice. | 3 of 5 fail -> 9/9 total |
| af3eb13 | One failing file (download error, server refusing one image of a 50-image batch) aborted the whole import, leaving a partly filled or empty new project. Missing destination project/dataset (or a nested dataset) left "Start import" spinning with no message. Skipped unsupported files were not mentioned. | 8 of 9 fail -> 18/18 total |
| f65a34e | Image move (below), plus an AppService runtime test. | runtime test fails without protobuf |
| 319d596 | A selected file that no longer exists was dropped and the import reported success. | 1 of 1 fails -> 20/20 total |
| 1d6e6b6 | A folder with an empty name (keys starting with `/`; present in dev bucket `remote-img-test`) has path `/<bucket>/`: selecting it imported the whole bucket. | 1 of 1 fails -> 21/21 total |

Offline tests: `python -m pytest tests` (fake `sly.Api`, `AppService` and cloud storage; no
server). Run with supervisely 6.74.34 on Python 3.14.3 (macOS) and inside the per-app image built
locally from `workflows/docker/hardened/Dockerfile.tmpl` (linux/amd64, Python 3.14.7): 21 passed.

## Intentional behaviour changes

- **Per-item failures no longer abort the import.** The rest is imported; a failed upload batch is
  retried in halves down to single images.
- **A partial import ends the task with an error.** Output project and workflow output are set
  first, then an error modal with the counts and the first five failed paths is shown and the
  callback raises; `AppService` stops the session with an error. Before, any failure crashed the
  session immediately (also an error), so only the "rest is imported" part is new.
- **Nothing imported -> the project (or dataset) this run created is removed** if the server
  reports it empty, then error modal and task error. Projects and datasets the user selected are
  never removed.
- Missing destination: error modal and the button is unlocked (was: endless spinner).
- An existing nested dataset is found by a recursive lookup if its name is unique in the project.
- Success modal adds "N file(s) skipped: not a supported image extension" when files were skipped.
- Missing selected files and empty-name folders count as failures.
- Local temp names are `downloads/<index><ext>`; image names in Supervisely are unchanged.
- `print` timing lines are now `sly.logger.info`.

## Found but not fixed

- Keys that start with `/` (e.g. `/a.jpg`) cannot be addressed: the viewer path drops the bucket
  (`os.path.join` with an absolute prefix) and the SDK strips the `/` of list paths. Such files
  are now reported as failures when selected through an empty-name folder, not imported.
- The viewer shows only the first 100 entries of a folder; files beyond that can only be imported
  by selecting their parent folder (existing UX limit, `USER_PREVIEW_LIMIT`).
- Copy mode updates the progress widgets with 2-3 `task.set_fields` calls per file; slow for very
  large imports, not wrong.
- A quota error (`PaymentRequired`) is retried item by item like any other failure instead of
  stopping at once.
- If `images.bulk.add` were not atomic, a failed batch retried in halves could report an image as
  failed that the first attempt did add (name conflict). Not observed; the server treats a batch
  as one request.
- `refresh_tree_viewer`/`preview` warn with `repr(e)` of listing errors (server messages, no
  credentials); left as is.

## Image

`supervisely/import-export:6.74.34` (sdk_legacy) -> `supervisely/import-images-from-cloud-storage:6.74.34`,
a per-app image from `build_image_from_template.yml` on `base-py-sdk-hardened:6.74.34`
(Python 3.14) with `dev_requirements.txt` = `supervisely==6.74.34` + `protobuf==3.20.3`.

- **Why not the bare hardened base:** the legacy `AppService` receives GUI commands as protobuf
  messages; `base-py-sdk-hardened` has no protobuf (`ModuleNotFoundError: No module named
  'google'`), so the GUI would never answer. Checked with `docker run` on the image.
  `protobuf==3.20.3` is the SDK's `agent` extra pin and works (pure Python) on 3.14;
  `tests/test_runtime.py` runs a real `AppService` loop through protobuf messages.
- SDK stays 6.74.34: the newest allowed for `instance_version` 6.17.22 (`versions.json`:
  6.17.22 -> [6.74.29, 6.74.35)).
- CI: `release.yml` **and `release_branch.yml`** run `build-image` before the release (skipped
  when the tag exists); `build_app_image.yml` added for manual builds.

## Dev-check plan

Start each case with
`uv run ecosystem-fleet/fleet.py run import-images-from-cloud-storage --workspace 733 --version ecosystem-fixes-2026-10 --branch --no-wait`
and the same without `--version/--branch` (published v1.5.2) for comparison, then use the session
GUI. Provider/bucket below are connected to team 1 (workspace 733) on dev. Delete the projects
the checks create afterwards.

| # | GUI steps | Expected on the branch | Published v1.5.2 |
|---|---|---|---|
| 1 | Amazon S3, `remote-img-test`, Connect; select folders `a` and `SAMPLE_PNG_IMAGES`; copy; new project | all images imported, info modal with the count; project is task output; no files left in the session data dir | same |
| 2 | Bucket field `remote-img-test/a`, Connect; select folder `b`; copy | 2 images (`image.jpg`, `image-upload1.jpg`) | "There are no images to import" |
| 3 | `remote-img-test`; select folders `broken` (3 four-byte jpegs) and `a`; copy | 2 imported, error modal "Import is incomplete: 3 of 5 images failed", task ends with an error, project kept | task crashes on the first batch, 0 imported, empty project left |
| 4 | `remote-img-test`; select only `broken`; copy | "No images were imported", no project left, task error | task error, empty project `my_images` left |
| 5 | Same as 1 with "add by link", Data validation on | images added by link, open in the labeling tool | same |
| 6 | Run 5 again into the same existing project and dataset | names get `_01` suffixes, success | same |
| 7 | `remote-img-test`; select the blank-named folder at the top of the list and file `a/b/image.jpg` (open `a`, `b` first) | 1 imported, error modal naming `/remote-img-test/` | **do not run**: imports the whole bucket |
| 8 | Google Cloud Storage `sly-dev-test`, folder `test_img` (has sub-folder `ds0_007`); copy | 8 images | same |
| 9 | Existing project from case 1 -> create a nested dataset in it in the UI, then import `a` into "existing dataset" = the nested one | 2 images in the nested dataset | spinner never stops, no message (if the selector offers nested datasets) |

## Branch image (test tag)

On this branch `config.json` uses `supervisely/import-images-from-cloud-storage:test-f5c839ed`. `release_branch.yml` follows
`workflows/templates/build_release_branch.yml`: on push it builds that tag, named by the sha256 of
`dev_requirements.txt`, and only if the tag is not on Docker Hub yet. Dev agents pull images "if not present", so
every dependency change gets a new tag. **Before merging, set `docker_image` back to `supervisely/import-images-from-cloud-storage:6.74.34`**; `release.yml`
builds that tag on the version release.

## Process exit on Python 3.14 (2026-10-28)

`AppService._shutdown` releases executor threads through `thread._tstate_lock`, which Python 3.13+ no longer has.
The consumer thread stays blocked on the agent stream, and the interpreter waits for it at exit. This was seen on dev
in import-dicom-studies, where the task stayed `started` after a finished import. Here the same would keep the
container alive after the session is stopped. The app now ends with `os._exit(0)` after `main_wrapper`, which
already uses `os._exit(1)` on errors. `tests/test_exit.py` reproduces the hang in a subprocess.
