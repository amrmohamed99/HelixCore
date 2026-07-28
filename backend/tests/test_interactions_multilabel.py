"""Multi-label interaction classification (publication plan item 1.4).

Before this change each receptor-atom/ligand-atom pair carried exactly one
label, resolved by the precedence H-bond > hydrophobic > salt bridge.  A
charge-complementary pair that also sat inside the hydrogen-bond distance was
therefore counted as a hydrogen bond and vanished from the salt-bridge count,
which is why the manuscript had to describe salt-bridge counts as "a
classification summary rather than an exhaustive enumeration".

These tests pin the corrected behaviour: both labels are assigned to the same
pair, both counts are reported separately, and the old single-label numbers
remain available for continuity with previously published figures.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers.interactions import (
    HBOND_LABEL,
    HYDROPHOBIC_LABEL,
    LEGACY_LABEL_PRECEDENCE,
    SALT_BRIDGE_LABEL,
    _detect_contacts,
    _parse_pdbqt_atoms,
    summarize_contacts,
)


def _protein_atom(name, resname, element, x, y=0.0, z=0.0, resseq=1, chain="A", charge=0.0):
    return {
        "name": name, "resname": resname, "chain": chain, "resseq": resseq,
        "x": x, "y": y, "z": z,
        "element": element, "ad_type": element, "charge": charge,
    }


def _ligand_atom(name, element, x, y=0.0, z=0.0, ad_type=None, charge=0.0):
    return {
        "name": name, "resname": "LIG", "chain": "L", "resseq": 1,
        "x": x, "y": y, "z": z,
        "element": element, "ad_type": ad_type or element, "charge": charge,
    }


def _labels(contacts):
    return [c.type for c in contacts]


# ---------------------------------------------------------------------------
# The case the limitation sentence was written about
# ---------------------------------------------------------------------------

def test_arginine_carboxylate_inside_hbond_distance_is_counted_in_both_classes():
    """ARG guanidinium against an anionic ligand oxygen at 3.0 A.

    This is the exact configuration the old classifier dropped from the
    salt-bridge count.
    """
    protein = [_protein_atom("NH1", "ARG", "N", 0.0, resseq=7)]
    ligand = [_ligand_atom("O1", "O", 3.0, ad_type="OA", charge=-0.8)]

    contacts = _detect_contacts(protein, ligand)

    assert _labels(contacts) == [HBOND_LABEL, SALT_BRIDGE_LABEL]
    # Both labels describe one and the same atom pair.
    assert {(c.residue, c.receptor_atom, c.ligand_atom, c.distance) for c in contacts} == {
        ("ARG7", "NH1", "O1", 3.0)
    }

    counts = summarize_contacts(contacts)
    assert counts["h_bonds"] == 1
    assert counts["salt_bridges"] == 1
    assert counts["dual_labeled_pairs"] == 1


def test_aspartate_ammonium_inside_hbond_distance_is_counted_in_both_classes():
    """The acidic branch: ASP carboxylate against a protonated ligand amine.

    The ligand nitrogen carries an explicit AutoDock polar hydrogen, so it is a
    donor as well as a cation.
    """
    protein = [_protein_atom("OD1", "ASP", "O", 0.0, resseq=189)]
    ligand = [
        _ligand_atom("N1", "N", 3.0, ad_type="N", charge=0.3),
        _ligand_atom("HN1", "H", 3.0, y=1.0, ad_type="HD"),  # 1.0 A from N1
    ]

    contacts = _detect_contacts(protein, ligand)

    assert _labels(contacts) == [HBOND_LABEL, SALT_BRIDGE_LABEL]
    assert all(c.residue == "ASP189" and c.ligand_atom == "N1" for c in contacts)


# ---------------------------------------------------------------------------
# Single-label cases must be unaffected
# ---------------------------------------------------------------------------

def test_salt_bridge_outside_hbond_distance_still_carries_one_label():
    """At 3.8 A the pair is ionic only; multi-labelling must not invent an H-bond."""
    protein = [_protein_atom("NH1", "ARG", "N", 0.0)]
    ligand = [_ligand_atom("O1", "O", 3.8, ad_type="OA", charge=-0.8)]

    counts = summarize_contacts(_detect_contacts(protein, ligand))

    assert counts["h_bonds"] == 0
    assert counts["salt_bridges"] == 1
    assert counts["salt_bridges_single_label"] == 1
    assert counts["dual_labeled_pairs"] == 0


def test_uncharged_hydrogen_bond_still_carries_one_label():
    """A neutral acceptor is an H-bond and nothing else."""
    protein = [_protein_atom("NH1", "ARG", "N", 0.0)]
    ligand = [_ligand_atom("O1", "O", 3.0, ad_type="OA", charge=0.0)]

    counts = summarize_contacts(_detect_contacts(protein, ligand))

    assert counts["h_bonds"] == 1
    assert counts["salt_bridges"] == 0
    assert counts["dual_labeled_pairs"] == 0


def test_hydrophobic_contacts_can_never_be_multi_labelled():
    """Hydrophobic contacts are carbon-carbon, so they exclude the polar classes."""
    protein = [_protein_atom("CB", "ALA", "C", 0.0)]
    ligand = [_ligand_atom("C1", "C", 4.0, charge=-0.8)]

    counts = summarize_contacts(_detect_contacts(protein, ligand))

    assert counts["hydrophobic"] == 1
    assert counts["h_bonds"] == 0
    assert counts["salt_bridges"] == 0
    assert counts["dual_labeled_pairs"] == 0


def test_a_label_is_never_assigned_twice_to_the_same_atom_pair():
    """Two chains sharing a residue/atom name must not inflate a single class."""
    protein = [
        _protein_atom("NH1", "ARG", "N", 0.0, resseq=7, chain="A"),
        _protein_atom("NH1", "ARG", "N", 0.0, y=0.2, resseq=7, chain="B"),
    ]
    ligand = [_ligand_atom("O1", "O", 3.0, ad_type="OA", charge=-0.8)]

    counts = summarize_contacts(_detect_contacts(protein, ligand))

    assert counts["h_bonds"] == 1
    assert counts["salt_bridges"] == 1
    assert counts["total_single_label"] == 1


# ---------------------------------------------------------------------------
# Count bookkeeping
# ---------------------------------------------------------------------------

def test_counts_are_internally_consistent_on_a_mixed_pose():
    """Every reported number must be derivable from the same contact list."""
    protein = [
        _protein_atom("NH1", "ARG", "N", 0.0, resseq=7),        # dual-label partner
        _protein_atom("OD1", "ASP", "O", 40.0, resseq=25),      # ionic only (3.8 A)
        _protein_atom("CB", "ALA", "C", 80.0, resseq=31),       # hydrophobic only
        _protein_atom("NE2", "HIS", "N", 120.0, resseq=57),     # H-bond only
    ]
    ligand = [
        _ligand_atom("O1", "O", 3.0, ad_type="OA", charge=-0.8),
        _ligand_atom("N2", "N", 43.8, ad_type="N", charge=0.3),
        _ligand_atom("C3", "C", 84.0),
        _ligand_atom("O4", "O", 123.2, ad_type="OA", charge=0.0),
    ]

    contacts = _detect_contacts(protein, ligand)
    counts = summarize_contacts(contacts)

    assert counts["h_bonds"] == 2                     # ARG7 (dual) + HIS57
    assert counts["hydrophobic"] == 1
    assert counts["salt_bridges"] == 2                # ARG7 (dual) + ASP25
    assert counts["salt_bridges_single_label"] == 1   # only ASP25 under the old rule
    assert counts["dual_labeled_pairs"] == 1

    # The two totals differ by exactly the number of extra labels.
    assert counts["total"] == len(contacts)
    assert counts["total"] == counts["h_bonds"] + counts["hydrophobic"] + counts["salt_bridges"]
    assert counts["total_single_label"] == counts["total"] - counts["dual_labeled_pairs"]
    assert counts["salt_bridges_single_label"] == (
        counts["salt_bridges"] - counts["dual_labeled_pairs"]
    )


def test_legacy_precedence_is_documented_in_the_order_it_was_applied():
    """`*_single_label` is only meaningful against the precedence it replaced."""
    assert LEGACY_LABEL_PRECEDENCE == (HBOND_LABEL, HYDROPHOBIC_LABEL, SALT_BRIDGE_LABEL)


def test_empty_contact_list_summarises_to_zeroes():
    assert summarize_contacts([]) == {
        "h_bonds": 0,
        "hydrophobic": 0,
        "salt_bridges": 0,
        "salt_bridges_single_label": 0,
        "total": 0,
        "total_single_label": 0,
        "dual_labeled_pairs": 0,
    }


# ---------------------------------------------------------------------------
# End-to-end through the HTTP contract
# ---------------------------------------------------------------------------

def _pdbqt_line(serial, name, resname, chain, resseq, x, y, z, charge, ad_type):
    """A PDBQT ATOM record in the exact columns `_parse_pdbqt_atoms` reads."""
    return (
        "ATOM  "
        + f"{serial:>5d}"
        + " "
        + f"{name:<4s}"
        + " "                                   # altLoc
        + f"{resname:>3s}"
        + " "
        + chain
        + f"{resseq:>4d}"
        + "    "                                # iCode + padding
        + f"{x:>8.3f}{y:>8.3f}{z:>8.3f}"
        + f"{1.00:>6.2f}{20.00:>6.2f}"
        + "    "
        + f"{charge:>6.3f}"
        + " "
        + f"{ad_type:<2s}"
        + "\n"
    )


@pytest.fixture
def dual_label_pose(tmp_path):
    """A one-atom receptor and a one-atom ligand forming an H-bonded salt bridge."""
    receptor = tmp_path / "receptor.pdbqt"
    receptor.write_text(
        _pdbqt_line(1, "NH1", "ARG", "A", 7, 0.0, 0.0, 0.0, 0.0, "N")
        + _pdbqt_line(2, "CB", "ALA", "A", 8, 40.0, 0.0, 0.0, 0.0, "C")
        + "END\n",
        encoding="utf-8",
    )
    ligand = tmp_path / "ligand_out.pdbqt"
    ligand.write_text(
        "ROOT\n"
        + _pdbqt_line(1, "O1", "LIG", "L", 1, 3.0, 0.0, 0.0, -0.800, "OA")
        + _pdbqt_line(2, "C1", "LIG", "L", 1, 43.0, 0.0, 0.0, 0.000, "C")
        + "ENDROOT\nTORSDOF 0\n",
        encoding="utf-8",
    )
    return receptor, ligand


def test_pdbqt_fixture_parses_into_the_atoms_the_test_intends(dual_label_pose):
    """Guards the fixture itself: a column slip would silently void the HTTP test."""
    receptor, ligand = dual_label_pose

    protein_atoms = _parse_pdbqt_atoms(str(receptor))
    ligand_atoms = _parse_pdbqt_atoms(str(ligand))

    assert [(a["name"], a["resname"], a["resseq"], a["element"]) for a in protein_atoms] == [
        ("NH1", "ARG", 7, "N"),
        ("CB", "ALA", 8, "C"),
    ]
    assert [(a["name"], a["ad_type"], a["charge"]) for a in ligand_atoms] == [
        ("O1", "OA", -0.8),
        ("C1", "C", 0.0),
    ]


def test_analyze_endpoint_reports_both_counts_and_the_legacy_totals(dual_label_pose):
    """The published API surfaces the exhaustive and the legacy numbers side by side."""
    receptor, ligand = dual_label_pose

    with TestClient(app) as client:
        response = client.post(
            "/api/interactions/analyze",
            json={"receptor_path": str(receptor), "ligand_path": str(ligand)},
        )

    assert response.status_code == 200
    body = response.json()

    assert body["h_bonds"] == 1
    assert body["hydrophobic"] == 1
    assert body["salt_bridges"] == 1
    assert body["salt_bridges_single_label"] == 0
    assert body["dual_labeled_pairs"] == 1
    assert body["total"] == 3
    assert body["total_single_label"] == 2
    assert len(body["interactions"]) == body["total"]

    ionic = [i for i in body["interactions"] if i["type"] == SALT_BRIDGE_LABEL]
    assert [(i["residue"], i["receptor_atom"], i["ligand_atom"]) for i in ionic] == [
        ("ARG7", "NH1", "O1")
    ]


def test_network_endpoint_emits_one_edge_per_label(dual_label_pose):
    """The interaction graph must show the ionic edge it previously suppressed."""
    receptor, ligand = dual_label_pose

    with TestClient(app) as client:
        response = client.post(
            "/api/interactions/network",
            json={"receptor_path": str(receptor), "ligand_path": str(ligand)},
        )

    assert response.status_code == 200
    body = response.json()

    edge_types = sorted(e["type"] for e in body["edges"])
    assert edge_types == ["hbond", "hydrophobic", "ionic"]
    assert body["counts"]["salt_bridges"] == 1
    assert body["counts"]["dual_labeled_pairs"] == 1
