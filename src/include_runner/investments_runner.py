import glob
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

from src.common.constants.countries import set_country_trigram
from src.common.constants.prod_types import ProdTypeNames

AVAILABLE_COUNTRIES: List[str] = [
    "benelux",
    "france",
    "germany",
    "iberian-peninsula",
    "italy",
    "poland",
    "scandinavia",
]

COUNTRY_ALIASES: Dict[str, str] = {
    "france": "france",
    "fr": "france",
    "germany": "germany",
    "de": "germany",
    "allemagne": "germany",
    "deutschland": "germany",
    "italy": "italy",
    "it": "italy",
    "italie": "italy",
    "italia": "italy",
    "poland": "poland",
    "pl": "poland",
    "pologne": "poland",
    "polska": "poland",
    "benelux": "benelux",
    "be": "benelux",
    "belgique": "benelux",
    "netherlands": "benelux",
    "pays-bas": "benelux",
    "nl": "benelux",
    "scandinavia": "scandinavia",
    "scandinavie": "scandinavia",
    "scand": "scandinavia",
    "se": "scandinavia",
    "no": "scandinavia",
    "suede": "scandinavia",
    "iberian-peninsula": "iberian-peninsula",
    "iberian_peninsula": "iberian-peninsula",
    "iberia": "iberian-peninsula",
    "peninsule_iberique": "iberian-peninsula",
    "péninsule ibérique": "iberian-peninsula",
    "es": "iberian-peninsula",
    "espagne": "iberian-peninsula",
    "spain": "iberian-peninsula",
    "portugal": "iberian-peninsula",
    "pt": "iberian-peninsula",
}

ASSET_ALIASES: Dict[str, str] = {
    # Nuclear
    "nuclear": ProdTypeNames.nuclear,
    "nucleaire": ProdTypeNames.nuclear,
    "nucléaire": ProdTypeNames.nuclear,
    "nuc": ProdTypeNames.nuclear,
    # Wind onshore
    "wind_onshore": ProdTypeNames.wind_onshore,
    "wind_on_shore": ProdTypeNames.wind_onshore,
    "wind onshore": ProdTypeNames.wind_onshore,
    "onshore_wind": ProdTypeNames.wind_onshore,
    "onshore": ProdTypeNames.wind_onshore,
    "eolien_terrestre": ProdTypeNames.wind_onshore,
    "éolien_terrestre": ProdTypeNames.wind_onshore,
    "eolien terrestre": ProdTypeNames.wind_onshore,
    "éolien terrestre": ProdTypeNames.wind_onshore,
    "eolien_onshore": ProdTypeNames.wind_onshore,
    # Wind offshore
    "wind_offshore": ProdTypeNames.wind_offshore,
    "wind_off_shore": ProdTypeNames.wind_offshore,
    "wind offshore": ProdTypeNames.wind_offshore,
    "offshore_wind": ProdTypeNames.wind_offshore,
    "offshore": ProdTypeNames.wind_offshore,
    "eolien_en_mer": ProdTypeNames.wind_offshore,
    "éolien_en_mer": ProdTypeNames.wind_offshore,
    "eolien en mer": ProdTypeNames.wind_offshore,
    "éolien en mer": ProdTypeNames.wind_offshore,
    "eolien_offshore": ProdTypeNames.wind_offshore,
    # Solar PV
    "solar_pv": ProdTypeNames.solar_pv,
    "solar": ProdTypeNames.solar_pv,
    "pv": ProdTypeNames.solar_pv,
    "solaire": ProdTypeNames.solar_pv,
    "solaire_pv": ProdTypeNames.solar_pv,
    "solar pv": ProdTypeNames.solar_pv,
    # Thermal & Fossil
    "gas": ProdTypeNames.gas,
    "gaz": ProdTypeNames.gas,
    "ccgt": ProdTypeNames.gas,
    "ocgt": ProdTypeNames.gas,
    "coal": ProdTypeNames.coal,
    "charbon": ProdTypeNames.coal,
    "lignite": ProdTypeNames.lignite,
    "oil": ProdTypeNames.oil,
    "fioul": ProdTypeNames.oil,
    "fuel": ProdTypeNames.oil,
    "petrole": ProdTypeNames.oil,
    "pétrole": ProdTypeNames.oil,
    "biofuel": ProdTypeNames.biofuel,
    "biomasse": ProdTypeNames.biofuel,
    "biomass": ProdTypeNames.biofuel,
    # Storage & Flexibility
    "batteries": ProdTypeNames.batteries,
    "battery": ProdTypeNames.batteries,
    "batterie": ProdTypeNames.batteries,
    "dsr": ProdTypeNames.dsr,
    "demand_side_response": ProdTypeNames.dsr,
    "effacement": ProdTypeNames.dsr,
    # Hydro
    "hydro_reservoir": ProdTypeNames.hydro_reservoir,
    "reservoir": ProdTypeNames.hydro_reservoir,
    "réservoir": ProdTypeNames.hydro_reservoir,
    "barrage": ProdTypeNames.hydro_reservoir,
    "hydro_pondage": ProdTypeNames.hydro_pondage,
    "pondage": ProdTypeNames.hydro_pondage,
    "eclusee": ProdTypeNames.hydro_pondage,
    "éclusée": ProdTypeNames.hydro_pondage,
    "hydro_run_of_river": ProdTypeNames.hydro_ror,
    "run_of_river": ProdTypeNames.hydro_ror,
    "ror": ProdTypeNames.hydro_ror,
    "fil_de_leau": ProdTypeNames.hydro_ror,
    "fil d'eau": ProdTypeNames.hydro_ror,
    "hydro_pump_storage_closed_loop": ProdTypeNames.hydro_pump_storage_closed,
    "pump_storage_closed_loop": ProdTypeNames.hydro_pump_storage_closed,
    "step_closed": ProdTypeNames.hydro_pump_storage_closed,
    "step_fermee": ProdTypeNames.hydro_pump_storage_closed,
    "step fermée": ProdTypeNames.hydro_pump_storage_closed,
    "hydro_pump_storage_open_loop": ProdTypeNames.hydro_pump_storage_open,
    "pump_storage_open_loop": ProdTypeNames.hydro_pump_storage_open,
    "step_open": ProdTypeNames.hydro_pump_storage_open,
    "step_ouverte": ProdTypeNames.hydro_pump_storage_open,
    "step ouverte": ProdTypeNames.hydro_pump_storage_open,
    # Other
    "others_fatal": ProdTypeNames.others_fatal,
    "fatal": ProdTypeNames.others_fatal,
    "failure": ProdTypeNames.failure,
    "defaillance": ProdTypeNames.failure,
    "défaillance": ProdTypeNames.failure,
}


def normalize_country_name(name: str) -> str:
    """Normalize and validate country name."""
    clean = name.strip().lower()
    clean = clean.replace(" ", "-").replace("_", "-")
    if clean in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[clean]
    if clean in AVAILABLE_COUNTRIES:
        return clean
    raise ValueError(
        f"Unknown country '{name}'. Available countries: {', '.join(AVAILABLE_COUNTRIES)}"
    )


def normalize_asset_name(name: str) -> str:
    """Normalize and validate production asset name."""
    clean = name.strip().lower()
    clean_key = clean.replace("-", "_")
    if clean_key in ASSET_ALIASES:
        return ASSET_ALIASES[clean_key]
    if clean in ASSET_ALIASES:
        return ASSET_ALIASES[clean]
    valid_names = [getattr(ProdTypeNames, attr) for attr in dir(ProdTypeNames)
                   if not attr.startswith("_") and isinstance(getattr(ProdTypeNames, attr), str)]
    if clean_key in valid_names:
        return clean_key
    raise ValueError(
        f"Unknown asset type '{name}'. Supported assets: nuclear, wind_onshore, wind_offshore, "
        f"solar_pv, gas, coal, lignite, oil, biofuel, batteries, dsr, hydro_reservoir, "
        f"hydro_pondage, hydro_run_of_river, hydro_pump_storage_closed_loop, hydro_pump_storage_open_loop"
    )


def parse_capacity_value(val_str: str) -> float:
    """Parse capacity value string in MW (e.g. '60000', '60000 MW', '60000.5')."""
    cleaned = val_str.strip().upper()
    if cleaned.endswith("MW"):
        cleaned = cleaned[:-2].strip()
    try:
        val = float(cleaned)
    except ValueError:
        raise ValueError(
            f"Invalid capacity value '{val_str}'. Please provide a number in MW (e.g. 60000)."
        )
    if val < 0:
        raise ValueError(f"Capacity cannot be negative ({val} MW).")
    return val


def extract_europe_id(filepath_or_name: str, default_europe: str = "europe1") -> str:
    """
    Extract Europe identifier ('europe1' or 'europe2') from a filename or its contents.
    Supported patterns in filename:
        france_europe1.txt -> 'europe1'
        france_europe2.txt -> 'europe2'
        germany_europe_1.json -> 'europe1'
        germany_eur2.json -> 'europe2'
    If not specified in filename or file contents, defaults to default_europe.
    """
    basename = os.path.basename(filepath_or_name)
    stem = os.path.splitext(basename)[0].lower()

    if re.search(r"(?:^|[_\-\s])(?:europe[_\-\s]*2|eur[_\-\s]*2)(?:[_\-\s]|$)", stem):
        return "europe2"
    if re.search(r"(?:^|[_\-\s])(?:europe[_\-\s]*1|eur[_\-\s]*1)(?:[_\-\s]|$)", stem):
        return "europe1"

    # Inspect file content if available
    if os.path.isfile(filepath_or_name):
        try:
            if filepath_or_name.endswith(".json"):
                with open(filepath_or_name, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    val = data.get("europe") or data.get("europe_id") or data.get("scenario")
                    if val:
                        val_str = str(val).strip().lower()
                        if "2" in val_str:
                            return "europe2"
                        if "1" in val_str:
                            return "europe1"
            else:
                with open(filepath_or_name, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or line.startswith("//"):
                            continue
                        if ":" in line or "=" in line:
                            sep = ":" if ":" in line else "="
                            parts = line.split(sep, 1)
                            key = parts[0].strip().lower()
                            if key in ("europe", "europe_id", "scenario"):
                                val_str = parts[1].strip().lower()
                                if "2" in val_str:
                                    return "europe2"
                                if "1" in val_str:
                                    return "europe1"
        except Exception:
            pass

    return default_europe


def extract_country_and_europe(filepath: str, default_europe: str = "europe1") -> Tuple[str, str]:
    """Extract country name and Europe identifier for an investment file."""
    country, _ = load_country_capacities(filepath=filepath)
    europe_id = extract_europe_id(filepath_or_name=filepath, default_europe=default_europe)
    return country, europe_id


def parse_investment_file(filepath: str, country: Optional[str] = None) -> Tuple[str, Dict[str, float]]:
    """
    Parse a student investment text file.
    Each line can be:
        nuclear: 60000
        wind_onshore = 25000
        solar_pv 35000
        country: france
    Lines starting with '#' or '//' are treated as comments.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Investment file not found: '{filepath}'")

    file_country: Optional[str] = None
    basename = os.path.basename(filepath)
    stem = os.path.splitext(basename)[0].lower()
    for c in AVAILABLE_COUNTRIES:
        if c in stem:
            file_country = c
            break

    if not file_country:
        tokens = re.split(r"[_\-\s.]+", stem)
        for token in tokens:
            if token in COUNTRY_ALIASES:
                file_country = COUNTRY_ALIASES[token]
                break

    capacities: Dict[str, float] = {}

    with open(filepath, "r", encoding="utf-8") as f:
        for line_idx, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue

            if ":" in line:
                parts = line.split(":", 1)
            elif "=" in line:
                parts = line.split("=", 1)
            elif "," in line:
                parts = line.split(",", 1)
            else:
                parts = line.split(None, 1)

            if len(parts) != 2:
                raise ValueError(
                    f"Syntax error on line {line_idx} in '{filepath}': '{line}'. "
                    f"Expected format: 'asset: capacity' (e.g., 'nuclear: 60000')."
                )

            key = parts[0].strip().lower()
            val = parts[1].strip()

            if key in ("country", "pays"):
                file_country = normalize_country_name(val)
                continue

            asset = normalize_asset_name(key)
            capa = parse_capacity_value(val)
            capacities[asset] = capa

    resolved_country = country or file_country
    if not resolved_country:
        raise ValueError(
            f"Country not specified for file '{filepath}'. "
            f"Please name your file '{AVAILABLE_COUNTRIES[1]}.txt', add 'country: <country>' "
            f"in the file, or pass '--country <country>' as argument."
        )

    resolved_country = normalize_country_name(resolved_country)
    return resolved_country, capacities


def parse_country_json_file(filepath: str, country: Optional[str] = None) -> Tuple[str, Dict[str, float]]:
    """
    Parse an existing country JSON file (e.g. input/long_term_uc/countries/{country}.json).
    Extracts the country name and capacity dictionary.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Country JSON file not found: '{filepath}'")

    with open(filepath, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON file '{filepath}': {exc}")

    file_country: Optional[str] = data.get("team")
    if not file_country:
        basename = os.path.basename(filepath)
        stem = os.path.splitext(basename)[0].lower()
        for c in AVAILABLE_COUNTRIES:
            if c in stem:
                file_country = c
                break
        if not file_country:
            tokens = re.split(r"[_\-\s.]+", stem)
            for token in tokens:
                if token in COUNTRY_ALIASES:
                    file_country = COUNTRY_ALIASES[token]
                    break

    resolved_country = country or file_country
    if not resolved_country:
        raise ValueError(
            f"Country not specified in JSON file '{filepath}' (missing 'team' key)."
        )

    resolved_country = normalize_country_name(resolved_country)

    raw_capas: dict = {}
    if "capacities_tb_overwritten" in data and isinstance(data["capacities_tb_overwritten"], dict):
        raw_capas = data["capacities_tb_overwritten"].get(resolved_country, {})
        if not raw_capas and len(data["capacities_tb_overwritten"]) == 1:
            raw_capas = next(iter(data["capacities_tb_overwritten"].values()))
    elif "capacities" in data and isinstance(data["capacities"], dict):
        raw_capas = data["capacities"]

    capacities: Dict[str, float] = {}
    for k, v in raw_capas.items():
        try:
            asset = normalize_asset_name(k)
            capacities[asset] = float(v)
        except Exception:
            pass

    return resolved_country, capacities


def load_country_capacities(filepath: str, country: Optional[str] = None) -> Tuple[str, Dict[str, float]]:
    """Load country name and capacities from either a .txt or a .json file."""
    if filepath.endswith(".json"):
        return parse_country_json_file(filepath=filepath, country=country)
    return parse_investment_file(filepath=filepath, country=country)


def group_files_by_europe(
    filepaths: List[str],
    default_europe: str = "europe1",
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Groups collected investment files by Europe identifier ('europe1', 'europe2', ...).
    Returns:
        {europe_id: {country: {asset: capacity}}}
    """
    grouped_capas, _ = group_files_by_europe_with_sources(filepaths, default_europe=default_europe)
    return grouped_capas


def group_files_by_europe_with_sources(
    filepaths: List[str],
    default_europe: str = "europe1",
) -> Tuple[Dict[str, Dict[str, Dict[str, float]]], Dict[str, Dict[str, str]]]:
    """
    Groups collected investment files by Europe identifier and tracks file sources.
    Returns:
        (grouped_capacities, grouped_sources)
        where:
        grouped_capacities: {europe_id: {country: capacities}}
        grouped_sources: {europe_id: {country: filepath}}
    """
    grouped_capas: Dict[str, Dict[str, Dict[str, float]]] = {}
    grouped_srcs: Dict[str, Dict[str, str]] = {}
    for fpath in filepaths:
        country, capacities = load_country_capacities(filepath=fpath)
        europe_id = extract_europe_id(filepath_or_name=fpath, default_europe=default_europe)
        if europe_id not in grouped_capas:
            grouped_capas[europe_id] = {}
            grouped_srcs[europe_id] = {}
        grouped_capas[europe_id][country] = capacities
        grouped_srcs[europe_id][country] = fpath
    return grouped_capas, grouped_srcs


def collect_investment_files(target: Union[str, List[str]], extension: str = ".txt") -> List[str]:
    """Find all investment files (.txt or .json) in a given directory or from a list of paths."""
    ext = extension if extension.startswith(".") else f".{extension}"
    pattern = f"*{ext}"

    if isinstance(target, list):
        files = []
        for item in target:
            if os.path.isdir(item):
                files.extend(glob.glob(os.path.join(item, pattern)))
            elif os.path.isfile(item) and item.endswith(ext):
                files.append(item)
        return sorted(list(set(files)))

    if os.path.isdir(target):
        files = glob.glob(os.path.join(target, pattern))
        return sorted(files)
    elif os.path.isfile(target):
        return [target] if target.endswith(ext) else []
    return []


def get_selected_target_year(
    europe_params_path: str = "input/long_term_uc/elec-europe_params_to-be-modif.json",
    default: int = 2033,
) -> int:
    """Read the target year from elec-europe_params_to-be-modif.json."""
    if os.path.isfile(europe_params_path):
        try:
            with open(europe_params_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return int(data.get("selected_target_year", default))
        except Exception:
            pass
    return default


def get_eraa_available_prod_types(
    country: str,
    target_year: int = 2033,
    eraa_values_path: str = "input/long_term_uc/elec-europe_eraa-available-values.json",
) -> Optional[List[str]]:
    """Return the list of aggregate production types available in ERAA for a given country and year."""
    if not os.path.isfile(eraa_values_path):
        return None
    try:
        with open(eraa_values_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        types_by_country = data.get("aggreg_prod_types", {}).get(country, {})
        return types_by_country.get(str(target_year)) or types_by_country.get(target_year)
    except Exception as e:
        logging.warning(f"Could not read {eraa_values_path}: {e}")
        return None


def write_country_json(country: str, capacities: Dict[str, float],
                       countries_dir: str = "input/long_term_uc/countries",
                       target_year: Optional[int] = None) -> str:
    """
    Write or update input/long_term_uc/countries/{country}.json.
    Sets team, selected_prod_types, and capacities_tb_overwritten.
    Filters out assets not present in the ERAA dataset for this country and year.
    """
    os.makedirs(countries_dir, exist_ok=True)
    json_path = os.path.join(countries_dir, f"{country}.json")

    if target_year is None:
        target_year = get_selected_target_year()

    available_eraa = get_eraa_available_prod_types(country=country, target_year=target_year)
    valid_capacities: Dict[str, float] = {}
    for asset, capa in capacities.items():
        if available_eraa is not None and asset not in available_eraa:
            print(f"      [!] Warning: '{asset}' is not available in the ERAA dataset for '{country}' in {target_year}. Asset ignored.")
            continue
        valid_capacities[asset] = capa

    active_assets = [asset for asset, capa in valid_capacities.items() if capa > 0]
    if ProdTypeNames.failure not in active_assets:
        active_assets.append(ProdTypeNames.failure)

    data_to_write = {
        "team": country,
        "selected_prod_types": {country: active_assets},
        "capacities_tb_overwritten": {country: valid_capacities}
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data_to_write, f, indent=2, ensure_ascii=False)

    return json_path


DEFAULT_PERIOD_START: str = "1900/1/1"
DEFAULT_PERIOD_END: str = "1901/1/1"
TEST_PERIOD_START: str = "1900/1/1"
TEST_PERIOD_END: str = "1900/1/15"  # 14 days / 2 weeks for fast debugging


def resolve_simulation_period(
    is_test: bool = False,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Resolve the simulation start and end dates based on flags and parameters.

    In test/debug mode (is_test=True):
      - Defaults to a 2-week period (1900/1/1 to 1900/1/15).
      - If a non-default period_start is provided, it is preserved.
      - If a non-default period_end is provided, it is preserved.
    In standard mode (is_test=False):
      - Defaults to the full year (1900/1/1 to 1901/1/1).
    """
    if is_test:
        start = period_start if (period_start and period_start != DEFAULT_PERIOD_START) else TEST_PERIOD_START
        end = period_end if (period_end and period_end != DEFAULT_PERIOD_END) else TEST_PERIOD_END
        return start, end

    return period_start or DEFAULT_PERIOD_START, period_end or DEFAULT_PERIOD_END


def update_europe_params(mode: str = "europe", team: Optional[str] = None,
                         period_start: str = DEFAULT_PERIOD_START, period_end: str = DEFAULT_PERIOD_END,
                         europe_params_path: str = "input/long_term_uc/elec-europe_params_to-be-modif.json") -> None:
    """
    Enforce and set 'mode' to 'europe', and configure the simulation period
    (by default full year '1900/1/1' to '1901/1/1', or test period '1900/1/1' to '1900/1/15')
    in elec-europe_params_to-be-modif.json.
    The runner exclusively operates in European mode ('europe'). Solo mode is not supported for the runner.
    """
    if mode != "europe":
        raise ValueError(
            f"The runner exclusively operates in 'europe' mode (received mode='{mode}'). "
            f"Solo mode is not supported by the runner."
        )

    if not os.path.isfile(europe_params_path):
        return

    try:
        with open(europe_params_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        modified = False
        if data.get("mode") != "europe":
            data["mode"] = "europe"
            modified = True
        if team and data.get("team") != team:
            data["team"] = team
            modified = True
        if period_start and data.get("uc_period_start") != period_start:
            data["uc_period_start"] = period_start
            modified = True
        if period_end and data.get("uc_period_end") != period_end:
            data["uc_period_end"] = period_end
            modified = True

        if modified:
            with open(europe_params_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logging.info(
                f"Updated {europe_params_path}: mode='europe' team='{team or data.get('team')}' "
                f"period=[{period_start} - {period_end}]"
            )
    except Exception as e:
        logging.warning(f"Could not update {europe_params_path}: {e}")


def update_team_in_europe_params(country: str,
                                 europe_params_path: str = "input/long_term_uc/elec-europe_params_to-be-modif.json") -> None:
    """Ensure the 'team' parameter matches the country in elec-europe_params_to-be-modif.json."""
    update_europe_params(mode="europe", team=country, europe_params_path=europe_params_path)


def find_latest_summary_file(output_base_dir: str = "output/long_term_uc") -> Optional[str]:
    """Find the most recently generated uc-summary_*.json file."""
    pattern = os.path.join(output_base_dir, "**", "uc-summary_*.json")
    files = glob.glob(pattern, recursive=True)
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def find_new_summary_file(before_files: set, output_base_dir: str = "output/long_term_uc") -> Optional[str]:
    """Find the summary file created after before_files was captured."""
    pattern = os.path.join(output_base_dir, "**", "uc-summary_*.json")
    current_files = set(glob.glob(pattern, recursive=True))
    new_files = current_files - before_files
    if new_files:
        return sorted(list(new_files), key=os.path.getmtime, reverse=True)[0]
    return find_latest_summary_file(output_base_dir=output_base_dir)


# Mapping of model prod types to technology.json keys
TECH_MAPPING: Dict[str, str] = {
    "nuclear": "Nuclear",
    "solar_pv": "Solar PV",
    "wind_onshore": "Wind Onshore",
    "wind_offshore": "Wind Offshore",
    "hydro_run_of_river": "Hydro ROR",
    "gas": "CCGT",
    "oil": "Oil",
    "coal": "Hard Coal",
    "lignite": "Lignite",
    "biofuel": "Biomass",
}

# Reference techno-economic parameters (fallback if technology.json is missing or for storage/hydro assets)
# CAPEX: EUR/MW, Lifetime: years, WACC: fraction
DEFAULT_TECH_PARAMS: Dict[str, Dict[str, float]] = {
    "nuclear": {"CAPEX": 4500e3, "Lifetime": 60, "WACC": 0.04},
    "solar_pv": {"CAPEX": 500e3, "Lifetime": 20, "WACC": 0.05},
    "wind_onshore": {"CAPEX": 1200e3, "Lifetime": 25, "WACC": 0.05},
    "wind_offshore": {"CAPEX": 2200e3, "Lifetime": 25, "WACC": 0.08},
    "hydro_run_of_river": {"CAPEX": 1600e3, "Lifetime": 50, "WACC": 0.04},
    "hydro_reservoir": {"CAPEX": 2000e3, "Lifetime": 50, "WACC": 0.04},
    "hydro_pondage": {"CAPEX": 1600e3, "Lifetime": 50, "WACC": 0.04},
    "hydro_pump_storage_closed_loop": {"CAPEX": 1800e3, "Lifetime": 40, "WACC": 0.05},
    "hydro_pump_storage_open_loop": {"CAPEX": 1500e3, "Lifetime": 40, "WACC": 0.05},
    "batteries": {"CAPEX": 1200e3, "Lifetime": 15, "WACC": 0.06},  # 300 €/kWh * 4h * 1000 kW/MW
    "dsr": {"CAPEX": 50e3, "Lifetime": 10, "WACC": 0.05},
    "gas": {"CAPEX": 1000e3, "Lifetime": 30, "WACC": 0.08},
    "oil": {"CAPEX": 500e3, "Lifetime": 20, "WACC": 0.08},
    "coal": {"CAPEX": 1800e3, "Lifetime": 35, "WACC": 0.08},
    "lignite": {"CAPEX": 1800e3, "Lifetime": 35, "WACC": 0.08},
    "biofuel": {"CAPEX": 1500e3, "Lifetime": 40, "WACC": 0.08},
    "others_fatal": {"CAPEX": 1000e3, "Lifetime": 25, "WACC": 0.05},
    "failure": {"CAPEX": 0.0, "Lifetime": 1, "WACC": 0.0},
}


def calc_crf(wacc: float, lifetime: int) -> float:
    """Capital Recovery Factor (CRF) / annuity factor."""
    if wacc <= 0 or lifetime <= 0:
        return 1.0 / max(lifetime, 1)
    return wacc * ((1.0 + wacc) ** lifetime) / (((1.0 + wacc) ** lifetime) - 1.0)


def calc_annualized_capex_per_mw(capex_eur_per_mw: float, wacc: float, lifetime: int) -> float:
    """Calculate annualized CAPEX in EUR / MW / year."""
    crf = calc_crf(wacc=wacc, lifetime=lifetime)
    return capex_eur_per_mw * crf


def get_country_capacities_from_json(country: str,
                                     countries_dir: str = "input/long_term_uc/countries") -> Dict[str, float]:
    """Load capacities for a given country from its input/long_term_uc/countries/{country}.json file."""
    json_path = os.path.join(countries_dir, f"{country}.json")
    if not os.path.isfile(json_path):
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("capacities_tb_overwritten", {}).get(country, {})
    except Exception:
        return {}


def compute_country_annualized_capex(
    capacities: Dict[str, float],
    tech_data_path: str = "data/fuel_sources/technology.json",
) -> Tuple[float, float]:
    """
    Compute total overnight CAPEX (EUR) and total annualized CAPEX (EUR/year)
    for a dictionary of production asset capacities in MW.
    Returns: (total_overnight_capex_eur, total_annualized_capex_eur_per_year)
    """
    tech_data: dict = {}
    if os.path.isfile(tech_data_path):
        try:
            with open(tech_data_path, "r", encoding="utf-8") as f:
                tech_data = json.load(f)
        except Exception:
            pass

    total_overnight = 0.0
    total_annualized = 0.0

    for asset, capa_mw in capacities.items():
        if capa_mw <= 0 or asset == ProdTypeNames.failure:
            continue

        tech_key = TECH_MAPPING.get(asset)
        params = None
        if tech_key and tech_key in tech_data:
            params = tech_data[tech_key]
        elif asset in DEFAULT_TECH_PARAMS:
            params = DEFAULT_TECH_PARAMS[asset]

        if not params:
            continue

        capex_per_mw = float(params.get("CAPEX", 0.0))
        lifetime = int(params.get("Lifetime", 25))
        wacc = float(params.get("WACC", 0.05))

        total_overnight += capa_mw * capex_per_mw
        total_annualized += capa_mw * calc_annualized_capex_per_mw(capex_per_mw, wacc, lifetime)

    return total_overnight, total_annualized


def get_production_from_opt_power_csv(summary_file_path: Optional[str]) -> Dict[str, float]:
    """Compute per-country total generated energy in GWh from opt_power_*.csv if available."""
    if not summary_file_path or not os.path.isfile(summary_file_path):
        return {}
    dir_path = os.path.dirname(summary_file_path)
    csv_files = glob.glob(os.path.join(dir_path, "opt_power_*.csv"))
    if not csv_files:
        return {}
    try:
        import pandas as pd
        df = pd.read_csv(csv_files[0])
        prod_cols = [c for c in df.columns if c != "date" and not c.endswith("_failure")]
        per_country_prod_gwh: Dict[str, float] = {}
        for col in prod_cols:
            tri = col.split("_")[0]
            per_country_prod_gwh[tri] = per_country_prod_gwh.get(tri, 0.0) + float(df[col].sum()) / 1e3
        return per_country_prod_gwh
    except Exception:
        return {}


def display_summary(summary_data: dict, country: str) -> None:
    """
    Display summary for a country within the European simulation.
    Delegates to display_multi_country_summary as the runner runs exclusively in Europe mode.
    """
    display_multi_country_summary(summary_data=summary_data, countries=[country])


def display_multi_country_summary(summary_data: dict,
                                  countries: Optional[List[str]] = None,
                                  updated_countries: Optional[List[str]] = None,
                                  per_country_capacities: Optional[Dict[str, Dict[str, float]]] = None,
                                  summary_file_path: Optional[str] = None) -> None:
    """
    Print a clean comparative multi-country summary table for European mode.
    Displays ENS, Loss of Load hours, OPEX, annualized CAPEX, TOTAL cost, cost per MWh produced, and CO2 emissions.
    Supports both full country names and 3-letter trigrams in summary_data keys.
    """
    total_cost = summary_data.get("total_cost", 0.0)
    total_op_cost = summary_data.get("total_operational_cost", 0.0)
    total_co2 = summary_data.get("total_co2_emissions", 0.0)

    per_country_ens = summary_data.get("per_country_ens", {}) or {}
    per_country_fail_h = summary_data.get("per_country_n_failure_hours", {}) or {}
    per_country_cost = summary_data.get("per_country_total_cost", {}) or {}
    per_country_op_cost = summary_data.get("per_country_total_operational_cost", {}) or {}
    per_country_co2 = summary_data.get("per_country_co2_emissions", {}) or {}

    # Production data (in GWh)
    per_country_prod = summary_data.get("per_country_production", {}) or {}
    if not per_country_prod and summary_file_path:
        per_country_prod = get_production_from_opt_power_csv(summary_file_path=summary_file_path)

    total_ens = sum(per_country_ens.values()) if per_country_ens else 0.0
    max_fail_h = max(per_country_fail_h.values()) if per_country_fail_h else 0.0

    display_countries = countries if countries is not None else AVAILABLE_COUNTRIES
    updated_set = set(updated_countries or [])

    print("\n" + "=" * 110)
    print("                              RESULTS OF THE EUROPEAN INTERCONNECTED SIMULATION")
    print("=" * 110)
    header = f"{'COUNTRY':<20} | {'ENS (MWh)':>10} | {'FAIL.(h)':>8} | {'OPEX(M€/yr)':>11} | {'CAPEX(M€/yr)':>12} | {'TOTAL(M€/yr)':>12} | {'COST(€/MWh)':>11} | {'CO2 (Mt)':>8}"
    print(header)
    print("-" * 110)

    total_europe_capex_m_yr = 0.0
    total_europe_overnight_b = 0.0
    total_europe_opex = 0.0
    total_europe_prod_gwh = 0.0

    for country in sorted(display_countries):
        tri = set_country_trigram(country)
        ens = per_country_ens.get(tri, per_country_ens.get(country, 0.0))
        fail_h = per_country_fail_h.get(tri, per_country_fail_h.get(country, 0.0))

        # OPEX for country (operational cost, fallback to total cost)
        opex = per_country_op_cost.get(tri, per_country_op_cost.get(country, per_country_cost.get(tri, per_country_cost.get(country, 0.0))))
        total_europe_opex += opex

        # CAPEX for country
        country_capas = {}
        if per_country_capacities and country in per_country_capacities:
            country_capas = per_country_capacities[country]
        else:
            country_capas = get_country_capacities_from_json(country=country)

        overnight_eur, annualized_eur = compute_country_annualized_capex(capacities=country_capas)
        capex_m_yr = annualized_eur / 1e6
        overnight_b = overnight_eur / 1e9

        total_europe_capex_m_yr += capex_m_yr
        total_europe_overnight_b += overnight_b

        total_m_yr = opex + capex_m_yr
        co2 = per_country_co2.get(tri, per_country_co2.get(country, 0.0))

        # Cost per MWh produced (€/MWh = (M€ * 1e6) / (GWh * 1e3) = M€ * 1000 / GWh)
        prod_gwh = per_country_prod.get(tri, per_country_prod.get(country, 0.0))
        total_europe_prod_gwh += prod_gwh
        if prod_gwh > 0:
            cost_per_mwh = (total_m_yr * 1000.0) / prod_gwh
            cost_mwh_str = f"{cost_per_mwh:>11,.1f}"
        else:
            cost_mwh_str = f"{'-':>11}"

        opex_str = f"{opex:>11,.1f}" if opex > 0 else f"{'-':>11}"
        capex_str = f"{capex_m_yr:>12,.1f}" if capex_m_yr > 0 else f"{'-':>12}"
        total_str = f"{total_m_yr:>12,.1f}" if total_m_yr > 0 else f"{'-':>12}"
        co2_str = f"{co2:>8,.2f}" if co2 > 0 else f"{'-':>8}"

        tag = " *" if country in updated_set else ""
        c_display = f"{country}{tag}"
        print(f"{c_display:<20} | {ens:>10,.1f} | {fail_h:>8.1f} | {opex_str} | {capex_str} | {total_str} | {cost_mwh_str} | {co2_str}")

    # European total OPEX: prefer global metric if available
    display_europe_opex = total_op_cost if total_op_cost > 0 else total_europe_opex
    total_europe_cost = display_europe_opex + total_europe_capex_m_yr

    # European cost per MWh
    if total_europe_prod_gwh > 0:
        total_europe_cost_mwh = (total_europe_cost * 1000.0) / total_europe_prod_gwh
        total_europe_cost_mwh_str = f"{total_europe_cost_mwh:>11,.1f}"
    else:
        total_europe_cost_mwh_str = f"{'-':>11}"

    print("-" * 110)
    print(f"{'TOTAL EUROPE':<20} | {total_ens:>10,.1f} | {max_fail_h:>8.1f} | {display_europe_opex:>11,.1f} | {total_europe_capex_m_yr:>12,.1f} | {total_europe_cost:>12,.1f} | {total_europe_cost_mwh_str} | {total_co2:>8,.2f}")
    print("=" * 110)
    print(f"  Total operational cost (OPEX) : {display_europe_opex:,.2f} M€/year")
    print(f"  Total annualized CAPEX        : {total_europe_capex_m_yr:,.2f} M€/year (Total overnight: ~{total_europe_overnight_b:,.1f} B€)")
    print(f"  Total system cost (OPEX+CAPEX): {total_europe_cost:,.2f} M€/year")
    if total_europe_prod_gwh > 0:
        total_europe_prod_twh = total_europe_prod_gwh / 1000.0
        avg_opex_mwh = (display_europe_opex * 1000.0) / total_europe_prod_gwh
        avg_capex_mwh = (total_europe_capex_m_yr * 1000.0) / total_europe_prod_gwh
        avg_cost_mwh = (total_europe_cost * 1000.0) / total_europe_prod_gwh
        print(f"  Total generation              : {total_europe_prod_twh:,.2f} TWh ({total_europe_prod_gwh:,.0f} GWh)")
        print(f"  Average electricity cost      : {avg_cost_mwh:,.2f} €/MWh (OPEX: {avg_opex_mwh:,.2f} €/MWh, CAPEX: {avg_capex_mwh:,.2f} €/MWh)")
    if updated_set:
        print(f"  (*) Countries updated by the runner during this session: {', '.join(sorted(updated_set))}")

    # Countries with ENS
    countries_with_fail = [
        c for c in display_countries
        if per_country_ens.get(set_country_trigram(c), per_country_ens.get(c, 0.0)) > 0.1
        or per_country_fail_h.get(set_country_trigram(c), per_country_fail_h.get(c, 0.0)) > 0
    ]
    if countries_with_fail:
        print(f"\n[!] LOSS OF LOAD / FAILURE DETECTED in: {', '.join(countries_with_fail)}")
        print("    These countries must reinforce dispatchable capacities, renewables, or flexibility/interconnections.")
    else:
        print("\n[OK] NO LOSS OF LOAD: The entire European system is balanced!")
    print()


def run_simulation(script_path: str = "my_little_europe_lt_uc.py") -> int:
    """Execute the simulation script via subprocess, streaming stdout/stderr."""
    cmd = [sys.executable, script_path]
    logging.info(f"Running simulation: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def extract_simulation_metrics(
    summary_data: dict,
    per_country_capacities: Optional[Dict[str, Dict[str, float]]] = None,
    summary_file_path: Optional[str] = None,
    countries: Optional[List[str]] = None,
) -> dict:
    """
    Extract standardized European and per-country metrics from summary_data.
    """
    display_countries = countries if countries is not None else AVAILABLE_COUNTRIES

    total_op_cost = float(summary_data.get("total_operational_cost", 0.0))
    total_co2 = float(summary_data.get("total_co2_emissions", 0.0))

    per_country_ens = summary_data.get("per_country_ens", {}) or {}
    per_country_fail_h = summary_data.get("per_country_n_failure_hours", {}) or {}
    per_country_cost = summary_data.get("per_country_total_cost", {}) or {}
    per_country_op_cost = summary_data.get("per_country_total_operational_cost", {}) or {}
    per_country_co2 = summary_data.get("per_country_co2_emissions", {}) or {}

    per_country_prod = summary_data.get("per_country_production", {}) or {}
    if not per_country_prod and summary_file_path:
        per_country_prod = get_production_from_opt_power_csv(summary_file_path=summary_file_path)

    total_ens = sum(float(v) for v in per_country_ens.values()) if per_country_ens else 0.0
    max_fail_h = max(float(v) for v in per_country_fail_h.values()) if per_country_fail_h else 0.0

    total_europe_capex_m_yr = 0.0
    total_europe_overnight_b = 0.0
    total_europe_opex = 0.0
    total_europe_prod_gwh = 0.0

    per_country_metrics: Dict[str, dict] = {}

    for country in sorted(display_countries):
        tri = set_country_trigram(country)
        ens = float(per_country_ens.get(tri, per_country_ens.get(country, 0.0)))
        fail_h = float(per_country_fail_h.get(tri, per_country_fail_h.get(country, 0.0)))

        opex = float(per_country_op_cost.get(tri, per_country_op_cost.get(country, per_country_cost.get(tri, per_country_cost.get(country, 0.0)))))
        total_europe_opex += opex

        country_capas = {}
        if per_country_capacities and country in per_country_capacities:
            country_capas = per_country_capacities[country]
        else:
            country_capas = get_country_capacities_from_json(country=country)

        overnight_eur, annualized_eur = compute_country_annualized_capex(capacities=country_capas)
        capex_m_yr = annualized_eur / 1e6
        overnight_b = overnight_eur / 1e9

        total_europe_capex_m_yr += capex_m_yr
        total_europe_overnight_b += overnight_b

        total_m_yr = opex + capex_m_yr
        raw_co2 = float(per_country_co2.get(tri, per_country_co2.get(country, 0.0)))
        # CO2 emissions in UCSummaryMetrics are in ktCO2eq. Convert to Mt if in kt (> 500)
        co2 = (raw_co2 / 1000.0) if raw_co2 > 500.0 else raw_co2

        prod_gwh = float(per_country_prod.get(tri, per_country_prod.get(country, 0.0)))
        total_europe_prod_gwh += prod_gwh
        cost_per_mwh = (total_m_yr * 1000.0) / prod_gwh if prod_gwh > 0 else 0.0

        per_country_metrics[country] = {
            "ens_mwh": ens,
            "failure_hours": fail_h,
            "opex_m_yr": opex,
            "capex_m_yr": capex_m_yr,
            "total_cost_m_yr": total_m_yr,
            "cost_per_mwh": cost_per_mwh,
            "co2_mt": co2,
            "production_gwh": prod_gwh,
        }

    display_europe_opex = total_op_cost if total_op_cost > 0 else total_europe_opex
    total_europe_cost = display_europe_opex + total_europe_capex_m_yr
    avg_cost_mwh = (total_europe_cost * 1000.0) / total_europe_prod_gwh if total_europe_prod_gwh > 0 else 0.0

    total_co2_raw = float(summary_data.get("total_co2_emissions", 0.0))
    total_co2_mt = (total_co2_raw / 1000.0) if total_co2_raw > 500.0 else total_co2_raw

    return {
        "summary_file": summary_file_path,
        "total_cost_m_yr": total_europe_cost,
        "total_operational_cost_m_yr": display_europe_opex,
        "total_annualized_capex_m_yr": total_europe_capex_m_yr,
        "total_overnight_capex_b": total_europe_overnight_b,
        "avg_cost_per_mwh": avg_cost_mwh,
        "total_co2_emissions_mt": total_co2_mt,
        "total_production_gwh": total_europe_prod_gwh,
        "total_production_twh": total_europe_prod_gwh / 1000.0,
        "total_ens_mwh": total_ens,
        "max_failure_hours": max_fail_h,
        "per_country": per_country_metrics,
    }


def compute_europe_comparison(metrics_eur1: dict, metrics_eur2: dict) -> dict:
    """
    Compute delta (Eur2 - Eur1) and relative change (%) between Europe 1 and Europe 2.
    """
    def _diff(val1: float, val2: float) -> dict:
        delta = val2 - val1
        pct = ((val2 - val1) / val1 * 100.0) if abs(val1) > 1e-6 else (0.0 if abs(val2) < 1e-6 else None)
        return {"eur1": val1, "eur2": val2, "delta": delta, "pct_change": pct}

    global_keys = [
        "total_cost_m_yr",
        "total_operational_cost_m_yr",
        "total_annualized_capex_m_yr",
        "total_overnight_capex_b",
        "avg_cost_per_mwh",
        "total_co2_emissions_mt",
        "total_production_twh",
        "total_ens_mwh",
        "max_failure_hours",
    ]

    global_diffs = {}
    for k in global_keys:
        v1 = float(metrics_eur1.get(k, 0.0))
        v2 = float(metrics_eur2.get(k, 0.0))
        global_diffs[k] = _diff(v1, v2)

    countries = sorted(list(set(metrics_eur1.get("per_country", {}).keys()) | set(metrics_eur2.get("per_country", {}).keys())))
    country_diffs = {}
    for c in countries:
        c1 = metrics_eur1.get("per_country", {}).get(c, {})
        c2 = metrics_eur2.get("per_country", {}).get(c, {})
        country_diffs[c] = {
            "total_cost_m_yr": _diff(c1.get("total_cost_m_yr", 0.0), c2.get("total_cost_m_yr", 0.0)),
            "opex_m_yr": _diff(c1.get("opex_m_yr", 0.0), c2.get("opex_m_yr", 0.0)),
            "capex_m_yr": _diff(c1.get("capex_m_yr", 0.0), c2.get("capex_m_yr", 0.0)),
            "co2_mt": _diff(c1.get("co2_mt", 0.0), c2.get("co2_mt", 0.0)),
            "ens_mwh": _diff(c1.get("ens_mwh", 0.0), c2.get("ens_mwh", 0.0)),
            "failure_hours": _diff(c1.get("failure_hours", 0.0), c2.get("failure_hours", 0.0)),
            "production_gwh": _diff(c1.get("production_gwh", 0.0), c2.get("production_gwh", 0.0)),
            "cost_per_mwh": _diff(c1.get("cost_per_mwh", 0.0), c2.get("cost_per_mwh", 0.0)),
        }

    return {
        "global": global_diffs,
        "per_country": country_diffs,
        "europe1_summary_file": metrics_eur1.get("summary_file"),
        "europe2_summary_file": metrics_eur2.get("summary_file"),
    }


def format_comparison_table(
    metrics_eur1: dict,
    metrics_eur2: dict,
    comparison: dict,
    eur1_label: str = "Europe 1",
    eur2_label: str = "Europe 2",
) -> str:
    """Format a comprehensive comparative dashboard into a string."""
    lines = []
    width = 133
    sep = "=" * width
    thin_sep = "-" * width

    title = f"COMPARATIVE DASHBOARD: {eur1_label.upper()} vs {eur2_label.upper()}"
    lines.append("")
    lines.append(sep)
    lines.append(f"{title:^{width}}")
    lines.append(sep)

    lines.append("\n[1] GLOBAL EUROPE SYSTEM METRICS:")
    lines.append(thin_sep)
    hdr1 = f"{'METRIC':<48} | {eur1_label:>18} | {eur2_label:>18} | {'DELTA (E2-E1)':>20} | {'CHANGE (%)':>16}"
    lines.append(hdr1)
    lines.append(thin_sep)

    def _fmt_pct(val):
        if val is None:
            return f"{'N/A':>16}"
        sign = "+" if val > 0 else ""
        return f"{sign}{val:>15.1f}%"

    g = comparison.get("global", {})
    metric_rows = [
        ("Total System Cost (OPEX+CAPEX)", "total_cost_m_yr", "M€/yr", "{:>18,.2f}", "{:>+20,.2f}"),
        ("Operational Cost (OPEX)", "total_operational_cost_m_yr", "M€/yr", "{:>18,.2f}", "{:>+20,.2f}"),
        ("Annualized CAPEX", "total_annualized_capex_m_yr", "M€/yr", "{:>18,.2f}", "{:>+20,.2f}"),
        ("Total Overnight CAPEX", "total_overnight_capex_b", "B€", "{:>18,.2f}", "{:>+20,.2f}"),
        ("Average Electricity Cost", "avg_cost_per_mwh", "€/MWh", "{:>18,.2f}", "{:>+20,.2f}"),
        ("CO2 Emissions", "total_co2_emissions_mt", "Mt", "{:>18,.2f}", "{:>+20,.2f}"),
        ("Total Generation", "total_production_twh", "TWh", "{:>18,.2f}", "{:>+20,.2f}"),
        ("Energy Not Served (ENS)", "total_ens_mwh", "MWh", "{:>18,.1f}", "{:>+20,.1f}"),
        ("Loss of Load Max Duration", "max_failure_hours", "h", "{:>18.1f}", "{:>+20.1f}"),
    ]

    for label, key, unit, val_fmt, delta_fmt in metric_rows:
        item = g.get(key, {})
        v1 = item.get("eur1", 0.0)
        v2 = item.get("eur2", 0.0)
        delta = item.get("delta", 0.0)
        pct = item.get("pct_change")
        l_str = f"{label} ({unit})" if unit else label
        v1_str = val_fmt.format(v1)
        v2_str = val_fmt.format(v2)
        d_str = delta_fmt.format(delta)
        pct_str = _fmt_pct(pct)
        lines.append(f"{l_str:<48} | {v1_str} | {v2_str} | {d_str} | {pct_str}")

    lines.append(thin_sep)

    lines.append("\n[2] PER-COUNTRY COMPARISON:")
    lines.append(thin_sep)
    hdr2 = (
        f"{'COUNTRY':<18} | {'TOTAL SYSTEM COST (M€/yr)':^29} | {'CO2 EMISSIONS (Mt)':^24} | "
        f"{'ENERGY NOT SERVED (MWh)':^26} | {'FAILURE HOURS (h)':^24}"
    )
    subhdr2 = (
        f"{'':<18} | {'Eur 1':>8} | {'Eur 2':>8} | {'Delta':>7} | {'Eur 1':>6} | {'Eur 2':>6} | {'Delta':>6} | "
        f"{'Eur 1':>7} | {'Eur 2':>7} | {'Delta':>6} | {'Eur 1':>6} | {'Eur 2':>6} | {'Delta':>6}"
    )
    sub_sep = (
        f"{'-'*18}-+-{'-'*8}-+-{'-'*8}-+-{'-'*7}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}-+-"
        f"{'-'*7}-+-{'-'*7}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}"
    )
    lines.append(hdr2)
    lines.append(subhdr2)
    lines.append(sub_sep)

    c_diffs = comparison.get("per_country", {})
    for country in sorted(c_diffs.keys()):
        cd = c_diffs[country]
        cost = cd.get("total_cost_m_yr", {})
        co2 = cd.get("co2_mt", {})
        ens = cd.get("ens_mwh", {})
        fail = cd.get("failure_hours", {})

        cost_e1 = f"{cost.get('eur1', 0.0):>8,.0f}"
        cost_e2 = f"{cost.get('eur2', 0.0):>8,.0f}"
        cost_d = f"{cost.get('delta', 0.0):>+7,.0f}"

        # CO2 emissions in Mt: if raw values exceed 500 (e.g. from tests or raw inputs), divide by 1000
        co2_val1 = co2.get('eur1', 0.0)
        co2_val2 = co2.get('eur2', 0.0)
        c1 = co2_val1 / 1000.0 if abs(co2_val1) > 500.0 else co2_val1
        c2 = co2_val2 / 1000.0 if abs(co2_val2) > 500.0 else co2_val2
        c_delta = c2 - c1
        co2_e1 = f"{c1:>6.1f}"
        co2_e2 = f"{c2:>6.1f}"
        co2_d = f"{c_delta:>+6.1f}"

        ens_e1 = f"{ens.get('eur1', 0.0):>7,.0f}"
        ens_e2 = f"{ens.get('eur2', 0.0):>7,.0f}"
        ens_d = f"{ens.get('delta', 0.0):>+6,.0f}"

        fail_e1 = f"{fail.get('eur1', 0.0):>6,.0f}"
        fail_e2 = f"{fail.get('eur2', 0.0):>6,.0f}"
        fail_d = f"{fail.get('delta', 0.0):>+6,.0f}"

        lines.append(
            f"{country:<18} | {cost_e1} | {cost_e2} | {cost_d} | {co2_e1} | {co2_e2} | {co2_d} | "
            f"{ens_e1} | {ens_e2} | {ens_d} | {fail_e1} | {fail_e2} | {fail_d}"
        )

    lines.append(sep)
    return "\n".join(lines) + "\n"


def display_europe_comparison(formatted_report: str) -> None:
    """Print comparative report to console."""
    print(formatted_report)


def save_comparison_results(
    comparison_data: dict,
    formatted_report: str,
    output_dir: str = "output/runner",
    filename_prefix: str = "comparison_europe1_vs_europe2",
    metrics_eur1: Optional[dict] = None,
    metrics_eur2: Optional[dict] = None,
    timestamp: Optional[datetime] = None,
) -> Tuple[str, str]:
    """
    Save the comparative results to both a timestamped text file and a JSON file
    in output_dir (default: output/runner/), and update latest pointer files.
    """
    os.makedirs(output_dir, exist_ok=True)
    dt = timestamp or datetime.now()
    ts_str = dt.strftime("%Y%m%d_%H%M%S")
    ts_readable = dt.strftime("%Y-%m-%d %H:%M:%S")

    # Enrich comparison data with metadata and raw Europe metrics for history tracking
    enriched_data = dict(comparison_data)
    enriched_data["timestamp"] = dt.isoformat()
    enriched_data["timestamp_str"] = ts_readable
    if metrics_eur1:
        enriched_data["europe1_metrics"] = metrics_eur1
    if metrics_eur2:
        enriched_data["europe2_metrics"] = metrics_eur2

    txt_filename = f"{filename_prefix}_{ts_str}.txt"
    json_filename = f"{filename_prefix}_{ts_str}.json"
    txt_path = os.path.join(output_dir, txt_filename)
    json_path = os.path.join(output_dir, json_filename)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(formatted_report)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(enriched_data, f, indent=2, ensure_ascii=False)

    # Also update latest convenience copies
    latest_txt_path = os.path.join(output_dir, f"{filename_prefix}_latest.txt")
    latest_json_path = os.path.join(output_dir, f"{filename_prefix}_latest.json")
    try:
        with open(latest_txt_path, "w", encoding="utf-8") as f:
            f.write(formatted_report)
        with open(latest_json_path, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logging.warning(f"Could not update latest pointer files: {exc}")

    return txt_path, json_path


def load_simulation_history(
    output_dir: str = "output/runner",
    target_europe: str = "europe1",
) -> List[dict]:
    """
    Load historical simulation runs from output_dir sorted chronologically.
    Filters out '_latest.json' and 'history_' files to avoid duplicates.
    Extracts metrics for target_europe ('europe1' or 'europe2').
    """
    if not os.path.isdir(output_dir):
        return []

    pattern = os.path.join(output_dir, "*.json")
    all_files = glob.glob(pattern)

    sim_files = [
        f for f in all_files
        if not os.path.basename(f).startswith("history_")
        and not os.path.basename(f).endswith("_latest.json")
    ]

    history = []
    for fpath in sim_files:
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            dt_str = data.get("timestamp_str")
            if not dt_str:
                mtime = os.path.getmtime(fpath)
                dt_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

            metrics = None
            if f"{target_europe}_metrics" in data and isinstance(data[f"{target_europe}_metrics"], dict):
                metrics = data[f"{target_europe}_metrics"]
            elif "per_country" in data:
                # Extract from comparison structure
                eur_key = "eur1" if target_europe == "europe1" else "eur2"
                glob_data = data.get("global", {})
                
                def _get_glob(k: str) -> float:
                    sub = glob_data.get(k, {})
                    if isinstance(sub, dict):
                        return float(sub.get(eur_key, sub.get("eur1", 0.0)))
                    return float(data.get(k, 0.0))

                metrics = {
                    "total_cost_m_yr": _get_glob("total_cost_m_yr"),
                    "total_operational_cost_m_yr": _get_glob("total_operational_cost_m_yr"),
                    "total_annualized_capex_m_yr": _get_glob("total_annualized_capex_m_yr"),
                    "total_co2_emissions_mt": _get_glob("total_co2_emissions_mt"),
                    "total_ens_mwh": _get_glob("total_ens_mwh"),
                    "max_failure_hours": _get_glob("max_failure_hours"),
                    "per_country": {},
                }
                for c, cdata in data.get("per_country", {}).items():
                    if isinstance(cdata, dict):
                        def _get_c(k: str) -> float:
                            sub = cdata.get(k, {})
                            if isinstance(sub, dict):
                                return float(sub.get(eur_key, sub.get("eur1", 0.0)))
                            return float(sub) if sub is not None else 0.0

                        metrics["per_country"][c] = {
                            "total_cost_m_yr": _get_c("total_cost_m_yr"),
                            "co2_mt": _get_c("co2_mt"),
                            "ens_mwh": _get_c("ens_mwh"),
                            "failure_hours": _get_c("failure_hours"),
                        }

            if metrics and metrics.get("per_country"):
                history.append({
                    "filepath": fpath,
                    "filename": os.path.basename(fpath),
                    "timestamp": dt_str,
                    "metrics": metrics,
                })
        except Exception as exc:
            logging.warning(f"Could not load simulation history file {fpath}: {exc}")

    # Sort chronologically by timestamp
    history.sort(key=lambda item: item["timestamp"])
    for idx, item in enumerate(history, start=1):
        item["run_index"] = idx

    return history


def compute_simulation_evolutions(history: List[dict]) -> dict:
    """
    Compute evolution progression across historical simulation runs.
    """
    if not history:
        return {"has_history": False, "history_len": 0}

    runs_data = []
    for h in history:
        m = h["metrics"]
        runs_data.append({
            "run_index": h["run_index"],
            "filename": h["filename"],
            "timestamp": h["timestamp"],
            "total_cost_m_yr": float(m.get("total_cost_m_yr", 0.0)),
            "total_operational_cost_m_yr": float(m.get("total_operational_cost_m_yr", 0.0)),
            "total_annualized_capex_m_yr": float(m.get("total_annualized_capex_m_yr", 0.0)),
            "total_co2_emissions_mt": float(m.get("total_co2_emissions_mt", 0.0)),
            "total_ens_mwh": float(m.get("total_ens_mwh", 0.0)),
            "max_failure_hours": float(m.get("max_failure_hours", 0.0)),
        })

    # Net global evolution from first to last run
    first_run = runs_data[0]
    last_run = runs_data[-1]
    
    def _diff_stat(key: str) -> dict:
        v1 = first_run[key]
        v2 = last_run[key]
        delta = v2 - v1
        pct = (delta / v1 * 100.0) if abs(v1) > 1e-6 else (0.0 if abs(v2) < 1e-6 else None)
        return {"first": v1, "last": v2, "delta": delta, "pct_change": pct}

    global_net_evolution = {
        "total_cost_m_yr": _diff_stat("total_cost_m_yr"),
        "total_operational_cost_m_yr": _diff_stat("total_operational_cost_m_yr"),
        "total_annualized_capex_m_yr": _diff_stat("total_annualized_capex_m_yr"),
        "total_co2_emissions_mt": _diff_stat("total_co2_emissions_mt"),
        "total_ens_mwh": _diff_stat("total_ens_mwh"),
        "max_failure_hours": _diff_stat("max_failure_hours"),
    }

    # Per-country evolution across all runs
    all_countries = sorted(list(set().union(*(h["metrics"].get("per_country", {}).keys() for h in history))))
    country_evolutions = {}

    for c in all_countries:
        c_runs_cost = []
        c_runs_co2 = []
        c_runs_ens = []
        c_runs_fail = []

        for h in history:
            cm = h["metrics"].get("per_country", {}).get(c, {})
            cost_val = float(cm.get("total_cost_m_yr", 0.0))
            raw_co2 = float(cm.get("co2_mt", 0.0))
            co2_val = (raw_co2 / 1000.0) if abs(raw_co2) > 500.0 else raw_co2
            ens_val = float(cm.get("ens_mwh", 0.0))
            fail_val = float(cm.get("failure_hours", 0.0))

            c_runs_cost.append(cost_val)
            c_runs_co2.append(co2_val)
            c_runs_ens.append(ens_val)
            c_runs_fail.append(fail_val)

        cost_delta = c_runs_cost[-1] - c_runs_cost[0]
        cost_pct = (cost_delta / c_runs_cost[0] * 100.0) if abs(c_runs_cost[0]) > 1e-6 else 0.0

        co2_delta = c_runs_co2[-1] - c_runs_co2[0]
        co2_pct = (co2_delta / c_runs_co2[0] * 100.0) if abs(c_runs_co2[0]) > 1e-6 else 0.0

        ens_delta = c_runs_ens[-1] - c_runs_ens[0]
        fail_delta = c_runs_fail[-1] - c_runs_fail[0]

        country_evolutions[c] = {
            "costs": c_runs_cost,
            "cost_delta": cost_delta,
            "cost_pct": cost_pct,
            "co2": c_runs_co2,
            "co2_delta": co2_delta,
            "co2_pct": co2_pct,
            "ens": c_runs_ens,
            "ens_delta": ens_delta,
            "failure": c_runs_fail,
            "failure_delta": fail_delta,
        }

    return {
        "has_history": len(history) >= 2,
        "history_len": len(history),
        "runs": runs_data,
        "global_net_evolution": global_net_evolution,
        "country_evolutions": country_evolutions,
    }


def format_simulation_evolutions_table(evolution_data: dict, target_europe: str = "Europe 1") -> str:
    """
    Format a complete simulation evolution dashboard into an aligned ASCII table.
    """
    if not evolution_data.get("has_history"):
        return f"\n[i] Only 1 simulation run found for {target_europe}. History tracking requires at least 2 runs.\n"

    runs = evolution_data["runs"]
    num_runs = len(runs)
    width = 133
    sep = "=" * width
    thin_sep = "-" * width

    lines = []
    title = f"SIMULATION EVOLUTION HISTORY: {target_europe.upper()} ({num_runs} RUNS RECORDED)"
    lines.append("")
    lines.append(sep)
    lines.append(f"{title:^{width}}")
    lines.append(sep)

    # 1. Global System Evolution
    lines.append(f"\n[1] GLOBAL SYSTEM EVOLUTION ACROSS SIMULATIONS ({target_europe.upper()}):")
    lines.append(thin_sep)
    g_hdr = (
        f"{'RUN':<5} | {'TIMESTAMP':<19} | {'TOTAL COST (M€/yr)':>18} | {'OPEX (M€/yr)':>16} | "
        f"{'CAPEX (M€/yr)':>16} | {'CO2 (Mt)':>12} | {'ENS (MWh)':>14} | {'FAILURE (h)':>13}"
    )
    lines.append(g_hdr)
    lines.append(thin_sep)

    for r in runs:
        idx_str = f"#{r['run_index']}"
        ts_str = r['timestamp']
        cost_str = f"{r['total_cost_m_yr']:>18,.2f}"
        opex_str = f"{r['total_operational_cost_m_yr']:>16,.2f}"
        capex_str = f"{r['total_annualized_capex_m_yr']:>16,.2f}"
        co2_str = f"{r['total_co2_emissions_mt']:>12,.2f}"
        ens_str = f"{r['total_ens_mwh']:>14,.1f}"
        fail_str = f"{r['max_failure_hours']:>13,.1f}"
        lines.append(
            f"{idx_str:<5} | {ts_str:<19} | {cost_str} | {opex_str} | {capex_str} | {co2_str} | {ens_str} | {fail_str}"
        )

    lines.append(thin_sep)
    gnet = evolution_data["global_net_evolution"]
    summary_label = f"TOTAL CHANGE (#{runs[0]['run_index']} -> #{runs[-1]['run_index']})"
    cost_d = f"{gnet['total_cost_m_yr']['delta']:>+18,.2f}"
    opex_d = f"{gnet['total_operational_cost_m_yr']['delta']:>+16,.2f}"
    capex_d = f"{gnet['total_annualized_capex_m_yr']['delta']:>+16,.2f}"
    co2_d = f"{gnet['total_co2_emissions_mt']['delta']:>+12,.2f}"
    ens_d = f"{gnet['total_ens_mwh']['delta']:>+14,.1f}"
    fail_d = f"{gnet['max_failure_hours']['delta']:>+13,.1f}"
    lines.append(
        f"{summary_label:<27} | {cost_d} | {opex_d} | {capex_d} | {co2_d} | {ens_d} | {fail_d}"
    )
    lines.append(thin_sep)

    # Helper for per-country tables: decide which runs to display as columns
    max_run_cols = min(num_runs, 4)
    displayed_run_indices = list(range(max_run_cols)) if num_runs <= 4 else [0, num_runs - 2, num_runs - 1]

    # 2. Per-Country Total Cost Evolution
    lines.append(f"\n[2] PER-COUNTRY TOTAL SYSTEM COST (M€/yr) EVOLUTION:")
    lines.append(thin_sep)

    run_col_headers = "".join(f" | {f'RUN #{runs[i][run_index_key]}':>12}" for i, run_index_key in [(i, 'run_index') for i in displayed_run_indices])
    cost_hdr = f"{'COUNTRY':<18}{run_col_headers} | {'NET CHANGE (Δ)':>15} | {'CHANGE (%)':>12}"
    lines.append(cost_hdr)
    lines.append(thin_sep)

    cev = evolution_data["country_evolutions"]
    for c in sorted(cev.keys()):
        cdata = cev[c]
        run_vals_str = "".join(f" | {cdata['costs'][i]:>12,.0f}" for i in displayed_run_indices)
        d_str = f"{cdata['cost_delta']:>+15,.0f}"
        pct_sign = "+" if cdata['cost_pct'] > 0 else ""
        pct_str = f"{pct_sign}{cdata['cost_pct']:>11.1f}%"
        lines.append(f"{c:<18}{run_vals_str} | {d_str} | {pct_str}")

    lines.append(thin_sep)

    # 3. Per-Country CO2 Emissions Evolution
    lines.append(f"\n[3] PER-COUNTRY CO2 EMISSIONS (Mt) EVOLUTION:")
    lines.append(thin_sep)
    co2_hdr = f"{'COUNTRY':<18}{run_col_headers} | {'NET CHANGE (Δ)':>15} | {'CHANGE (%)':>12}"
    lines.append(co2_hdr)
    lines.append(thin_sep)

    for c in sorted(cev.keys()):
        cdata = cev[c]
        run_vals_str = "".join(f" | {cdata['co2'][i]:>12.1f}" for i in displayed_run_indices)
        d_str = f"{cdata['co2_delta']:>+15.1f}"
        pct_sign = "+" if cdata['co2_pct'] > 0 else ""
        pct_str = f"{pct_sign}{cdata['co2_pct']:>11.1f}%"
        lines.append(f"{c:<18}{run_vals_str} | {d_str} | {pct_str}")

    lines.append(thin_sep)

    # 4. Per-Country Security of Supply Evolution
    lines.append(f"\n[4] PER-COUNTRY SECURITY OF SUPPLY (ENS & LOSS OF LOAD) EVOLUTION:")
    lines.append(thin_sep)
    idx_first = displayed_run_indices[0]
    idx_last = displayed_run_indices[-1]
    lbl_first = f"#{runs[idx_first]['run_index']}"
    lbl_last = f"#{runs[idx_last]['run_index']}"
    sec_hdr = (
        f"{'COUNTRY':<18} | {f'ENS {lbl_first} (MWh)':>14} | {f'ENS {lbl_last} (MWh)':>14} | {'Δ ENS (MWh)':>13} | "
        f"{f'FAIL {lbl_first} (h)':>13} | {f'FAIL {lbl_last} (h)':>13} | {'Δ FAIL (h)':>12}"
    )
    lines.append(sec_hdr)
    lines.append(thin_sep)

    for c in sorted(cev.keys()):
        cdata = cev[c]
        ens_1 = f"{cdata['ens'][idx_first]:>14,.0f}"
        ens_n = f"{cdata['ens'][idx_last]:>14,.0f}"
        ens_d = f"{cdata['ens_delta']:>+13,.0f}"

        fail_1 = f"{cdata['failure'][idx_first]:>13,.1f}"
        fail_n = f"{cdata['failure'][idx_last]:>13,.1f}"
        fail_d = f"{cdata['failure_delta']:>+12,.1f}"

        lines.append(f"{c:<18} | {ens_1} | {ens_n} | {ens_d} | {fail_1} | {fail_n} | {fail_d}")

    lines.append(sep)
    return "\n".join(lines) + "\n"


def display_simulation_evolutions(report_text: str) -> None:
    """Print simulation evolution report to console."""
    print(report_text)


def save_simulation_evolutions(
    evolution_data: dict,
    report_text: str,
    output_dir: str = "output/runner",
    target_europe: str = "europe1",
) -> Tuple[str, str]:
    """
    Save simulation evolution data and formatted text report to disk.
    """
    os.makedirs(output_dir, exist_ok=True)
    txt_path = os.path.join(output_dir, f"history_evolutions_{target_europe}.txt")
    json_path = os.path.join(output_dir, f"history_evolutions_{target_europe}.json")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(evolution_data, f, indent=2, ensure_ascii=False)

    return txt_path, json_path
