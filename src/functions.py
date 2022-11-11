from supervisely.io.fs import get_file_ext, get_file_name


def generate_free_name(used_names, possible_name, with_ext=False, extend_used_names=False):
    res_name = possible_name
    new_suffix = 1
    while res_name in used_names:
        if with_ext is True:
            res_name = "{}_{:02d}{}".format(
                get_file_name(possible_name),
                new_suffix,
                get_file_ext(possible_name),
            )
        else:
            res_name = "{}_{:02d}".format(possible_name, new_suffix)
        new_suffix += 1
    if extend_used_names:
        used_names.add(res_name)
    return res_name
