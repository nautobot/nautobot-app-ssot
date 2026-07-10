"""Execution engine for the Data Import integration.

Pipeline: sources (fetch/parse) → normalize (flatten + derive tables) →
resolver (FK strategies) → loader (batched upsert) — orchestrated by runner.
"""
