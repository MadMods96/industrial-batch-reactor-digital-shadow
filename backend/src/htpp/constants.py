"""Physical constants taken from cited literature. Not identified from plant data."""

# Yang, Tanguy and Roy, Chem. Eng. Sci. 50 (1995) 1909-1922.
# Rubber specific heat used by later tyre-pyrolysis models (Rudniak, 2017,
# citing Yang et al.) as 1.9 kJ/(kg·K) at the reference temperature.
# This is an assumed literature value, not fitted.
CP_CHARGE_J_PER_KG_K = 1900.0
CP_CHARGE_CITATION = (
    "Yang J., Tanguy P.A., Roy C., Chem. Eng. Sci. 50 (1995) 1909-1922, "
    "as tabulated for tyre rubber by Rudniak (Chem. Process Eng. 2017)."
)

# Activation-energy envelope compiled by Danon et al., Materials Science 19(4)
# (2013): Lopez et al. 50.6-246 kJ/mol, Aylon et al. 70-256 kJ/mol.
EA_MIN_J_PER_MOL = 50_600.0
EA_MAX_J_PER_MOL = 256_000.0
EA_CITATION = (
    "Danon B. et al., Materials Science 19(4) (2013), compiling "
    "Lopez et al. and Aylon et al. tyre-pyrolysis activation energies."
)

R_J_PER_MOL_K = 8.314
FAULT_MATCH_WINDOW_MIN = 120
SAMPLE_RESOLUTION_MIN = 4
