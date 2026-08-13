"""Command-line interface for synthetic query generation."""

import argparse
import json
from pathlib import Path

from synthetic_query_generation.constraints import DEFAULT_REGISTRY
from synthetic_query_generation.models import FromPlansConfig, SeedQueryConfig
from synthetic_query_generation.templates import TEMPLATE_CATALOG


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate synthetic ChinaTravel queries from verified seed plans."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser(
        "seed-queries",
        help="Generate unconstrained base queries for running a planner.",
    )
    seed.add_argument("--output-dir", required=True)
    seed.add_argument("--num-records", type=int, default=100)
    seed.add_argument("--lang", choices=["zh", "en"], default="en")
    seed.add_argument("--seed", type=int, default=2026)
    seed.add_argument("--uid-prefix", default="synthetic_seed")
    seed.add_argument("--tag", default="synthetic_seed")
    seed.add_argument("--min-days", type=int, default=2)
    seed.add_argument("--max-days", type=int, default=5)
    seed.add_argument("--min-people", type=int, default=1)
    seed.add_argument("--max-people", type=int, default=5)
    seed.set_defaults(func=command_seed_queries)

    list_generators = subparsers.add_parser(
        "list-generators",
        help="List registered constraint generator families.",
    )
    list_generators.set_defaults(func=command_list_generators)

    from_plans = subparsers.add_parser(
        "from-plans",
        help="Sample verified constraints from seed plans and write query records.",
    )
    from_plans.add_argument("--plans-dir", required=True)
    from_plans.add_argument("--output-dir", required=True)
    from_plans.add_argument("--num-records", type=int, default=100)
    from_plans.add_argument("--max-seed-plans", type=int, default=0)
    from_plans.add_argument("--plan-glob", default="*.json")
    from_plans.add_argument("--lang", choices=["auto", "zh", "en"], default="auto")
    from_plans.add_argument("--seed", type=int, default=2026)
    from_plans.add_argument("--uid-prefix", default="synthetic_hard")
    from_plans.add_argument("--tag", default="synthetic_hard")
    from_plans.add_argument("--min-constraints", type=int, default=4)
    from_plans.add_argument("--max-constraints", type=int, default=7)
    from_plans.add_argument("--min-tricky-constraints", type=int, default=2)
    from_plans.add_argument("--min-logic-constraints", type=int, default=2)
    from_plans.add_argument(
        "--priority-constraint-keys",
        default="",
        help="Comma-separated constraint keys to prioritize during sampling.",
    )
    from_plans.add_argument(
        "--min-priority-constraints",
        type=int,
        default=0,
        help="Minimum number of directly sampled priority constraints per record.",
    )
    from_plans.add_argument("--budget-margin", type=float, default=0.03)
    from_plans.add_argument("--include-basic-constraints", action="store_true", default=True)
    from_plans.add_argument("--no-basic-constraints", dest="include_basic_constraints", action="store_false")
    from_plans.add_argument("--include-negative-constraints", action="store_true", default=True)
    from_plans.add_argument("--no-negative-constraints", dest="include_negative_constraints", action="store_false")
    from_plans.add_argument("--include-or-constraints", action="store_true", default=True)
    from_plans.add_argument("--no-or-constraints", dest="include_or_constraints", action="store_false")
    from_plans.add_argument("--max-or-candidates-per-plan", type=int, default=8)
    from_plans.add_argument(
        "--only-generators",
        default=None,
        help="Comma-separated generator family names to run, for example room,transport,budget.",
    )
    from_plans.add_argument(
        "--disable-generators",
        default="",
        help="Comma-separated generator family names to skip.",
    )
    from_plans.add_argument(
        "--only-constraint-keys",
        default=None,
        help="Comma-separated template keys allowed in generated records.",
    )
    from_plans.add_argument(
        "--disable-constraint-keys",
        default="",
        help="Comma-separated template keys to exclude from generated records.",
    )
    from_plans.add_argument(
        "--exclude-plan-prefixes",
        default="",
        help="Comma-separated source-plan UID prefixes to ignore.",
    )
    from_plans.add_argument("--variants-per-plan", type=int, default=1)
    from_plans.add_argument("--flat-output", action="store_true")
    from_plans.add_argument("--split-file", default=None)
    from_plans.add_argument("--copy-seed-plans", action="store_true")
    from_plans.add_argument("--validate-seed-commonsense", action="store_true", default=True)
    from_plans.add_argument(
        "--no-validate-seed-commonsense",
        dest="validate_seed_commonsense",
        action="store_false",
    )
    from_plans.add_argument("--shuffle", action="store_true", default=True)
    from_plans.add_argument("--no-shuffle", dest="shuffle", action="store_false")
    from_plans.add_argument("--max-manifest-errors", type=int, default=50)
    from_plans.set_defaults(func=command_from_plans)
    return parser


def parse_generator_names(value):
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def validate_generator_names(parser, names):
    known = set(DEFAULT_REGISTRY.names())
    unknown = sorted(names - known)
    if unknown:
        parser.error(
            "unknown generator(s): "
            + ", ".join(unknown)
            + "; known generators: "
            + ", ".join(DEFAULT_REGISTRY.names())
        )


def validate_constraint_keys(parser, names):
    unknown = sorted(names - set(TEMPLATE_CATALOG))
    if unknown:
        parser.error(
            "unknown constraint key(s): "
            + ", ".join(unknown)
            + "; known keys: "
            + ", ".join(sorted(TEMPLATE_CATALOG))
        )


def command_list_generators(_args):
    print("\n".join(DEFAULT_REGISTRY.names()))


def command_seed_queries(args):
    from synthetic_query_generation.pipeline import generate_seed_queries

    config = SeedQueryConfig(
        output_dir=Path(args.output_dir),
        num_records=args.num_records,
        lang=args.lang,
        seed=args.seed,
        uid_prefix=args.uid_prefix,
        tag=args.tag,
        min_days=args.min_days,
        max_days=args.max_days,
        min_people=args.min_people,
        max_people=args.max_people,
    )
    manifest = generate_seed_queries(config)
    print(f"Wrote {manifest['num_records_generated']} seed queries to {config.output_dir}")


def command_from_plans(args):
    from synthetic_query_generation.pipeline import generate_from_plans

    only_generators = parse_generator_names(args.only_generators)
    disabled_generators = parse_generator_names(args.disable_generators)
    only_constraint_keys = parse_generator_names(args.only_constraint_keys)
    disabled_constraint_keys = parse_generator_names(args.disable_constraint_keys)
    priority_constraint_keys = parse_generator_names(args.priority_constraint_keys)
    excluded_plan_prefixes = tuple(
        sorted(parse_generator_names(args.exclude_plan_prefixes))
    )
    config = FromPlansConfig(
        plans_dir=Path(args.plans_dir),
        output_dir=Path(args.output_dir),
        num_records=args.num_records,
        max_seed_plans=args.max_seed_plans or None,
        plan_glob=args.plan_glob,
        lang=args.lang,
        seed=args.seed,
        uid_prefix=args.uid_prefix,
        tag=args.tag,
        min_constraints=args.min_constraints,
        max_constraints=args.max_constraints,
        min_tricky_constraints=args.min_tricky_constraints,
        min_logic_constraints=args.min_logic_constraints,
        priority_constraint_keys=priority_constraint_keys,
        min_priority_constraints=args.min_priority_constraints,
        budget_margin=args.budget_margin,
        include_basic_constraints=args.include_basic_constraints,
        include_negative_constraints=args.include_negative_constraints,
        include_or_constraints=args.include_or_constraints,
        max_or_candidates_per_plan=args.max_or_candidates_per_plan,
        only_generators=only_generators or None,
        disabled_generators=disabled_generators,
        only_constraint_keys=only_constraint_keys or None,
        disabled_constraint_keys=disabled_constraint_keys,
        excluded_plan_prefixes=excluded_plan_prefixes,
        variants_per_plan=args.variants_per_plan,
        flat_output=args.flat_output,
        split_file=Path(args.split_file) if args.split_file else None,
        copy_seed_plans=args.copy_seed_plans,
        validate_seed_commonsense=args.validate_seed_commonsense,
        shuffle=args.shuffle,
        max_manifest_errors=args.max_manifest_errors,
    )
    manifest = generate_from_plans(config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def validate_args(parser, args):
    if hasattr(args, "min_constraints") and args.min_constraints > args.max_constraints:
        parser.error("--min-constraints cannot exceed --max-constraints")
    if hasattr(args, "min_logic_constraints") and args.min_logic_constraints > args.max_constraints:
        parser.error("--min-logic-constraints cannot exceed --max-constraints")
    if (
        hasattr(args, "min_priority_constraints")
        and args.min_priority_constraints > args.min_constraints
    ):
        parser.error("--min-priority-constraints cannot exceed --min-constraints")
    if hasattr(args, "variants_per_plan") and args.variants_per_plan < 1:
        parser.error("--variants-per-plan must be at least 1")
    if hasattr(args, "max_or_candidates_per_plan") and args.max_or_candidates_per_plan < 0:
        parser.error("--max-or-candidates-per-plan cannot be negative")
    if hasattr(args, "only_generators"):
        only_generators = parse_generator_names(args.only_generators)
        disabled_generators = parse_generator_names(args.disable_generators)
        validate_generator_names(parser, only_generators | disabled_generators)
    if hasattr(args, "only_constraint_keys"):
        only_constraint_keys = parse_generator_names(args.only_constraint_keys)
        disabled_constraint_keys = parse_generator_names(args.disable_constraint_keys)
        priority_constraint_keys = parse_generator_names(args.priority_constraint_keys)
        validate_constraint_keys(
            parser,
            only_constraint_keys
            | disabled_constraint_keys
            | priority_constraint_keys,
        )
        if args.min_priority_constraints and not priority_constraint_keys:
            parser.error(
                "--min-priority-constraints requires --priority-constraint-keys"
            )


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    args.func(args)
