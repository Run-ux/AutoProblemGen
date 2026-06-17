from __future__ import annotations

__all__ = ["build_manifest", "generate_report", "load_manifest", "run_ablation"]


def build_manifest(*args, **kwargs):
    from .manifest import build_manifest as _build_manifest

    return _build_manifest(*args, **kwargs)


def load_manifest(*args, **kwargs):
    from .manifest import load_manifest as _load_manifest

    return _load_manifest(*args, **kwargs)


def run_ablation(*args, **kwargs):
    from .pipeline import run_ablation as _run_ablation

    return _run_ablation(*args, **kwargs)


def generate_report(*args, **kwargs):
    from .reporting import generate_report as _generate_report

    return _generate_report(*args, **kwargs)
