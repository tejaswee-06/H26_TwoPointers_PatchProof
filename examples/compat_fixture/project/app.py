"""Tiny synthetic fixture mirroring the playbook's Jinja2/MarkupSafe compatibility case.

This is NOT the organizer's LinkWatch repository.
"""
from jinja2 import Template


def render(name: str) -> str:
    return Template("Hello {{ name|e }}").render(name=name)
