import argparse
import ast
import sys

import textwrap
from collections import defaultdict
from copy import deepcopy

# gleaned from https://raw.githubusercontent.com/pypa/setuptools/main/docs/userguide/declarative_config.rst

METADATA_KEYS = {
    "name": "str",
    "version": "attr:, file:, str",
    "url": "str",
    "download_url": "str",
    "project_urls": "dict",
    "author": "str",
    "author_email": "str",
    "maintainer": "str",
    "maintainer_email": "str",
    "classifiers": "file:, list-comma",
    "license": "str",
    "license_files": "list-comma",
    "description": "file:, str",
    "long_description": "file:, str",
    "long_description_content_type": "str",
    "keywords": "list-comma",
    "platforms": "list-comma",
    "provides": "list-comma",
    "requires": "list-comma",
    "obsoletes": "list-comma",
}

OPTIONS_KEYS = {
    "zip_safe": "bool",
    "setup_requires": "list-semi",
    "install_requires": "list-semi",
    "extras_require": "section",
    "python_requires": "str",
    "entry_points": "file:, section",
    "scripts": "list-comma",
    "eager_resources": "list-comma",
    "dependency_links": "list-comma",
    "tests_require": "list-semi",
    "include_package_data": "bool",
    "packages": "find:, find_namespace:, list-comma",
    "package_dir": "dict",
    "package_data": "section",
    "exclude_package_data": "section",
    "namespace_packages": "list-comma",
    "py_modules": "list-comma",
    "data_files": "section",
}


def warn(msg):
    print("***", msg, file=sys.stderr)


class Walker(ast.NodeVisitor):
    def __init__(self, source: str):
        self.source = source
        self.output = defaultdict(dict)

    def get_source_segment(self, node: ast.AST) -> str:
        return ast.get_source_segment(self.source, node)

    def get_value(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return f"attr:{self.get_source_segment(node)}"
        return ast.literal_eval(node)

    def visit_Call(self, node: ast.Call):
        if self.get_source_segment(node.func).endswith("setup"):
            self.process_setup_call(node)

    def process_setup_call(self, node: ast.Call):
        for kw in node.keywords:
            arg = kw.arg
            output_key = None
            if arg in METADATA_KEYS:
                output_key = ("metadata", arg)
            elif arg in OPTIONS_KEYS:
                output_key = ("options", arg)
            if not output_key:
                warn(f"No output mapping for {arg}")
                continue
            try:
                value = self.get_value(kw.value)
                output_section, output_key = output_key
                self.output[output_section][output_key] = value
            except Exception as exc:
                ind_source = textwrap.indent(self.get_source_segment(kw.value), "|  ")
                warn(f"Unable to get value for {arg}: {exc}\n{ind_source}")

    def get_output(self):
        return deepcopy(dict(self.output))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-i", dest="input", type=argparse.FileType(), required=False, default=sys.stdin
    )
    args = ap.parse_args()
    source = args.input.read()
    parsed = ast.parse(source, getattr(args.input, "name", str(args.input)))
    walker = Walker(source)
    walker.visit(parsed)
    config = walker.get_output()

    config["options.entry_points"] = config.get("options", {}).pop("entry_points", None)

    for section, data in config.items():
        if not data:
            continue
        print(f"[{section}]")
        for key, value in data.items():
            if isinstance(value, (str, bool, int)):
                print(f"{key} = {value}")
            elif isinstance(value, list):
                print(f"{key} =")
                for atom in value:
                    print(f"  {atom}")
            else:
                warn(f"Non-serializable value {section}.{key}")
        print()


if __name__ == "__main__":
    main()
