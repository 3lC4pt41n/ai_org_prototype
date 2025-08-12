import pytest

from ai_org_backend.utils.filetypes import infer_extension


def test_infer_tsx():
    code = """export function Greeting() {\n  return <div>Hello!</div>;\n}\n"""
    assert infer_extension(code) == ".tsx"


def test_infer_ts():
    code = """export function add(a: number, b: number): number {\n  return a + b;\n}\n"""
    assert infer_extension(code) == ".ts"


def test_infer_html():
    code = """<html><head></head><body><div></div></body></html>"""
    assert infer_extension(code) == ".html"


def test_infer_css():
    code = """.container {\n  color: red;\n}\n"""
    assert infer_extension(code) == ".css"


def test_infer_python_default():
    code = """def foo():\n    pass\n"""
    assert infer_extension(code) == ".py"
