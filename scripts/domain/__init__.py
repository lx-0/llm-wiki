"""Domain types — substrate-shaped data that flows through the engine.

Modules under `domain/` have NO imports from `adapters/` or `collectors/`.
They sit at the bottom of the dependency graph: adapters and collectors
import from domain, never the reverse. See [CONTEXT.md] for the rule.
"""
