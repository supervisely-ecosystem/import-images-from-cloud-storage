from collections import Counter

from supervisely.io.fs import get_file_ext, get_file_name, get_file_name_with_ext


def get_images_names_from_paths(local_paths, used_names=None):
    names = []
    for local_path in local_paths:
        image_name = get_file_name_with_ext(local_path)
        names.append(image_name)
    name_counter = Counter(names)
    if len(name_counter) == len(local_paths):
        return names
    else:
        collisions = {name: count for name, count in name_counter.items() if count != 1}
    res_names = used_names if used_names is not None else []
    new_suffix = 1
    for name in names:
        if name in collisions:
            res_name = "{}_{:02d}{}".format(
                get_file_name(name),
                new_suffix,
                get_file_ext(name),
            )
            new_suffix += 1
            res_names.append(res_name)
        else:
            res_names.append(name)
    return res_names