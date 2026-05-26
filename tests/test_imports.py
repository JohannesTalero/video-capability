"""Smoke test: all pipeline modules import without error.

Catches accidental circular imports or syntax errors before they reach a
real run. Cheap to execute — no network, no filesystem beyond reading
the modules themselves.
"""


def test_pipeline_modules_import():
    import pipeline                           # noqa: F401
    import pipeline.config                    # noqa: F401
    import pipeline.formats                   # noqa: F401
    import pipeline.llm                       # noqa: F401
    import pipeline.models                    # noqa: F401
    import pipeline.orchestrator              # noqa: F401
    import pipeline.storage                   # noqa: F401
    import pipeline.validator                 # noqa: F401


def test_phase_modules_import():
    import pipeline.phases.phase1_ingest      # noqa: F401
    import pipeline.phases.phase2_narrative   # noqa: F401
