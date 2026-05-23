"""Tests for startup-time import behavior."""

import builtins
import importlib
import sys


def test_app_import_does_not_import_openai(monkeypatch):
    for name in list(sys.modules):
        if name == "openai" or name.startswith("md_preview_server.app"):
            sys.modules.pop(name, None)

    real_import = builtins.__import__

    def import_without_openai(name, *args, **kwargs):
        if name == "openai":
            raise AssertionError("openai should only be imported by the AI route")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_openai)
    module = importlib.import_module("md_preview_server.app")

    assert module.create_app is not None
