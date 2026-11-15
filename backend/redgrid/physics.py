"""Physics of walking (RedGrid System Specification, RedGrid Class Specification "Physics of a square").

Sources (check against the originals before quoting; see docs/ALGORITHMS.md):
  * Minetti A.E. et al. (2002) Energy cost of walking and running at extreme uphill and downhill slopes.
    J. Appl. Physiol. 93:1039-1046.  C(i) in J kg^-1 m^-1, gradient i in [-0.45, +0.45].
  * Tobler W. (1993) Three presentations on geographical analysis and modeling, NCGIA TR 93-1.
    Walking speed v = 6 exp(-3.5 |i + 0.05|) km/h; used here only RELATIVE to flat ground.
  * Pandolf K.B. et al. (1977) J. Appl. Physiol. 43:577-581, terrain coefficients from Soule R.G. and
    Goldman R.F. (1972) J. Appl. Physiol. 32:706-708 (planning constants terrain_factor_*).
  * Oxygen: 20.1 kJ per litre O2 (indirect calorimetry, mixed diet), 1.429 g per litre (O2 at STP).

All curves are Earth measurements on unsuited walkers. They supply only the RELATIVE change with slope and
surface. The absolute level is the planning constants metabolic_rate_w (Apollo 14 EVA average on the Moon)
and walk_speed_flat_kmh (prototype value); no Mars-gravity correction is applied (open item S3).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

I_MAX = 0.45  # validity range of the Minetti polynomial


def minetti_cost(i):
    """Metabolic cost of walking, J kg^-1 m^-1, at gradient i (rise/run, positive uphill)."""
    i = np.clip(i, -I_MAX, I_MAX)
    return ((((280.5 * i - 58.7) * i - 76.8) * i + 51.9) * i + 19.6) * i + 2.5


C0 = float(minetti_cost(0.0))  # 2.5 J kg^-1 m^-1


def tobler_relative_speed(i):
    """Walking speed relative to flat ground (Tobler 1993): exp(-3.5(|i+0.05| - 0.05))."""
    i = np.clip(i, -I_MAX, I_MAX)
    return np.exp(-3.5 * (np.abs(i + 0.05) - 0.05))


def energy_ratio_directed(i):
    return minetti_cost(i) / C0


def energy_ratio_symmetric(i_abs):
    """Mean of walking up and down a slope: direction-free, used on the routing grid."""
    return (minetti_cost(i_abs) + minetti_cost(-i_abs)) / (2.0 * C0)


def pace_ratio_symmetric(i_abs):
    """Mean of 1/v up and down, relative to flat (seconds per metre ratio)."""
    return 0.5 * (1.0 / tobler_relative_speed(i_abs) + 1.0 / tobler_relative_speed(-i_abs))


@dataclass(frozen=True)
class WalkingModel:
    metabolic_rate_w: float        # W, flat regolith
    walk_speed_flat_ms: float      # m/s
    suit_power_w: float            # W
    oxygen_energy_j_per_l: float   # J/L
    oxygen_density_g_per_l: float  # g/L

    @property
    def energy_per_m_flat(self) -> float:          # J/m on flat regolith
        return self.metabolic_rate_w / self.walk_speed_flat_ms

    @property
    def oxygen_per_m_flat(self) -> float:          # kg/m
        return self.energy_per_m_flat / self.oxygen_energy_j_per_l * self.oxygen_density_g_per_l / 1000.0

    @property
    def battery_per_m_flat(self) -> float:         # Wh/m
        return self.suit_power_w / self.walk_speed_flat_ms / 3600.0

    # --- grid (direction-free), per metre of ground ---
    def grid_rates(self, slope_deg: np.ndarray, terrain_factor: np.ndarray):
        """Return (oxygen kg/m, battery Wh/m, seconds/m) per square, averaged over walking up and down."""
        i = np.tan(np.radians(slope_deg))
        o2 = self.oxygen_per_m_flat * terrain_factor * energy_ratio_symmetric(i)
        pace = pace_ratio_symmetric(i) / self.walk_speed_flat_ms
        bat = self.suit_power_w * pace / 3600.0
        return o2, bat, pace

    # --- one step in its real direction ---
    def step(self, length_m: float, rise_m: float, terrain_factor: float):
        """Oxygen (kg), battery (Wh), time (s) and energy (J) for one step of ground length length_m."""
        i = rise_m / length_m if length_m > 0 else 0.0
        e = self.energy_per_m_flat * terrain_factor * float(energy_ratio_directed(i)) * length_m
        t = length_m / (self.walk_speed_flat_ms * float(tobler_relative_speed(i)))
        o2 = e / self.oxygen_energy_j_per_l * self.oxygen_density_g_per_l / 1000.0
        bat = self.suit_power_w * t / 3600.0
        return o2, bat, t, e
