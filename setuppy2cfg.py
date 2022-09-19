import argparse
import ast
import inspect
import sys

import textwrap
from collections import defaultdict
from copy import deepcopy

from typing import Dict, Any, List


def warn(msg):
    print("***", msg, file=sys.stderr)


def call_to_args(call: ast.Call, func) -> Dict[str, Any]:
    """
    Take an AST call and interpret its args + kwargs with func.
    """
    args = [ast.literal_eval(arg) for arg in call.args]
    kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
    return inspect.signature(func).bind(*args, **kwargs).arguments


class Walker(ast.NodeVisitor):
    metadata_keys = {}
    options_keys = {}

    def __init__(self, source: str):
        self.source = source
        self.output = defaultdict(dict)
        self.warnings = []

    def get_source_segment(self, node: ast.AST) -> str:
        return ast.get_source_segment(self.source, node)

    def get_value(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return f"attr:{self.get_source_segment(node)}"
        return ast.literal_eval(node)

    def visit_Call(self, node: ast.Call):
        if self.get_source_segment(node.func).endswith("setup"):
            self.process_setup_call(node)

    def process_setup_call(self, node: ast.Call) -> None:
        for kw in node.keywords:
            try:
                self.process_setup_keyword(kw)
            except Exception as exc:
                ind_source = textwrap.indent(self.get_source_segment(kw.value), "|  ")
                self.warn(
                    f"Unable to get value for {kw.arg}: {exc}\n{ind_source}"
                )

    def process_setup_keyword(self, kw: ast.keyword) -> None:
        raise NotImplementedError('...')

    def is_find_packages_call(self, node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        return self.get_source_segment(node.func).endswith("find_packages")

    def process_find_packages(self, call: ast.Call) -> str:
        import setuptools

        fp_args = call_to_args(call, setuptools.find_packages)
        where = fp_args.get("where", ".")
        if where != ".":
            raise ValueError(f"Unable to process find_packages(where={where!r}, ...)")
        for key in ("include", "exclude"):
            value = fp_args.get(key)
            if value:
                self.output["options.packages.find"][key] = list(value)
        return "find:"

    def get_output(self):
        return deepcopy(dict(self.output))

    def warn(self, msg):
        warn(msg)
        self.warnings.append(msg)

    def write(
        self,
        *,
        file,
        indent=4,
    ):
        config = self.get_output()
        for section, data in config.items():
            if not data:
                continue
            print(f"[{section}]", file=file)
            for key, value in data.items():
                if isinstance(value, (str, bool, int)):
                    print(f"{key} = {value}", file=file)
                elif isinstance(value, list):
                    print(f"{key} =", file=file)
                    for atom in value:
                        print(f"{' ' * indent}{atom}", file=file)
                else:
                    msg = f"Non-serializable value {section}.{key}"
                    warn(msg)
                    print(f"# {msg}", file=file)
            print(file=file)

        for warning in self.warnings:
            print(textwrap.indent(warning, "# "), file=file)


class SetupCfgWalker(Walker):
    # gleaned from https://raw.githubusercontent.com/pypa/setuptools/main/docs/userguide/declarative_config.rst
    metadata_keys = {
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
    options_keys = {
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

    def process_setup_keyword(self, kw: ast.keyword) -> None:
        arg = kw.arg
        output_key = None
        if arg in self.metadata_keys:
            output_key = ("metadata", arg)
        elif arg in self.options_keys:
            output_key = ("options", arg)
        if not output_key:
            warn(f"No output mapping for {arg}")
            return
        value = None
        if output_key == ("options", "packages"):
            if self.is_find_packages_call(kw.value):
                value = self.process_find_packages(kw.value)
        if value is None:
            value = self.get_value(kw.value)
        output_section, output_key = output_key
        self.output[output_section][output_key] = value

    def get_output(self):
        config = super().get_output()
        config["options.entry_points"] = config.get("options", {}).pop(
            "entry_points", None
        )
        return config


class PyProjectTomlWalker(Walker):

    def write(
        self,
        *,
        file,
        indent=4,
    ):
        import tomli_w
        config = self.get_output()
        print(tomli_w.dumps(config), file=file)

    def process_setup_keyword(self, kw: ast.keyword) -> None:
        arg = kw.arg
        value = self.get_value(kw.value)
        self.output["project"][arg] = value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-i", dest="input", type=argparse.FileType(), required=False, default=sys.stdin
    )
    ap.add_argument("--format", choices=("setup.cfg", "pyproject.toml"), default="setup.cfg")
    args = ap.parse_args()
    source = args.input.read()
    parsed = ast.parse(source, getattr(args.input, "name", str(args.input)))
    if args.format == "setup.cfg":
        walker = SetupCfgWalker(source)
    elif args.format == "pyproject.toml":
        walker = PyProjectTomlWalker(source)
    else:
        raise ValueError(f"Unknown format {args.format!r}")
    walker.visit(parsed)
    walker.write(file=sys.stdout)


if __name__ == "__main__":
    main()
