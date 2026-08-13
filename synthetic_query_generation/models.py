"""Shared data models for the synthetic query generation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from typing import Callable


@dataclass
class ConstraintCandidate:
    key: str
    code: str
    nl: dict
    category: str
    tags: set = field(default_factory=set)
    hardness: int = 1
    metadata: dict = field(default_factory=dict)

    def text(self, lang):
        return self.nl.get(lang) or self.nl.get("en") or next(iter(self.nl.values()))


@dataclass
class EntityContext:
    by_type: dict
    type_values: dict


@dataclass
class ConstraintGenerationOptions:
    budget_margin: float = 0.03
    include_negative_constraints: bool = True
    include_or_constraints: bool = True
    max_or_candidates_per_plan: int = 8
    enabled_generators: set | None = None
    disabled_generators: set = field(default_factory=set)
    enabled_constraint_keys: set | None = None
    disabled_constraint_keys: set = field(default_factory=set)


@dataclass
class ConstraintSelectionOptions:
    min_constraints: int = 4
    max_constraints: int = 7
    min_tricky_constraints: int = 2
    min_logic_constraints: int = 2
    priority_constraint_keys: set = field(default_factory=set)
    min_priority_constraints: int = 0


@dataclass
class RecordGenerationOptions:
    lang: str = "auto"
    uid_prefix: str = "synthetic_hard"
    tag: str = "synthetic_hard"
    include_basic_constraints: bool = True
    constraint_generation: ConstraintGenerationOptions = field(
        default_factory=ConstraintGenerationOptions
    )
    constraint_selection: ConstraintSelectionOptions = field(
        default_factory=ConstraintSelectionOptions
    )


@dataclass
class ConstraintContext:
    plan: dict
    lang: str
    rng: Random
    options: ConstraintGenerationOptions
    entities_loader: Callable[[], EntityContext]
    _entities: EntityContext | None = None

    @property
    def entities(self):
        if self._entities is None:
            self._entities = self.entities_loader()
        return self._entities


@dataclass
class FromPlansConfig:
    plans_dir: Path
    output_dir: Path
    num_records: int = 100
    max_seed_plans: int | None = None
    plan_glob: str = "*.json"
    lang: str = "auto"
    seed: int = 2026
    uid_prefix: str = "synthetic_hard"
    tag: str = "synthetic_hard"
    min_constraints: int = 4
    max_constraints: int = 7
    min_tricky_constraints: int = 2
    min_logic_constraints: int = 2
    priority_constraint_keys: set = field(default_factory=set)
    min_priority_constraints: int = 0
    budget_margin: float = 0.03
    include_basic_constraints: bool = True
    include_negative_constraints: bool = True
    include_or_constraints: bool = True
    max_or_candidates_per_plan: int = 8
    only_generators: set | None = None
    disabled_generators: set = field(default_factory=set)
    only_constraint_keys: set | None = None
    disabled_constraint_keys: set = field(default_factory=set)
    excluded_plan_prefixes: tuple = field(default_factory=tuple)
    variants_per_plan: int = 1
    flat_output: bool = False
    split_file: Path | None = None
    copy_seed_plans: bool = False
    validate_seed_commonsense: bool = True
    shuffle: bool = True
    max_manifest_errors: int = 50

    def record_options(self):
        return RecordGenerationOptions(
            lang=self.lang,
            uid_prefix=self.uid_prefix,
            tag=self.tag,
            include_basic_constraints=self.include_basic_constraints,
            constraint_generation=ConstraintGenerationOptions(
                budget_margin=self.budget_margin,
                include_negative_constraints=self.include_negative_constraints,
                include_or_constraints=self.include_or_constraints,
                max_or_candidates_per_plan=self.max_or_candidates_per_plan,
                enabled_generators=self.only_generators,
                disabled_generators=self.disabled_generators,
                enabled_constraint_keys=self.only_constraint_keys,
                disabled_constraint_keys=self.disabled_constraint_keys,
            ),
            constraint_selection=ConstraintSelectionOptions(
                min_constraints=self.min_constraints,
                max_constraints=self.max_constraints,
                min_tricky_constraints=self.min_tricky_constraints,
                min_logic_constraints=self.min_logic_constraints,
                priority_constraint_keys=self.priority_constraint_keys,
                min_priority_constraints=self.min_priority_constraints,
            ),
        )


@dataclass
class SeedQueryConfig:
    output_dir: Path
    num_records: int = 100
    lang: str = "en"
    seed: int = 2026
    uid_prefix: str = "synthetic_seed"
    tag: str = "synthetic_seed"
    min_days: int = 2
    max_days: int = 5
    min_people: int = 1
    max_people: int = 5
