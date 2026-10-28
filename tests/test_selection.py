"""What gets imported for a selection in the file viewer."""

from conftest import FakeApi, make_state


def test_folder_selected_under_bucket_subpath(app):
    # "Bucket name" accepts a path that starts with the bucket name, e.g. "bkt/sub".
    api = FakeApi({"bkt/sub/dir/1.jpg": 3, "bkt/sub/dir/deep/2.png": 3, "bkt/sub/other/3.jpg": 3})
    main, g, error = app(api, make_state([("/bkt/sub/dir", "folder")], bucket="bkt/sub"))
    assert error is None
    assert sorted(api.datasets[api.created_datasets[0]]) == ["1.jpg", "2.png"]


def test_preview_paths_of_bucket_subpath_are_importable(app):
    api = FakeApi({"bkt/sub/dir/1.jpg": 3, "bkt/sub/top.jpg": 3})
    state = make_state([], bucket="bkt/sub")
    main, g, _ = app(api, state)  # import only; nothing selected
    main.preview(api, 1, {}, state, None)
    tree = api.fields["data.tree"]
    assert sorted((t["path"], t["type"]) for t in tree) == [
        ("/bkt/sub/dir", "folder"), ("/bkt/sub/top.jpg", "file")]
    state["selected"] = tree
    main.process(api, 1, {}, state, None)
    assert sorted(api.datasets[api.created_datasets[0]]) == ["1.jpg", "top.jpg"]


def test_large_folder_is_listed_page_by_page(app):
    api = FakeApi({f"bkt/x/{i:05d}.jpg": 1 for i in range(25)}, page_size=10)
    main, g, error = app(api, make_state([("/bkt/x", "folder")], add_mode="addByLink"))
    assert error is None
    assert len(api.datasets[api.created_datasets[0]]) == 25


def test_file_selected_twice_is_imported_once(app):
    api = FakeApi({"bkt/x/1.jpg": 3, "bkt/x/2.jpg": 3})
    state = make_state([("/bkt/x", "folder"), ("/bkt/x/1.jpg", "file")])
    main, g, error = app(api, state)
    assert error is None
    assert sorted(api.datasets[api.created_datasets[0]]) == ["1.jpg", "2.jpg"]


def test_link_mode_uses_bucket_links(app):
    api = FakeApi({"bkt/x/1.jpg": 3})
    main, g, error = app(api, make_state([("/bkt/x", "folder")], add_mode="addByLink"))
    assert error is None
    assert api.image.calls == [("links", ["1.jpg"], ["s3://bkt/x/1.jpg"])]
    assert api.remote_storage.downloads == []


def test_folder_with_empty_name_does_not_import_the_whole_bucket(app):
    # a key "/a.jpg" makes the viewer show a folder with an empty name: "/bkt/"
    api = FakeApi({"bkt//a.jpg": 3, "bkt/x/1.jpg": 3, "bkt/y/2.jpg": 3})
    main, g, error = app(api, make_state([("/bkt/", "folder"), ("/bkt/x/1.jpg", "file")]))
    assert api.datasets[api.created_datasets[0]] == ["1.jpg"]
    assert error is not None and "/bkt/" in str(error)
