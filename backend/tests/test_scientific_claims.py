"""Behavioural regression tests for the scientific constants the manuscript names.

`test_contracts.py` asserts that the paper-facing constants exist with the
expected values.  These tests assert that the constants are actually *used*:
each named structural alert fires on a reference substructure, covalent mode
suppresses exactly the declared warheads, the blood-brain-barrier triage flag
applies its three thresholds with the documented inclusivity and reports them,
and every interaction distance cutoff is enforced at its stated boundary under
multi-label classification.

They deliberately avoid the network, Vina, and Open Babel so that a manuscript
claim cannot drift without a fast, deterministic failure.
"""

from pathlib import Path

import pytest
from rdkit import Chem

from rdkit.Chem import AllChem

from backend.models import schemas
from backend.routers import admet as admet_router
from backend.routers import filters as filters_router
from backend.routers import interactions as interactions_router
from backend.routers import pharmacophore as pharmacophore_router
from backend.routers.filters import _check_compound
from backend.routers.interactions import _detect_contacts


# ---------------------------------------------------------------------------
# Blood-brain barrier triage flag (Table 1: MW < 450, TPSA < 90,
# 0.5 <= LogP <= 4.5).  Relabelled from "BBB permeable": it is a three-threshold
# descriptor filter, never a trained permeability model.
# ---------------------------------------------------------------------------

# (molecular weight, TPSA, LogP, expected verdict, what the case pins down)
BBB_BOUNDARY_CASES = [
    (449.9, 89.9, 2.0, True, "inside every threshold"),
    (449.9, 89.9, 0.5, True, "lower LogP bound is inclusive"),
    (449.9, 89.9, 4.5, True, "upper LogP bound is inclusive"),
    (449.9, 89.9, 0.499, False, "just below the lower LogP bound"),
    (449.9, 89.9, 4.501, False, "just above the upper LogP bound"),
    (449.9, 0.0, 2.0, True, "zero TPSA is permitted"),
    (450.0, 89.9, 2.0, False, "molecular-weight bound is exclusive"),
    (449.9, 90.0, 2.0, False, "TPSA bound is exclusive"),
    (449.99, 89.99, 2.0, True, "immediately inside both exclusive bounds"),
]


@pytest.mark.parametrize("mw,tpsa,logp,expected,rationale", BBB_BOUNDARY_CASES)
def test_bbb_triage_applies_its_published_thresholds(monkeypatch, mw, tpsa, logp, expected, rationale):
    """Table 1 publishes exact bounds; strictness and inclusivity must not drift."""
    monkeypatch.setattr(admet_router.Descriptors, "MolWt", lambda _mol: mw)
    monkeypatch.setattr(admet_router.Descriptors, "TPSA", lambda _mol: tpsa)
    monkeypatch.setattr(admet_router.Descriptors, "MolLogP", lambda _mol: logp)

    assert admet_router._bbb_triage_flag(object()) is expected, rationale
    # The deprecated name must keep returning the same verdict.
    assert admet_router._bbb_permeable(object()) is expected, rationale


# SMILES, expected verdict, the threshold that decides the case
BBB_REFERENCE_MOLECULES = [
    ("CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21", True, "diazepam satisfies all three bounds"),
    ("Cc1ccccc1", True, "toluene satisfies all three bounds"),
    ("CN1CCC23c4c5ccc(O)c4OC2C(O)C=CC3C1C5", True, "morphine satisfies all three bounds"),
    ("CC(C)NCC(O)COc1ccc(CC(N)=O)cc1", False, "atenolol falls below the lower LogP bound"),
    ("OCC1OC(CO)(OC2OC(CO)C(O)C(O)C2O)C(O)C1O", False, "sucrose exceeds the TPSA bound"),
]


@pytest.mark.parametrize("smiles,expected,rationale", BBB_REFERENCE_MOLECULES)
def test_bbb_triage_classifies_reference_molecules(smiles, expected, rationale):
    """The thresholds must survive real RDKit descriptors, not only mocked ones."""
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None

    assert admet_router._bbb_triage_flag(mol) is expected, rationale


def test_bbb_is_a_triage_filter_with_a_known_false_negative():
    """Caffeine crosses the blood-brain barrier but fails the LogP floor.

    The field is labelled a triage flag precisely because of cases like this.
    The test pins the boundary so the claim cannot be quietly upgraded to a
    validated permeability prediction.
    """
    caffeine = Chem.MolFromSmiles("Cn1cnc2c1c(=O)n(C)c(=O)n2C")

    triage = admet_router._bbb_triage(caffeine)

    assert triage.flag is False
    # Only the LogP floor rejects it — the reason must be visible, not implicit.
    failed = [c.name for c in triage.criteria if not c.passed]
    assert failed == ["LogP"]


def test_bbb_triage_surfaces_every_threshold_that_produced_the_verdict():
    """A user must be able to see all three rules, their values and their bounds."""
    diazepam = Chem.MolFromSmiles("CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21")

    triage = admet_router._bbb_triage(diazepam)

    assert triage.flag is True
    assert [c.name for c in triage.criteria] == ["MW", "TPSA", "LogP"]
    assert all(c.passed for c in triage.criteria)
    assert all(c.value is not None for c in triage.criteria)
    assert [c.threshold for c in triage.criteria] == ["450", "90", "[0.5, 4.5]"]
    # The published thresholds and the strings shown to the user are one source.
    assert admet_router.BBB_MW_MAX == 450.0
    assert admet_router.BBB_TPSA_MAX == 90.0
    assert admet_router.BBB_LOGP_MIN == 0.5
    assert admet_router.BBB_LOGP_MAX == 4.5


def test_bbb_caveat_travels_with_every_triage_result():
    """The field is not a trained model, and the response has to say so."""
    triage = admet_router._bbb_triage(Chem.MolFromSmiles("Cc1ccccc1"))

    assert triage.caveat == schemas.BBB_TRIAGE_CAVEAT
    assert "not a trained" in triage.caveat
    assert "caffeine" in triage.caveat


def test_admet_profile_reports_the_triage_flag_under_both_names():
    """`bbb_permeable` stays as a deprecated alias so existing clients keep working."""
    profile = admet_router._profile_mol(Chem.MolFromSmiles("Cc1ccccc1"), "toluene")

    assert profile.bbb_triage_flag is True
    assert profile.bbb_triage is not None
    assert profile.bbb_triage.flag is profile.bbb_triage_flag
    with pytest.warns(DeprecationWarning):
        assert profile.bbb_permeable is profile.bbb_triage_flag


# ---------------------------------------------------------------------------
# Structural alerts (16 named SMARTS patterns, 4 suppressible covalent warheads)
# ---------------------------------------------------------------------------

# Every named alert paired with a reference compound containing that group.
STRUCTURAL_ALERT_CONTROLS = {
    "Epoxide": "C1CO1",                                  # ethylene oxide
    "Aldehyde": "CC=O",                                  # acetaldehyde
    "Michael_Acceptor": "C=CC(=O)C",                     # methyl vinyl ketone
    "Vinyl_Sulfone": "C=CS(=O)(=O)c1ccccc1",             # phenyl vinyl sulfone
    "Acyl_Halide": "CC(=O)Cl",                           # acetyl chloride
    "Sulfonyl_Halide": "CS(=O)(=O)Cl",                   # methanesulfonyl chloride
    "Peroxide": "COOC",                                  # dimethyl peroxide
    "Azide": "CN=[N+]=[N-]",                             # methyl azide
    "Isocyanate": "CN=C=O",                              # methyl isocyanate
    "Acid_Anhydride": "CC(=O)OC(C)=O",                   # acetic anhydride
    "Nitro_Aromatic": "[O-][N+](=O)c1ccccc1",            # nitrobenzene
    "N_Oxide": "C[N+](C)(C)[O-]",                        # trimethylamine N-oxide
    "Azo_Compound": "c1ccccc1N=Nc1ccccc1",               # azobenzene
    "Thiocarbonyl": "NC(=S)N",                           # thiourea
    "Vinyl_Nitrile": "C=CC#N",                           # acrylonitrile
    "Maleimide": "O=C1C=CC(=O)N1",                       # maleimide
}

# Approved drugs that must stay clear of every named alert.
ALERT_FREE_REFERENCE_DRUGS = {
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "metformin": "CN(C)C(=N)NC(=N)N",
    "imatinib": "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1",
    "warfarin": "CC(=O)CC(c1ccccc1)c1c(O)c2ccccc2oc1=O",
    "glucose": "OCC1OC(O)C(O)C(O)C1O",
}


def test_structural_alert_inventory_is_sixteen_compilable_patterns():
    """Every published alert must be a SMARTS RDKit can actually compile."""
    assert len(filters_router._STRUCTURAL_ALERTS) == 16
    assert len(STRUCTURAL_ALERT_CONTROLS) == 16
    assert set(STRUCTURAL_ALERT_CONTROLS) == set(filters_router._STRUCTURAL_ALERTS)

    for name, smarts in filters_router._STRUCTURAL_ALERTS.items():
        assert Chem.MolFromSmarts(smarts) is not None, f"{name} is not a valid SMARTS"


@pytest.mark.parametrize("name,smiles", sorted(STRUCTURAL_ALERT_CONTROLS.items()))
def test_every_named_alert_fires_on_its_reference_substructure(name, smiles):
    """A published alert that matches nothing is an undetectable liability filter."""
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, f"{name} control SMILES did not parse"

    result = _check_compound(mol)

    assert name in result["alerts"], f"{name} did not fire on its own reference compound"
    assert result["alert_free"] is False


@pytest.mark.parametrize("drug,smiles", sorted(ALERT_FREE_REFERENCE_DRUGS.items()))
def test_named_alerts_do_not_fire_on_alert_free_reference_drugs(drug, smiles):
    """Over-broad SMARTS would reject marketed drugs during compound triage."""
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None

    result = _check_compound(mol)

    assert result["alerts"] == [], f"{drug} was flagged by {result['alerts']}"
    assert result["alert_free"] is True


def test_n_oxide_alert_separates_n_oxides_from_nitro_and_neutral_amines():
    """The N-oxide pattern must cover aliphatic and aromatic N-oxides only."""
    n_oxide_pattern = Chem.MolFromSmarts(filters_router._STRUCTURAL_ALERTS["N_Oxide"])

    for smiles in (
        "C[N+](C)(C)[O-]",              # trimethylamine N-oxide
        "[O-][n+]1ccccc1",              # pyridine N-oxide
        "C[N+]1([O-])CCOCC1",           # N-methylmorpholine N-oxide
        "NC(=O)c1ccc[n+]([O-])c1",      # nicotinamide N-oxide
    ):
        assert Chem.MolFromSmiles(smiles).HasSubstructMatch(n_oxide_pattern), smiles

    for smiles in (
        "[O-][N+](=O)c1ccccc1",         # nitrobenzene — Nitro_Aromatic, not N_Oxide
        "C[N+](=O)[O-]",                # nitromethane
        "CN(C)C",                       # trimethylamine
        "c1ccncc1",                     # pyridine
        "C[N+](C)(C)CC(=O)[O-]",        # betaine — quaternary N without an N-oxide
    ):
        assert not Chem.MolFromSmiles(smiles).HasSubstructMatch(n_oxide_pattern), smiles


# ---------------------------------------------------------------------------
# Covalent screening mode
# ---------------------------------------------------------------------------

def test_covalent_mode_suppresses_exactly_the_four_declared_warheads():
    """Covalent mode is an opt-in exception list, not a blanket alert bypass."""
    assert filters_router._COVALENT_WARHEAD_ALERTS == {
        "Michael_Acceptor",
        "Vinyl_Sulfone",
        "Vinyl_Nitrile",
        "Maleimide",
    }

    for name, smiles in STRUCTURAL_ALERT_CONTROLS.items():
        mol = Chem.MolFromSmiles(smiles)
        covalent = _check_compound(mol, covalent_mode=True)

        if name in filters_router._COVALENT_WARHEAD_ALERTS:
            assert name not in covalent["alerts"], f"{name} survived covalent mode"
        else:
            assert name in covalent["alerts"], f"{name} was wrongly suppressed by covalent mode"


def test_covalent_mode_leaves_non_warhead_alerts_on_the_same_molecule():
    """Suppression is per-alert: a warhead plus an epoxide keeps the epoxide."""
    # Glycidyl acrylate: an acrylate Michael acceptor and an epoxide in one molecule.
    mol = Chem.MolFromSmiles("C=CC(=O)OCC1CO1")
    assert mol is not None

    default = _check_compound(mol)
    covalent = _check_compound(mol, covalent_mode=True)

    assert {"Michael_Acceptor", "Epoxide"} <= set(default["alerts"])
    assert covalent["alerts"] == ["Epoxide"]
    assert covalent["alert_free"] is False


def test_covalent_mode_does_not_suppress_pains_matches():
    """PAINS screening is independent of the covalent-warhead exception list."""
    mol = Chem.MolFromSmiles("c1ccccc1N=Nc1ccccc1")  # azobenzene matches the PAINS azo filter

    default = _check_compound(mol)
    covalent = _check_compound(mol, covalent_mode=True)

    assert default["pains_matches"], "expected a PAINS match for the control compound"
    assert covalent["pains_matches"] == default["pains_matches"]
    assert covalent["pains_free"] is False


# ---------------------------------------------------------------------------
# Interaction distance cutoffs
# (H-bond 3.5 A, sulfur H-bond 3.9 A, hydrophobic 4.5 A, salt bridge 4.0 A)
# ---------------------------------------------------------------------------

def _protein_atom(name, resname, element, x, resseq=1, charge=0.0):
    return {
        "name": name, "resname": resname, "resseq": resseq,
        "x": x, "y": 0.0, "z": 0.0,
        "element": element, "ad_type": element, "charge": charge,
    }


def _ligand_atom(name, element, x, ad_type=None, charge=0.0):
    return {
        "name": name, "resname": "LIG", "resseq": 1,
        "x": x, "y": 0.0, "z": 0.0,
        "element": element, "ad_type": ad_type or element, "charge": charge,
    }


def _contact_types(protein, ligand):
    return {contact.type for contact in _detect_contacts(protein, ligand)}


@pytest.mark.parametrize("distance,expected", [(3.49, True), (3.5, True), (3.51, False)])
def test_nitrogen_oxygen_hydrogen_bond_cutoff_is_enforced_at_3_5_angstrom(distance, expected):
    """HBOND_DIST must gate classification, not merely exist as a constant."""
    protein = [_protein_atom("NH1", "ARG", "N", 0.0)]
    ligand = [_ligand_atom("O1", "O", distance, ad_type="OA")]

    assert ("H-bond" in _contact_types(protein, ligand)) is expected


@pytest.mark.parametrize("distance,expected", [(3.89, True), (3.9, True), (3.91, False)])
def test_sulfur_hydrogen_bond_cutoff_is_enforced_at_3_9_angstrom(distance, expected):
    """Sulfur contacts use the longer Zhou et al. cutoff."""
    protein = [_protein_atom("SG", "CYS", "S", 0.0)]
    ligand = [_ligand_atom("O1", "O", distance, ad_type="OA")]

    assert ("H-bond" in _contact_types(protein, ligand)) is expected


def test_the_longer_cutoff_applies_only_when_sulfur_participates():
    """At 3.7 A a sulfur pair is an H-bond while an identical N/O pair is not."""
    ligand = [_ligand_atom("O1", "O", 3.7, ad_type="OA")]

    assert "H-bond" in _contact_types([_protein_atom("SG", "CYS", "S", 0.0)], ligand)
    assert "H-bond" not in _contact_types([_protein_atom("NH1", "ARG", "N", 0.0)], ligand)


@pytest.mark.parametrize("distance,expected", [(4.49, True), (4.5, True), (4.51, False)])
def test_hydrophobic_cutoff_is_enforced_at_4_5_angstrom(distance, expected):
    """HYDROPHOBIC_DIST gates carbon-carbon van der Waals contacts."""
    protein = [_protein_atom("CB", "ALA", "C", 0.0)]
    ligand = [_ligand_atom("C1", "C", distance)]

    assert ("Hydrophobic" in _contact_types(protein, ligand)) is expected


@pytest.mark.parametrize("distance,expected", [(3.99, True), (4.0, True), (4.01, False)])
def test_salt_bridge_cutoff_is_enforced_at_4_0_angstrom(distance, expected):
    """SALT_BRIDGE_DIST gates the charge-complementary contact class."""
    protein = [_protein_atom("NH1", "ARG", "N", 0.0)]
    ligand = [_ligand_atom("O1", "O", distance, ad_type="OA", charge=-0.8)]

    assert ("Salt bridge" in _contact_types(protein, ligand)) is expected


def test_salt_bridge_requires_a_charged_residue_and_a_complementary_ligand_charge():
    """Element identity alone must not produce an ionic contact."""
    charged_ligand = [_ligand_atom("O1", "O", 3.8, ad_type="OA", charge=-0.8)]
    neutral_ligand = [_ligand_atom("O1", "O", 3.8, ad_type="OA", charge=-0.2)]

    assert "Salt bridge" in _contact_types([_protein_atom("NH1", "ARG", "N", 0.0)], charged_ligand)
    assert "Salt bridge" not in _contact_types([_protein_atom("NH1", "ARG", "N", 0.0)], neutral_ligand)
    # A backbone amide nitrogen is not a formally charged group.
    assert "Salt bridge" not in _contact_types([_protein_atom("N", "ALA", "N", 0.0)], charged_ligand)

    # The acidic branch: ASP/GLU carboxylate oxygen against a cationic ligand nitrogen.
    cationic_ligand = [_ligand_atom("N1", "N", 3.8, ad_type="N", charge=0.3)]
    assert "Salt bridge" in _contact_types([_protein_atom("OD1", "ASP", "O", 0.0)], cationic_ligand)

    weak_cation = [_ligand_atom("N1", "N", 3.8, ad_type="N", charge=0.2)]
    assert "Salt bridge" not in _contact_types([_protein_atom("OD1", "ASP", "O", 0.0)], weak_cation)


def test_one_atom_pair_carries_both_a_hydrogen_bond_and_a_salt_bridge_label():
    """A close ARG-carboxylate pair is counted in *both* categories.

    Classification is multi-label, so a charge-complementary contact inside the
    3.5 A hydrogen-bond distance no longer disappears from the salt-bridge
    count.  Salt-bridge totals are therefore an exhaustive enumeration, not a
    classification summary.
    """
    protein = [_protein_atom("NH1", "ARG", "N", 0.0)]
    ligand = [_ligand_atom("O1", "O", 3.0, ad_type="OA", charge=-0.8)]

    contacts = _detect_contacts(protein, ligand)

    assert [contact.type for contact in contacts] == ["H-bond", "Salt bridge"]
    # Both labels describe the same atom pair.
    assert {(c.residue, c.receptor_atom, c.ligand_atom) for c in contacts} == {
        ("ARG1", "NH1", "O1")
    }

    counts = interactions_router.summarize_contacts(contacts)
    assert counts["h_bonds"] == 1
    assert counts["salt_bridges"] == 1
    assert counts["dual_labeled_pairs"] == 1
    # Continuity: the pre-multi-label numbers are still reported alongside.
    assert counts["total"] == 2
    assert counts["total_single_label"] == 1
    assert counts["salt_bridges_single_label"] == 0


def test_interaction_cutoff_constants_match_the_manuscript():
    """Guards the published values themselves alongside the behaviour above."""
    assert interactions_router.HBOND_DIST == 3.5
    assert interactions_router.HBOND_DIST_S == 3.9
    assert interactions_router.HYDROPHOBIC_DIST == 4.5
    assert interactions_router.SALT_BRIDGE_DIST == 4.0


# ---------------------------------------------------------------------------
# Deterministic conformer embedding
# ---------------------------------------------------------------------------

def test_pharmacophore_embedding_uses_the_shared_deterministic_seed():
    """Pharmacophore conformers must share the seed used elsewhere in the app."""
    assert pharmacophore_router.EMBED_SEED == 42
    assert pharmacophore_router._embed_params().randomSeed == 42


def test_pharmacophore_embedding_is_reproducible_between_runs():
    """3D alignment scores are only citable if the conformer search is fixed.

    Embedding the same molecule three times through the router's parameters must
    give bit-identical coordinates; an unseeded ETKDGv3 run does not.
    """
    smiles = "CC(=O)Oc1ccccc1C(=O)O"

    def embed(params):
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        assert AllChem.EmbedMolecule(mol, params) == 0
        AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
        return tuple(round(v, 6) for pos in mol.GetConformer().GetPositions() for v in pos)

    seeded = {embed(pharmacophore_router._embed_params()) for _ in range(3)}
    assert len(seeded) == 1, "seeded embedding was not reproducible"


# ---------------------------------------------------------------------------
# Declared environment
# ---------------------------------------------------------------------------

def _requirement_lines(name):
    path = Path(__file__).resolve().parents[2] / "backend" / name
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def test_requirements_do_not_name_the_retired_rdkit_wheel():
    """`rdkit-pypi` stopped publishing after 2022.9.5.

    A >=2024 constraint on it cannot resolve, so the documented install command
    fails outright on a clean machine. The package to depend on is `rdkit`.
    """
    declared = _requirement_lines("requirements.txt")

    assert not any(line.startswith("rdkit-pypi") for line in declared)
    assert any(line.startswith("rdkit>=") or line.startswith("rdkit==") for line in declared)


def test_lockfile_pins_every_dependency_exactly():
    """The reproducible environment must be stated as exact versions, not floors."""
    locked = _requirement_lines("requirements.lock.txt")

    assert locked, "requirements.lock.txt is empty"
    for line in locked:
        assert "==" in line, f"{line!r} is not an exact pin"
        assert ">=" not in line and "<" not in line, f"{line!r} is not an exact pin"


def test_lockfile_matches_the_runtime_for_the_scientific_stack():
    """A pin that has drifted from the installed runtime is worse than no pin."""
    import importlib.metadata as metadata

    pinned = {}
    for line in _requirement_lines("requirements.lock.txt"):
        name, version = line.split("==", 1)
        pinned[name.split("[", 1)[0]] = version

    for package in ("rdkit", "numpy", "meeko", "scipy", "fastapi", "pydantic"):
        assert pinned[package] == metadata.version(package), (
            f"{package} is pinned to {pinned[package]} but {metadata.version(package)} is installed"
        )
