import logging
import os
from datetime import datetime
from typing import Dict, Tuple, Optional, Union, List
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy import sparse

from src.utils.basic_utils import format_with_spaces

TRIGRAM_TO_ZONE = {
    "fra": "france",
    "ibe": "iberian-peninsula",
    "sca": "scandinavia",
    "ger": "germany",
    "deu": "germany",
    "ita": "italy",
    "ben": "benelux",
    "pol": "poland",
}


def get_zone_name_for_unit(unit_name: str, network=None) -> str:
    """
    Determine the ERAA zone name for a hydro storage unit.
    """
    if network is not None and hasattr(network, "storage_units") and unit_name in network.storage_units.index:
        bus = str(network.storage_units.loc[unit_name, "bus"])
        if bus in TRIGRAM_TO_ZONE:
            return TRIGRAM_TO_ZONE[bus]
        if bus.lower() in TRIGRAM_TO_ZONE.values():
            return bus.lower()

    # Fallback from unit name prefix (e.g. 'fra_hydro_reservoir' -> 'fra' -> 'france')
    prefix = unit_name.split("_")[0].lower()
    if prefix in TRIGRAM_TO_ZONE:
        return TRIGRAM_TO_ZONE[prefix]
    return prefix


def build_preprocessed_hydro_bounds_df(network,
                                       soc_min_processed_pu: Dict[str, np.ndarray],
                                       soc_max_processed_pu: Dict[str, np.ndarray],
                                       target_indices_per_unit: Optional[Dict[str, np.ndarray]] = None,
                                       decimal_digits: int = 3) -> pd.DataFrame:
    """
    Build a pandas DataFrame containing the preprocessed weekly min/max bounds
    for hydro reservoirs in the simulated horizon, matching the ERAA input format:
    zone;week;min_value;max_value

    :param network: PyPSA Network object with snapshots
    :param soc_min_processed_pu: Dict of {unit_name: relaxed_soc_min_pu_array}
    :param soc_max_processed_pu: Dict of {unit_name: relaxed_soc_max_pu_array}
    :param target_indices_per_unit: Optional Dict of {unit_name: target_snapshot_indices}
    :param decimal_digits: Decimal precision for rounding
    :return: DataFrame with columns ['zone', 'week', 'min_value', 'max_value']
    """
    rows = []
    snapshots = network.snapshots
    if len(snapshots) == 0:
        return pd.DataFrame(columns=["zone", "week", "min_value", "max_value"])

    first_snap = pd.Timestamp(snapshots[0])
    # In this environment, simulation weeks are defined on fictive year 1900 calendar
    try:
        start_date_1900 = datetime(1900, first_snap.month, first_snap.day)
        base_week = int(start_date_1900.isocalendar().week)
    except ValueError:
        base_week = 1

    for unit_name, min_arr in soc_min_processed_pu.items():
        if unit_name not in soc_max_processed_pu:
            continue
        max_arr = soc_max_processed_pu[unit_name]
        zone = get_zone_name_for_unit(unit_name, network=network)

        # Determine target snapshots corresponding to weekly bound targets
        if target_indices_per_unit is not None and unit_name in target_indices_per_unit:
            target_indices = target_indices_per_unit[unit_name]
        else:
            # Weekly steps occur every 168 hours starting from t=0
            weekly_steps = np.arange(0, len(snapshots), 168)
            # Plus any snapshot where values deviate from unconstrained corridor [0, 1]
            non_trivial = np.where((min_arr > 1e-4) | (max_arr < 1.0 - 1e-4))[0]
            target_indices = np.union1d(weekly_steps, non_trivial)

        for t_idx in target_indices:
            if t_idx >= len(snapshots):
                continue
            week_offset = int(t_idx // 168)
            week_idx = ((base_week - 1 + week_offset) % 52) + 1
            min_val = round(float(min_arr[t_idx]), decimal_digits)
            max_val = round(float(max_arr[t_idx]), decimal_digits)
            rows.append({
                "zone": zone,
                "week": week_idx,
                "min_value": min_val,
                "max_value": max_val
            })

    if len(rows) == 0:
        return pd.DataFrame(columns=["zone", "week", "min_value", "max_value"])

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["zone", "week"]).sort_values(by=["zone", "week"]).reset_index(drop=True)
    return df


def export_preprocessed_hydro_bounds_to_csv(network,
                                            soc_min_processed_pu: Dict[str, np.ndarray],
                                            soc_max_processed_pu: Dict[str, np.ndarray],
                                            output_filepath: str,
                                            target_indices_per_unit: Optional[Dict[str, np.ndarray]] = None,
                                            decimal_digits: int = 3) -> pd.DataFrame:
    """
    Export the preprocessed weekly hydro reservoir min/max bounds to a CSV file
    with the exact same format as the input file:
    zone;week;min_value;max_value

    :param network: PyPSA Network object with snapshots
    :param soc_min_processed_pu: Dict of {unit_name: relaxed_soc_min_pu_array}
    :param soc_max_processed_pu: Dict of {unit_name: relaxed_soc_max_pu_array}
    :param output_filepath: Destination CSV file path
    :param target_indices_per_unit: Optional Dict of {unit_name: target_snapshot_indices}
    :param decimal_digits: Decimal precision for values
    :return: Generated DataFrame
    """
    df = build_preprocessed_hydro_bounds_df(
        network=network,
        soc_min_processed_pu=soc_min_processed_pu,
        soc_max_processed_pu=soc_max_processed_pu,
        target_indices_per_unit=target_indices_per_unit,
        decimal_digits=decimal_digits
    )

    parent_dir = os.path.dirname(os.path.abspath(output_filepath))
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    df.to_csv(output_filepath, sep=";", index=False, float_format=f"%.{decimal_digits}f")
    logging.info(f"[Hydro Preprocessor] Exported preprocessed hydro bounds to CSV ({len(df)} rows): {output_filepath}")
    return df


def relax_single_hydro_reservoir_bounds_lp(unit_name: str,
                                           soc_min_pu: np.ndarray,
                                           soc_max_pu: np.ndarray,
                                           energy_capa: float,
                                           p_nom: float,
                                           soc_init: float,
                                           inflow: np.ndarray,
                                           efficiency_dispatch: float = 1.0,
                                           min_bandwidth_pu: float = 0.05) \
        -> Tuple[np.ndarray, np.ndarray]:
    """
    Solve a micro-LP for a single hydro reservoir to minimally relax weekly/hourly Vmin/Vmax bounds
    ensuring mathematical and physical feasibility.

    :param unit_name: Name of the hydro reservoir unit
    :param soc_min_pu: Minimum state-of-charge trajectory in per unit [0, 1] (or raw ERAA scale)
    :param soc_max_pu: Maximum state-of-charge trajectory in per unit [0, 1] (or raw ERAA scale)
    :param energy_capa: Reservoir energy capacity in MWh
    :param p_nom: Generator turbining capacity in MW
    :param soc_init: Initial state-of-charge in MWh
    :param inflow: Inflow series in MWh per snapshot
    :param efficiency_dispatch: Generation efficiency
    :param min_bandwidth_pu: Minimum required corridor width (Vmax - Vmin) in per unit
    :return: (soc_min_relaxed_pu, soc_max_relaxed_pu)
    """
    n_ts = len(soc_min_pu)
    if energy_capa <= 0 or n_ts == 0:
        return np.zeros(n_ts), np.ones(n_ts)

    # 1. Detect and normalize out-of-scale bounds (e.g. Scandinavia in ERAA data where values reach up to ~4.79)
    soc_min_clean = np.array(soc_min_pu, dtype=float).copy()
    soc_max_clean = np.array(soc_max_pu, dtype=float).copy()

    max_bound_val = max(float(np.nanmax(soc_min_clean)), float(np.nanmax(soc_max_clean)))
    if max_bound_val > 1.05:
        scale_factor = 5.0 if max_bound_val <= 5.5 else float(np.ceil(max_bound_val))
        logging.info(f"[Hydro Preprocessor] Unit '{unit_name}': detected out-of-scale bounds "
                     f"(max={max_bound_val:.3f} > 1.0). Normalizing by scale factor {scale_factor:.1f}.")
        soc_min_clean /= scale_factor
        soc_max_clean /= scale_factor

    # 2. Project bounds to [0, energy_capa] in MWh
    v_min_mwh = np.clip(soc_min_clean * energy_capa, 0.0, energy_capa)
    v_max_mwh = np.clip(soc_max_clean * energy_capa, 0.0, energy_capa)

    # Ensure v_min <= v_max point-wise
    inverted_mask = v_min_mwh > v_max_mwh
    if np.any(inverted_mask):
        mid = (v_min_mwh[inverted_mask] + v_max_mwh[inverted_mask]) / 2.0
        v_min_mwh[inverted_mask] = mid
        v_max_mwh[inverted_mask] = mid

    # 3. Identify target snapshots where actual bounds are enforced
    # Non-target snapshots are those filled with default unconstraining values (0 and energy_capa)
    is_target = (v_min_mwh > 1e-4 * energy_capa) | (v_max_mwh < (1.0 - 1e-4) * energy_capa)
    target_indices = np.where(is_target)[0]
    m_targets = len(target_indices)

    if m_targets == 0:
        # No active extreme levels constraints
        return np.zeros(n_ts), np.ones(n_ts)

    # Ensure initial SoC is physically valid
    soc_init_clean = float(np.clip(soc_init, 0.0, energy_capa))
    eff = efficiency_dispatch if efficiency_dispatch > 0 else 1.0

    # 4. Formulate minimal relaxation LP:
    # Variables x:
    # S[t]      for t in 0..N-1   (size N)
    # p[t]      for t in 0..N-1   (size N)
    # spill[t]  for t in 0..N-1   (size N)
    # delta_min[k] for k in 0..M-1 (size M)
    # delta_max[k] for k in 0..M-1 (size M)
    n_vars = 3 * n_ts + 2 * m_targets

    # Objective: min sum(delta_min + delta_max) + 1e-5 * sum(spill)
    c = np.zeros(n_vars)
    # delta_min and delta_max costs: 1.0
    c[3 * n_ts: 3 * n_ts + m_targets] = 1.0
    c[3 * n_ts + m_targets: 3 * n_ts + 2 * m_targets] = 1.0
    # tiny penalty on spillage to avoid unnecessary dumping of water
    c[2 * n_ts: 3 * n_ts] = 1e-5

    inflow_clean = np.nan_to_num(inflow, nan=0.0)

    # Variable bounds
    bounds = []
    # S[t] in [0, energy_capa]
    for _ in range(n_ts):
        bounds.append((0.0, energy_capa))
    # p[t] in [0, p_nom]
    for _ in range(n_ts):
        bounds.append((0.0, max(0.0, p_nom)))
    # spill[t] in [0, inflow[t]] (natural inflow can be spilled if reservoir is full, but stored water cannot)
    for t in range(n_ts):
        bounds.append((0.0, max(0.0, float(inflow_clean[t]))))
    # delta_min[k] in [0, v_min[target_k]] (cannot lower below 0)
    for k in range(m_targets):
        t_k = target_indices[k]
        bounds.append((0.0, float(v_min_mwh[t_k])))
    # delta_max[k] in [0, energy_capa - v_max[target_k]] (cannot raise above capa)
    for k in range(m_targets):
        t_k = target_indices[k]
        bounds.append((0.0, float(energy_capa - v_max_mwh[t_k])))

    # Equality constraints: Hydraulic mass balance
    # t = 0: S_0 + (1/eff)*p_0 + spill_0 = soc_init + inflow_0
    # t > 0: S_t - S_{t-1} + (1/eff)*p_t + spill_t = inflow_t
    A_eq = sparse.lil_matrix((n_ts, n_vars))
    b_eq = np.zeros(n_ts)

    # t = 0
    A_eq[0, 0] = 1.0  # S_0
    A_eq[0, n_ts] = 1.0 / eff  # p_0
    A_eq[0, 2 * n_ts] = 1.0  # spill_0
    b_eq[0] = soc_init_clean + inflow_clean[0]

    # t > 0
    for t in range(1, n_ts):
        A_eq[t, t] = 1.0  # S_t
        A_eq[t, t - 1] = -1.0  # -S_{t-1}
        A_eq[t, n_ts + t] = 1.0 / eff  # p_t
        A_eq[t, 2 * n_ts + t] = 1.0  # spill_t
        b_eq[t] = inflow_clean[t]

    # Inequality constraints:
    # 1. -S_{t_k} - delta_min_k <= -v_min[t_k]
    # 2.  S_{t_k} - delta_max_k <=  v_max[t_k]
    A_ub = sparse.lil_matrix((2 * m_targets, n_vars))
    b_ub = np.zeros(2 * m_targets)

    for k in range(m_targets):
        t_k = target_indices[k]
        # Lower bound
        A_ub[k, t_k] = -1.0
        A_ub[k, 3 * n_ts + k] = -1.0
        b_ub[k] = -float(v_min_mwh[t_k])

        # Upper bound
        A_ub[m_targets + k, t_k] = 1.0
        A_ub[m_targets + k, 3 * n_ts + m_targets + k] = -1.0
        b_ub[m_targets + k] = float(v_max_mwh[t_k])

    # Convert matrices to CSR format for fast solving
    A_eq_csr = A_eq.tocsr()
    A_ub_csr = A_ub.tocsr()

    # 5. Solve LP with HiGHS
    res = linprog(
        c=c,
        A_ub=A_ub_csr,
        b_ub=b_ub,
        A_eq=A_eq_csr,
        b_eq=b_eq,
        bounds=bounds,
        method="highs"
    )

    if not res.success:
        logging.warning(
            f"[Hydro Preprocessor] Unit '{unit_name}': LP relaxation did not converge ({res.message}). "
            f"Using unconstrained bounds [0, 1] as fallback."
        )
        return np.zeros(n_ts), np.ones(n_ts)

    # 6. Extract optimal slacks and update bounds
    delta_min_opt = res.x[3 * n_ts: 3 * n_ts + m_targets]
    delta_max_opt = res.x[3 * n_ts + m_targets: 3 * n_ts + 2 * m_targets]

    total_slack_min = float(np.sum(delta_min_opt))
    total_slack_max = float(np.sum(delta_max_opt))

    if total_slack_min > 1.0 or total_slack_max > 1.0:
        n_decimals_log = 1
        relaxed_log_msgs = []
        for key, slack_tot in {"Vmin": total_slack_min, "Vmax": total_slack_max}.items():
            if slack_tot > 1.0:
                relaxed_log_msgs.append(
                    f"{key} by {format_with_spaces(number=slack_tot, decimals=n_decimals_log)} MWh")
        relaxed_msg = " and ".join(relaxed_log_msgs)
        logging.info(f"[Hydro Preprocessor] Unit '{unit_name}': relaxed {relaxed_msg} to guarantee feasibility.")

    v_min_relaxed = v_min_mwh.copy()
    v_max_relaxed = v_max_mwh.copy()

    v_min_relaxed[target_indices] = np.maximum(0.0, v_min_mwh[target_indices] - delta_min_opt)
    v_max_relaxed[target_indices] = np.minimum(energy_capa, v_max_mwh[target_indices] + delta_max_opt)

    # 7. Enforce minimum bandwidth so UC has room for optimal dispatch flexibility
    min_bandwidth_mwh = min_bandwidth_pu * energy_capa
    for k in range(m_targets):
        t_k = target_indices[k]
        width = v_max_relaxed[t_k] - v_min_relaxed[t_k]
        if width < min_bandwidth_mwh:
            deficit = min_bandwidth_mwh - width
            half_deficit = deficit / 2.0
            room_lower = v_min_relaxed[t_k]
            room_upper = energy_capa - v_max_relaxed[t_k]
            shift_lower = min(room_lower, half_deficit)
            shift_upper = min(room_upper, half_deficit)
            v_min_relaxed[t_k] = max(0.0, v_min_relaxed[t_k] - (deficit - shift_upper))
            v_max_relaxed[t_k] = min(energy_capa, v_max_relaxed[t_k] + (deficit - shift_lower))

    # Convert back to per unit
    soc_min_relaxed_pu = v_min_relaxed / energy_capa
    soc_max_relaxed_pu = v_max_relaxed / energy_capa

    return soc_min_relaxed_pu, soc_max_relaxed_pu


def preprocess_all_hydro_soc_bounds(network,
                                    soc_min_pu: Dict[str, Union[float, np.ndarray]],
                                    soc_max_pu: Dict[str, Union[float, np.ndarray]],
                                    energy_capa: Dict[str, float],
                                    n_ts: int,
                                    min_bandwidth_pu: float = 0.05,
                                    enable_relaxation: bool = True,
                                    export_csv_path: Optional[str] = None) \
        -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """
    Preprocess and relax all hydro reservoir extreme level bounds before injecting into PyPSA / Linopy.

    :param network: PyPSA Network object
    :param soc_min_pu: Dict of {unit_name: bound_pu}
    :param soc_max_pu: Dict of {unit_name: bound_pu}
    :param energy_capa: Dict of {unit_name: energy_capacity_mwh}
    :param n_ts: Number of snapshots
    :param min_bandwidth_pu: Minimum bandwidth in per unit
    :param enable_relaxation: If False, only format arrays without LP relaxation
    :param export_csv_path: Optional CSV filepath to automatically export preprocessed bounds
    :return: (soc_min_processed_pu, soc_max_processed_pu)
    """
    processed_min = {}
    processed_max = {}

    for unit_name in soc_min_pu:
        capa = energy_capa.get(unit_name, 0.0)
        raw_min = soc_min_pu[unit_name]
        raw_max = soc_max_pu[unit_name]

        # Vectorize if scalar
        vec_min = raw_min if isinstance(raw_min, np.ndarray) else np.full(n_ts, float(raw_min))
        vec_max = raw_max if isinstance(raw_max, np.ndarray) else np.full(n_ts, float(raw_max))

        if not enable_relaxation or capa <= 0:
            processed_min[unit_name] = vec_min
            processed_max[unit_name] = vec_max
            continue

        # Extract unit parameters from network
        if unit_name in network.storage_units.index:
            p_nom = float(network.storage_units.loc[unit_name, "p_nom"])
            soc_init = float(network.storage_units.loc[unit_name, "state_of_charge_initial"])
            eff_dispatch = float(network.storage_units.loc[unit_name, "efficiency_dispatch"]) \
                if "efficiency_dispatch" in network.storage_units.columns else 1.0

            # Extract inflow time series
            if hasattr(network, "storage_units_t") and "inflow" in network.storage_units_t \
                    and unit_name in network.storage_units_t.inflow.columns:
                inflow_series = network.storage_units_t.inflow[unit_name].values
            elif "inflow" in network.storage_units.columns:
                inflow_series = np.full(n_ts, float(network.storage_units.loc[unit_name, "inflow"]))
            else:
                inflow_series = np.zeros(n_ts)
        else:
            p_nom = capa / 1000.0
            soc_init = 0.8 * capa
            eff_dispatch = 1.0
            inflow_series = np.zeros(n_ts)

        rel_min_pu, rel_max_pu = relax_single_hydro_reservoir_bounds_lp(
            unit_name=unit_name,
            soc_min_pu=vec_min,
            soc_max_pu=vec_max,
            energy_capa=capa,
            p_nom=p_nom,
            soc_init=soc_init,
            inflow=inflow_series,
            efficiency_dispatch=eff_dispatch,
            min_bandwidth_pu=min_bandwidth_pu
        )

        processed_min[unit_name] = rel_min_pu
        processed_max[unit_name] = rel_max_pu

    if export_csv_path is not None:
        export_preprocessed_hydro_bounds_to_csv(
            network=network,
            soc_min_processed_pu=processed_min,
            soc_max_processed_pu=processed_max,
            output_filepath=export_csv_path
        )

    return processed_min, processed_max
