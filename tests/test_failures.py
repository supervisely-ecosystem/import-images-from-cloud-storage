"""Partial and failed imports are reported as failures and leave no empty project behind."""

from conftest import FakeApi, make_state

FILES = {"bkt/x/1.jpg": 3, "bkt/x/2.jpg": 3, "bkt/x/3.jpg": 3}


def _error_modals(g):
    return [m for m, level in g.app.modals if level == "error"]


def test_download_failure_imports_the_rest_and_fails(app):
    api = FakeApi(FILES, download_fails=["bkt/x/2.jpg"])
    main, g, error = app(api, make_state([("/bkt/x", "folder")]))
    assert sorted(api.datasets[api.created_datasets[0]]) == ["1.jpg", "3.jpg"]
    assert error is not None and "1 of 3" in str(error)
    assert "/bkt/x/2.jpg" in str(error)
    assert api.output_project == api.created_projects[0]
    assert _error_modals(g)
    assert not any("successfully" in m for m, _ in g.app.modals)


def test_server_rejecting_one_image_keeps_the_rest_of_the_batch(app):
    api = FakeApi(FILES, rejects=["2.jpg"])
    main, g, error = app(api, make_state([("/bkt/x", "folder")]))
    assert sorted(api.datasets[api.created_datasets[0]]) == ["1.jpg", "3.jpg"]
    assert error is not None and "1 of 3" in str(error)


def test_link_mode_rejection_keeps_the_rest(app):
    api = FakeApi(FILES, rejects=["3.jpg"])
    main, g, error = app(api, make_state([("/bkt/x", "folder")], add_mode="addByLink"))
    assert sorted(api.datasets[api.created_datasets[0]]) == ["1.jpg", "2.jpg"]
    assert error is not None and "1 of 3" in str(error)


def test_nothing_imported_removes_the_new_project(app):
    api = FakeApi(FILES, download_fails=list(FILES))
    main, g, error = app(api, make_state([("/bkt/x", "folder")]))
    assert error is not None and "No images were imported" in str(error)
    assert api.removed_projects == api.created_projects == [100]
    assert api.output_project is None


def test_nothing_imported_into_existing_project_removes_only_the_new_dataset(app):
    api = FakeApi(FILES, rejects=["1.jpg", "2.jpg", "3.jpg"],
                  existing_project=(7, {70: ("ds", None, ["old.jpg"])}))
    main, g, error = app(api, make_state([("/bkt/x", "folder")], project_id=7))
    assert error is not None
    assert api.removed_projects == []
    assert api.removed_datasets == api.created_datasets and len(api.created_datasets) == 1
    assert api.datasets[70] == ["old.jpg"]


def test_nothing_imported_into_existing_dataset_removes_nothing(app):
    api = FakeApi(FILES, rejects=["1.jpg", "2.jpg", "3.jpg"],
                  existing_project=(7, {70: ("ds", None, [])}))
    main, g, error = app(api, make_state([("/bkt/x", "folder")], project_id=7, dataset_name="ds"))
    assert error is not None
    assert api.removed_projects == [] and api.removed_datasets == []


def test_existing_project_not_found_shows_error_and_unlocks_the_button(app):
    api = FakeApi(FILES)
    main, g, error = app(api, make_state([("/bkt/x", "folder")], project_id=404))
    assert _error_modals(g)
    assert api.fields.get("data.processing") is False
    assert api.created_datasets == []


def test_existing_nested_dataset_is_found(app):
    api = FakeApi(FILES, existing_project=(7, {70: ("parent", None, []), 71: ("child", 70, [])}))
    main, g, error = app(api, make_state([("/bkt/x", "folder")], project_id=7, dataset_name="child"))
    assert error is None
    assert sorted(api.datasets[71]) == ["1.jpg", "2.jpg", "3.jpg"]


def test_success_message_counts_skipped_files(app):
    api = FakeApi({"bkt/x/1.jpg": 3, "bkt/x/notes.txt": 3})
    main, g, error = app(api, make_state([("/bkt/x", "folder")]))
    assert error is None
    (message, level), = g.app.modals
    assert level == "info" and "1 images" in message and "1 file(s) skipped" in message
    assert api.fields.get("data.processing") is False
