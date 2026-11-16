#!/usr/bin/env python3
"""
Collective Energy Investment Runner - European Simulation (Exclusive Europe Mode).

Collects investment choice files from student groups (e.g. france_europe1.txt, france_europe2.txt in input/runner/,
or corresponding JSON files), configures the model exclusively in "europe" mode, runs the unified simulation
for Europe 1 and Europe 2 sequentially, displays a comparative dashboard, and saves the comparison to disk.

The runner operates exclusively in "europe" mode (solo mode is not supported by the runner).

Usage:
    # Standard execution: collect all files in input/runner/ (.txt) and run European simulations:
    python main_runner.py
    python main_runner.py txt

    # JSON execution: use JSON files in input/runner/ or input/long_term_uc/countries/ (.json):
    python main_runner.py json
    python main_runner.py --source json

    # Preview mode (updates country .json files without solving):
    python main_runner.py --dry-run
    python main_runner.py json --dry-run

    # Test/debug mode (fast 2-week simulation: 1900/1/1 to 1900/1/15):
    python main_runner.py --test
    python main_runner.py --test --dry-run

    # Execute only Europe 1 or Europe 2:
    python main_runner.py --europe europe1
    python main_runner.py --europe europe2

    # Clear previous runner outputs and history:
    python main_runner.py --clean
    python main_runner.py clean

    # Specify a custom folder or files:
    python main_runner.py custom_folder/
"""

import argparse
import glob
import json
import logging
import os
import sys
from typing import Dict, List, Optional

from src.include_runner.investments_runner import (
    AVAILABLE_COUNTRIES,
    DEFAULT_PERIOD_START,
    DEFAULT_PERIOD_END,
    TEST_PERIOD_START,
    TEST_PERIOD_END,
    resolve_simulation_period,
    parse_investment_file,
    parse_country_json_file,
    load_country_capacities,
    collect_investment_files,
    write_country_json,
    update_europe_params,
    run_simulation,
    find_latest_summary_file,
    find_new_summary_file,
    display_multi_country_summary,
    group_files_by_europe_with_sources,
    extract_simulation_metrics,
    compute_europe_comparison,
    format_comparison_table,
    display_europe_comparison,
    save_comparison_results,
    load_simulation_history,
    compute_simulation_evolutions,
    format_simulation_evolutions_table,
    display_simulation_evolutions,
    save_simulation_evolutions,
    clear_runner_outputs,
)


def run_single_europe_simulation(
    europe_name: str,
    country_capacities: Dict[str, Dict[str, float]],
    period_start: str,
    period_end: str,
    dry_run: bool = False,
    sim_output_base_dir: str = "output/long_term_uc",
) -> Optional[dict]:
    """
    Configure and execute simulation for one European mix, returning extracted metrics.
    """
    countries = sorted(list(country_capacities.keys()))
    print(f"\n--- [CONFIGURING {europe_name.upper()}] ({len(countries)} countries) ---")
    for country in countries:
        json_path = write_country_json(country=country, capacities=country_capacities[country])
        print(f"      -> {json_path} updated ({len(country_capacities[country])} assets)")

    # Update global parameters in elec-europe_params_to-be-modif.json
    update_europe_params(
        mode="europe",
        team=countries[0],
        period_start=period_start,
        period_end=period_end,
    )
    is_full_year = (period_start == DEFAULT_PERIOD_START and period_end == DEFAULT_PERIOD_END)
    period_label = "full year period" if is_full_year else "simulation period"
    print(
        f"      -> Global parameters: mode='europe', {period_label} [{period_start} - {period_end}] "
        f"activated in elec-europe_params_to-be-modif.json"
    )

    if dry_run:
        print(f"      [INFO] --dry-run active for {europe_name}: files updated, solver not launched.")
        return None

    pattern = os.path.join(sim_output_base_dir, "**", "uc-summary_*.json")
    before_files = set(glob.glob(pattern, recursive=True))

    print(f"\n[RUN] Launching simulation for {europe_name.upper()} (my_little_europe_lt_uc.py)...")
    print("-" * 70)
    return_code = run_simulation()
    print("-" * 70)

    if return_code != 0:
        print(f"\n[!] Simulation for {europe_name} failed with non-zero exit code ({return_code}).", file=sys.stderr)
        sys.exit(return_code)

    summary_file = find_new_summary_file(before_files=before_files, output_base_dir=sim_output_base_dir)
    if not summary_file or not os.path.isfile(summary_file):
        print(f"[!] Warning: No summary file found for {europe_name} run.")
        return None

    try:
        with open(summary_file, "r", encoding="utf-8") as f:
            summary_data = json.load(f)
        metrics = extract_simulation_metrics(
            summary_data=summary_data,
            per_country_capacities=country_capacities,
            summary_file_path=summary_file,
            countries=AVAILABLE_COUNTRIES,
        )
        return metrics
    except Exception as exc:
        logging.warning(f"Error reading summary file {summary_file}: {exc}")
        return None


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the collective runner."""
    parser = argparse.ArgumentParser(
        description="Collective Runner: collects student investments for all countries and executes European simulation(s)."
    )
    parser.add_argument(
        "folder_or_files",
        nargs="*",
        default=None,
        help="Directory, list of country files, or source keyword ('txt' or 'json') (default: input/runner/)",
    )
    parser.add_argument(
        "--source",
        choices=["txt", "json"],
        default=None,
        help="Source format to use: 'txt' (input/runner/*.txt) or 'json' (input/runner/*.json). Default: 'txt'",
    )
    parser.add_argument(
        "--europe",
        choices=["all", "europe1", "europe2"],
        default="all",
        help="Specify which Europe to simulate: 'europe1', 'europe2', or 'all' (default: 'all')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Update country .json files without executing the PyPSA simulation",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Fast debug mode: simulate only a 2-week period ('1900/1/1' to '1900/1/15') for quick testing",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Do not display the comparative summary table at the end of simulation",
    )
    parser.add_argument(
        "--output-dir",
        default="output/runner",
        help="Directory where comparison reports and simulation history are saved (default: 'output/runner')",
    )
    parser.add_argument(
        "--history-europe",
        choices=["europe1", "europe2"],
        default="europe1",
        help="Europe configuration to track across historical simulations (default: 'europe1')",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Do not display the simulation evolution history across successive runs",
    )
    parser.add_argument(
        "--clean",
        "--clear",
        action="store_true",
        dest="clean",
        help="Clear runner outputs and simulation history in output/runner/ (or specified --output-dir) to prevent blurring incremental results",
    )
    parser.add_argument(
        "--period-start",
        default="1900/1/1",
        help="Simulation start date (default: '1900/1/1', full year)",
    )
    parser.add_argument(
        "--period-end",
        default="1901/1/1",
        help="Simulation end date (default: '1901/1/1', full year)",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Determine source mode and input targets
    raw_targets = list(args.folder_or_files) if args.folder_or_files else []
    source_mode = args.source

    # Check if a positional keyword was used ('clean', 'clear', 'txt', or 'json')
    is_clean_keyword = False
    if raw_targets and len(raw_targets) == 1 and raw_targets[0].lower() in ("clean", "clear"):
        args.clean = True
        is_clean_keyword = True
        raw_targets = []

    # Handle cleaning runner outputs if requested
    if args.clean:
        removed = clear_runner_outputs(output_dir=args.output_dir)
        if removed:
            print(f"\n[OK] Cleared {len(removed)} output file(s) in '{args.output_dir}':")
            for f in removed:
                print(f"      - {f}")
        else:
            print(f"\n[i] Output directory '{args.output_dir}' is already clean (no files to remove).")

        # If --clean or 'clean' was called standalone (no test, dry-run, or custom targets specified), exit cleanly
        if is_clean_keyword or (not args.folder_or_files and not args.test and not args.dry_run and args.europe == "all"):
            print("\nRunner output directory reset. Exiting.")
            sys.exit(0)

    # Resolve simulation period (full year vs. 2-week test period)
    period_start, period_end = resolve_simulation_period(
        is_test=args.test,
        period_start=args.period_start,
        period_end=args.period_end,
    )

    # Check if a positional keyword was used ('txt' or 'json')
    if raw_targets and len(raw_targets) == 1 and raw_targets[0].lower() in ("txt", "json"):
        if source_mode is None:
            source_mode = raw_targets[0].lower()
        raw_targets = []

    # Default source mode is "txt" if not specified
    if source_mode is None:
        if raw_targets and all(f.endswith(".json") for f in raw_targets if os.path.isfile(f)):
            source_mode = "json"
        else:
            source_mode = "txt"

    if not raw_targets:
        runner_dir = os.path.join("input", "runner")
        if os.path.isdir(runner_dir):
            raw_targets = [runner_dir]
        elif source_mode == "json" and os.path.isdir(os.path.join("input", "long_term_uc", "countries")):
            raw_targets = [os.path.join("input", "long_term_uc", "countries")]
        else:
            parser.print_help()
            print(f"\nError: Directory '{runner_dir}' not found.")
            sys.exit(1)

    ext = ".json" if source_mode == "json" else ".txt"
    matched_files = collect_investment_files(raw_targets, extension=ext)

    if not matched_files:
        print(f"[!] No {ext} files found in: {raw_targets}")
        print(f"    Please place country files in input/runner/ (e.g., france_europe1{ext}, france_europe2{ext}...)")
        sys.exit(1)

    # Group files by Europe identifier (europe1, europe2, ...)
    grouped_capas, grouped_srcs = group_files_by_europe_with_sources(matched_files)

    # Filter Europes based on --europe argument if specified
    if args.europe != "all":
        grouped_capas = {k: v for k, v in grouped_capas.items() if k == args.europe}
        grouped_srcs = {k: v for k, v in grouped_srcs.items() if k == args.europe}

    available_europes = sorted(list(grouped_capas.keys()))
    if not available_europes:
        print(f"[!] No files matched the requested Europe configuration ('{args.europe}').")
        sys.exit(1)

    print("\n" + "=" * 76)
    print(f"   COLLECTIVE RUNNER FOR STUDENT INVESTMENTS - EUROPE MODE ({source_mode.upper()} SOURCE)")
    if args.test:
        print(f"   *** TEST / DEBUG MODE ACTIVATED: [{period_start} -> {period_end}] (2 WEEKS) ***")
    print("=" * 76)
    print(f"Detected Europe configuration(s): {', '.join(e.upper() for e in available_europes)}")
    for eur in available_europes:
        c_list = sorted(list(grouped_capas[eur].keys()))
        print(f"  * {eur.upper()} ({len(c_list)} countries): {', '.join(c_list)}")
        for c in c_list:
            print(f"      - {c:<18} <- {grouped_srcs[eur][c]} ({len(grouped_capas[eur][c])} assets)")

    # Case A: Two Europes are present and requested -> Sequential run + Comparison
    if len(available_europes) >= 2 and "europe1" in grouped_capas and "europe2" in grouped_capas:
        print("\n" + "=" * 76)
        print("   SEQUENTIAL EXECUTION: SIMULATION EUROPE 1 THEN SIMULATION EUROPE 2")
        print("=" * 76)

        # 1. Run Europe 1
        metrics_eur1 = run_single_europe_simulation(
            europe_name="europe1",
            country_capacities=grouped_capas["europe1"],
            period_start=period_start,
            period_end=period_end,
            dry_run=args.dry_run,
        )

        # 2. Run Europe 2
        metrics_eur2 = run_single_europe_simulation(
            europe_name="europe2",
            country_capacities=grouped_capas["europe2"],
            period_start=period_start,
            period_end=period_end,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            print("\n[INFO] --dry-run completed: both Europe 1 and Europe 2 configurations validated.")
            return

        if metrics_eur1 and metrics_eur2:
            # 3. Compute and display comparative dashboard
            comparison = compute_europe_comparison(metrics_eur1, metrics_eur2)
            report_text = format_comparison_table(metrics_eur1, metrics_eur2, comparison)

            if not args.no_summary:
                display_europe_comparison(report_text)

            # 4. Save comparative results
            txt_file, json_file = save_comparison_results(
                comparison_data=comparison,
                formatted_report=report_text,
                output_dir=args.output_dir,
                filename_prefix="comparison_europe1_vs_europe2",
                metrics_eur1=metrics_eur1,
                metrics_eur2=metrics_eur2,
            )
            print(f"\n[OK] Comparative summary successfully saved:")
            print(f"     -> Text report : {txt_file}")
            print(f"     -> JSON metrics: {json_file}\n")
        else:
            print("\n[!] Warning: Could not generate comparison because one of the simulations did not produce metrics.")

    # Case B: Single Europe configuration
    else:
        single_eur = available_europes[0]
        metrics = run_single_europe_simulation(
            europe_name=single_eur,
            country_capacities=grouped_capas[single_eur],
            period_start=period_start,
            period_end=period_end,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            print(f"\n[INFO] --dry-run completed for {single_eur}.")
            return

        if not args.no_summary and metrics and metrics.get("summary_file"):
            with open(metrics["summary_file"], "r", encoding="utf-8") as f:
                s_data = json.load(f)
            display_multi_country_summary(
                summary_data=s_data,
                countries=AVAILABLE_COUNTRIES,
                updated_countries=sorted(list(grouped_capas[single_eur].keys())),
                per_country_capacities=grouped_capas[single_eur],
                summary_file_path=metrics["summary_file"],
            )

    # 5. Simulation Evolution Tracking across successive runs (for target Europe, default: europe1)
    if not args.dry_run and not args.no_history:
        target_eur = args.history_europe
        history = load_simulation_history(output_dir=args.output_dir, target_europe=target_eur)
        if len(history) >= 2:
            evol_data = compute_simulation_evolutions(history)
            evol_table = format_simulation_evolutions_table(evol_data, target_europe=target_eur)
            display_simulation_evolutions(evol_table)
            hist_txt, hist_json = save_simulation_evolutions(
                evolution_data=evol_data,
                report_text=evol_table,
                output_dir=args.output_dir,
                target_europe=target_eur,
            )
            print(f"[i] Simulation evolution history saved to:")
            print(f"    -> Text report : {hist_txt}")
            print(f"    -> JSON metrics: {hist_json}\n")


if __name__ == "__main__":
    main()

