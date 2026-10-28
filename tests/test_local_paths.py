"""Downloaded files stay inside the app's temp dir, whatever the bucket keys look like."""

import os

from conftest import FakeApi, make_state


def _files_under(root):
    return [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs]


def test_key_with_dotdot_is_not_written_outside_data_dir(app, tmp_path):
    # S3 keys are arbitrary strings: "x/../../../escaped.jpg" is a valid key.
    api = FakeApi({"bkt/x/ok.jpg": 3, "bkt/x/../../../escaped.jpg": 3})
    main, g, error = app(api, make_state([("/bkt/x", "folder")]))
    assert error is None
    data_dir = os.path.realpath(g.app.data_dir)
    for p in api.remote_storage.downloads:
        assert os.path.realpath(p).startswith(data_dir + os.sep), p
    assert not (tmp_path / "escaped.jpg").exists()
    assert sorted(api.datasets[api.created_datasets[0]]) == ["escaped.jpg", "ok.jpg"]


def test_long_key_name_is_imported(app):
    long_name = "a" * 300 + ".jpg"  # longer than the 255-byte local file name limit
    api = FakeApi({f"bkt/x/{long_name}": 3, "bkt/x/short.jpg": 3})
    main, g, error = app(api, make_state([("/bkt/x", "folder")]))
    assert error is None
    assert sorted(api.datasets[api.created_datasets[0]]) == sorted([long_name, "short.jpg"])


def test_downloaded_files_are_removed_after_upload(app):
    api = FakeApi({f"bkt/x/{i}.jpg": 3 for i in range(120)})
    main, g, error = app(api, make_state([("/bkt/x", "folder")]))
    assert error is None
    assert len(api.datasets[api.created_datasets[0]]) == 120
    assert _files_under(g.app.data_dir) == []


def test_same_file_name_in_two_folders_gets_unique_names(app):
    api = FakeApi({"bkt/x/a/1.jpg": 3, "bkt/x/b/1.jpg": 3})
    main, g, error = app(api, make_state([("/bkt/x", "folder")]))
    assert error is None
    assert sorted(api.datasets[api.created_datasets[0]]) == ["1.jpg", "1_01.jpg"]
