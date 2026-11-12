"""Narrow compatibility loading for immutable, locally installed source assets.

Only MuJoCo add_geom/add_site size keywords are padded. No HTTP or voice input
can select a source path. Source files are never modified in their checkout.
"""

import ast
import sys
import types


def size3(value):
    result = list(value)
    return result + [0] * max(0, 3 - len(result))


class Sizes(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"add_geom", "add_site"}:
            for keyword in node.keywords:
                if keyword.arg == "size":
                    keyword.value = ast.Call(
                        func=ast.Name(id="_mj_size3", ctx=ast.Load()),
                        args=[keyword.value],
                        keywords=[],
                    )
        return node


def compatible_module(path, name):
    result = types.ModuleType(name)
    result.__file__ = str(path)
    result.__package__ = name.rpartition(".")[0]
    result.__dict__["_mj_size3"] = size3
    tree = ast.fix_missing_locations(Sizes().visit(ast.parse(path.read_text())))
    sys.modules[name] = result
    exec(compile(tree, str(path), "exec"), result.__dict__)
    return result


def scene_builder(path, name, namespace):
    """Load one pure MJCF builder without importing GPU training packages."""
    source = ast.parse(path.read_text())
    function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == name)
    tree = ast.fix_missing_locations(Sizes().visit(ast.Module(body=[function], type_ignores=[])))
    namespace = {**namespace, "_mj_size3": size3}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace[name]()


def source_symbols(path, names, namespace):
    """Extract named pure helpers/constants without importing training packages."""
    nodes = []
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in names for t in node.targets
        ):
            nodes.append(node)
    tree = ast.fix_missing_locations(Sizes().visit(ast.Module(body=nodes, type_ignores=[])))
    namespace = {**namespace, "_mj_size3": size3}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace
