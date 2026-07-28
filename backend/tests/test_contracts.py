"""Regression tests for paper-facing backend contracts.

These tests intentionally avoid starting the application or invoking external
scientific binaries.  They protect the API schema and Vina score extraction
contracts that the manuscript describes as reproducible interfaces.
"""

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from rdkit import Chem
from rdkit.Chem import AllChem

from backend.main import app
from backend.models.schemas import (
    BBB_TRIAGE_CAVEAT,
    AutoGridRequest,
    BatchPipelineResponse,
    BatchRequest,
    DockingRequest,
    InteractionResponse,
    MultiTargetRequest,
    PocketAnalysisRequest,
)
from backend.routers import admet as admet_router
from backend.routers import batch as batch_router
from backend.routers import filters as filters_router
from backend.routers import interactions as interactions_router
from backend.routers.docking import auto_calculate_grid
from backend.routers.pocket import calculate_grid as calculate_pocket_grid
from backend.services.report_builder import generate_html_report
from backend.utils.file_order import sorted_matching_files
from backend.utils.pdbqt_utils import (
    parse_vina_process_score,
    validate_ligand_pdbqt,
    validate_receptor_pdbqt,
)
from backend.routers.interactions import _detect_contacts
from backend.utils.symmetry_rmsd import calculate as calculate_redocking_rmsd


def test_openapi_schema_builds_with_multi_target_contract():
    """All documented routes, including multi-target docking, resolve cleanly."""
    schema = app.openapi()

    assert schema["info"]["version"] == "3.0.0"
    assert "/api/docking/multi-target" in schema["paths"]
    operation = schema["paths"]["/api/docking/multi-target"]["post"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert "seed" in schema["components"]["schemas"]["DockingRequest"]["properties"]
    assert "seed" in schema["components"]["schemas"]["MultiTargetRequest"]["properties"]


def test_docking_contract_uses_a_bounded_deterministic_seed():
    """All docking modes share a declared, valid default Vina seed."""
    request = DockingRequest(ligands_dir="ligands", receptor="receptor.pdbqt")
    multi = MultiTargetRequest(ligands_dir="ligands", receptors=["receptor.pdbqt"])

    assert request.seed == 42
    assert multi.seed == 42

    try:
        DockingRequest(ligands_dir="ligands", receptor="receptor.pdbqt", seed=0)
    except ValueError:
        pass
    else:  # pragma: no cover - documents the reproducibility contract
        raise AssertionError("an invalid Vina seed was accepted")


def test_file_based_scientific_workflows_use_stable_input_order(tmp_path):
    """Directory-backed stages must not inherit platform-dependent enumeration order."""
    for name in ("zeta.PDBQT", "Alpha.pdbqt", "notes.txt", "receptor.pdbqt"):
        (tmp_path / name).write_text("", encoding="utf-8")

    discovered = sorted_matching_files(
        str(tmp_path),
        (".pdbqt",),
        exclude=("receptor.pdbqt",),
    )

    assert discovered == ["Alpha.pdbqt", "zeta.PDBQT"]


def test_redocking_rmsd_is_symmetry_aware_and_in_place(tmp_path):
    """The publication metric accepts identical poses without order-based truncation."""
    molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    assert AllChem.EmbedMolecule(molecule, randomSeed=42) == 0
    reference_path = tmp_path / "reference.sdf"
    pose_path = tmp_path / "pose.sdf"
    Chem.MolToMolFile(molecule, str(reference_path))
    Chem.MolToMolFile(molecule, str(pose_path))

    evidence = calculate_redocking_rmsd(reference_path, pose_path, expected_heavy_atoms=3)

    assert evidence["rmsd_angstrom"] == 0.0
    assert evidence["status"] == "PASS"


def test_vina_score_parser_prefers_process_output():
    """The score table is preferred over a stale output-file remark."""
    score = parse_vina_process_score(
        stdout="\n   1       -8.7      0.000      0.000\n",
        output_path=None,
    )

    assert score == -8.7


def test_vina_score_parser_falls_back_to_stderr_and_pdbqt(tmp_path):
    """Vina builds may write the table to stderr or only emit a PDBQT remark."""
    assert parse_vina_process_score(stderr="  1 -7.25 0 0") == -7.25

    output_path = tmp_path / "docked_out.pdbqt"
    output_path.write_text("REMARK VINA RESULT: -6.10 0.000 0.000\n", encoding="utf-8")
    assert parse_vina_process_score(output_path=str(output_path)) == -6.10


def test_vina_score_parser_returns_none_when_no_score_exists(tmp_path):
    output_path = tmp_path / "empty_out.pdbqt"
    output_path.write_text("REMARK no score\n", encoding="utf-8")

    assert parse_vina_process_score(output_path=str(output_path)) is None


def test_auto_grid_reports_oversized_receptors_instead_of_silent_clamping(tmp_path):
    """A grid larger than Vina's limit must be an explicit user-facing error."""
    receptor_path = tmp_path / "large_receptor.pdb"
    receptor_path.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
        "ATOM      2  CA  ALA A   2     130.000   0.000   0.000  1.00 20.00           C\n",
        encoding="utf-8",
    )

    import asyncio
    from fastapi import HTTPException

    try:
        asyncio.run(auto_calculate_grid(AutoGridRequest(receptor_path=str(receptor_path), padding=10)))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "exceeds AutoDock Vina" in exc.detail
    else:  # pragma: no cover - assertion documents the required contract
        raise AssertionError("oversized auto-grid was silently accepted")


def test_pocket_grid_selects_the_exact_manifest_ligand_instance(tmp_path):
    """Same-named ligands in other chains/residues must not contaminate the grid."""
    pdb_path = tmp_path / "two_ben_instances.pdb"
    pdb_path.write_text(
        "ATOM      1  CA  ALA A  10       0.000   0.000   0.000  1.00 20.00           C\n"
        "ATOM      2  CA  ALA B  10     100.000   0.000   0.000  1.00 20.00           C\n"
        "HETATM    3  C1  BEN A   1       1.000   0.000   0.000  1.00 20.00           C\n"
        "HETATM    4  H1  BEN A   1       1.500   0.000   0.000  1.00 20.00           H\n"
        "HETATM    5  C1  BEN B   2     101.000   0.000   0.000  1.00 20.00           C\n"
        "END\n",
        encoding="utf-8",
    )

    response = asyncio.run(calculate_pocket_grid(PocketAnalysisRequest(
        pdb_path=str(pdb_path), ligand_name="BEN", ligand_chain="A", ligand_resseq=1,
    )))

    assert response.ligand_atom_count == 1  # explicit hydrogen is excluded
    assert response.selected_ligand == {"name": "BEN", "chain": "A", "resseq": 1, "icode": ""}
    assert response.grid.center_x == 0.0
    assert response.grid.size_x == 8.0


def test_pocket_grid_rejects_oversized_geometry_instead_of_clipping(tmp_path):
    pdb_path = tmp_path / "oversized_pocket.pdb"
    pdb_path.write_text(
        "ATOM      1  CA  ALA A  10       0.000   0.000   0.000  1.00 20.00           C\n"
        "ATOM      2  CA  ALA A  11     130.000   0.000   0.000  1.00 20.00           C\n"
        "HETATM    3  C1  BEN A   1       1.000   0.000   0.000  1.00 20.00           C\n"
        "HETATM    4  C2  BEN A   1     129.000   0.000   0.000  1.00 20.00           C\n"
        "END\n",
        encoding="utf-8",
    )

    from fastapi import HTTPException

    try:
        asyncio.run(calculate_pocket_grid(PocketAnalysisRequest(
            pdb_path=str(pdb_path), ligand_name="BEN", ligand_chain="A", ligand_resseq=1,
        )))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "exceeds AutoDock Vina" in exc.detail
    else:  # pragma: no cover - documents the publication contract
        raise AssertionError("oversized pocket grid was silently clipped")


def test_html_report_escapes_user_supplied_content(tmp_path):
    report_path = tmp_path / "report.html"
    generate_html_report(
        str(report_path),
        title='<script>alert("title")</script>',
        sections=[{"title": "Results", "type": "text", "data": "<b>untrusted</b>"}],
        metadata={"project": '<img src=x onerror="alert(1)">'},
    )

    html = report_path.read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "<b>untrusted</b>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;untrusted&lt;/b&gt;" in html


def test_no_embedded_license_secret_material():
    """No obfuscated secret material should ever be committed to the client source."""
    project_root = Path(__file__).resolve().parents[2]
    config_source = (project_root / "backend" / "config.py").read_text(encoding="utf-8")

    assert "_LICENSE_API_KEY_ENC" not in config_source
    assert "decode_secret" not in config_source
    assert not (project_root / "backend" / "utils" / "secrets_enc.py").exists()


def test_pdbqt_validation_distinguishes_rigid_receptors_and_flexible_ligands(tmp_path):
    """Docking inputs must fail early when the PDBQT role is structurally wrong."""
    receptor = tmp_path / "receptor.pdbqt"
    receptor.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00      A   C  0.000\nEND\n",
        encoding="utf-8",
    )
    validate_receptor_pdbqt(str(receptor))

    ligand = tmp_path / "ligand.pdbqt"
    ligand.write_text(
        "ROOT\n"
        "ATOM      1  C1  LIG L   1       0.000   0.000   0.000  1.00  0.00      A   C  0.000\n"
        "ENDROOT\nTORSDOF 0\n",
        encoding="utf-8",
    )
    validate_ligand_pdbqt(str(ligand))

    receptor.write_text(
        "ROOT\n"
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00      A   C  0.000\n",
        encoding="utf-8",
    )
    try:
        validate_receptor_pdbqt(str(receptor))
    except ValueError as exc:
        assert "ligand-format tag" in str(exc)
    else:  # pragma: no cover - documents the safety contract
        raise AssertionError("ligand-format receptor was accepted")


def test_interaction_response_reports_multi_label_and_legacy_counts():
    """A pair that is both an H-bond and a salt bridge is counted in both classes.

    ``salt_bridges`` is the exhaustive enumeration; ``*_single_label`` reproduces
    the one-label-per-pair numbers published before multi-label classification.
    """
    protein = [
        {
            "name": "NH1", "resname": "ARG", "resseq": 7,
            "x": 0.0, "y": 0.0, "z": 0.0, "element": "N", "ad_type": "N", "charge": 0.0,
        },
        {
            "name": "CB", "resname": "ALA", "resseq": 8,
            "x": 20.0, "y": 0.0, "z": 0.0, "element": "C", "ad_type": "C", "charge": 0.0,
        },
    ]
    ligand = [
        # 3.0 A from ARG NH1: inside both the H-bond and the salt-bridge cutoff.
        {
            "name": "O1", "resname": "LIG", "resseq": 1,
            "x": 3.0, "y": 0.0, "z": 0.0, "element": "O", "ad_type": "OA", "charge": -0.8,
        },
        # 4.0 A from ALA CB: a plain hydrophobic contact.
        {
            "name": "C1", "resname": "LIG", "resseq": 1,
            "x": 24.0, "y": 0.0, "z": 0.0, "element": "C", "ad_type": "C", "charge": 0.0,
        },
    ]

    contacts = _detect_contacts(protein, ligand)
    counts = interactions_router.summarize_contacts(contacts)

    assert counts["h_bonds"] == 1
    assert counts["hydrophobic"] == 1
    assert counts["salt_bridges"] == 1          # exhaustive
    assert counts["salt_bridges_single_label"] == 0  # the old, suppressed count
    assert counts["dual_labeled_pairs"] == 1
    assert counts["total"] == len(contacts) == 3
    assert counts["total_single_label"] == 2

    response = InteractionResponse(interactions=contacts, **counts)
    assert response.model_dump()["salt_bridges"] == 1
    assert response.total_single_label == 2


def test_interaction_response_schema_exposes_the_multi_label_counts():
    """The manuscript cites these fields; they must be in the public contract."""
    properties = app.openapi()["components"]["schemas"]["InteractionResponse"]["properties"]

    for field in (
        "h_bonds",
        "hydrophobic",
        "salt_bridges",
        "salt_bridges_single_label",
        "total",
        "total_single_label",
        "dual_labeled_pairs",
    ):
        assert field in properties, f"{field} is missing from InteractionResponse"


def test_interaction_classifier_requires_chemical_complementarity_and_charge():
    """Sulfur H-bonds are supported, while neutral N/O atoms are not salt bridges."""
    protein = [
        {
            "name": "SG", "resname": "CYS", "resseq": 42,
            "x": 0.0, "y": 0.0, "z": 0.0, "element": "S", "ad_type": "S", "charge": 0.0,
        },
        {
            "name": "NH1", "resname": "ARG", "resseq": 7,
            "x": 10.0, "y": 0.0, "z": 0.0, "element": "N", "ad_type": "N", "charge": 0.0,
        },
    ]
    ligand = [
        {
            "name": "O1", "resname": "LIG", "resseq": 1,
            "x": 3.7, "y": 0.0, "z": 0.0, "element": "O", "ad_type": "OA", "charge": 0.0,
        },
        {
            "name": "O2", "resname": "LIG", "resseq": 1,
            "x": 13.8, "y": 0.0, "z": 0.0, "element": "O", "ad_type": "OA", "charge": 0.0,
        },
    ]
    contacts = _detect_contacts(protein, ligand)
    assert any(c.type == "H-bond" and c.ligand_atom == "O1" for c in contacts)
    assert not any(c.type == "Salt bridge" for c in contacts)

    ligand[1]["charge"] = -0.8
    contacts = _detect_contacts(protein, ligand)
    assert any(c.type == "Salt bridge" and c.ligand_atom == "O2" for c in contacts)


def test_paper_facing_scientific_constants_match_the_implementation(monkeypatch):
    """Manuscript-facing thresholds and alert inventory must not drift silently."""
    assert interactions_router.HBOND_DIST == 3.5
    assert interactions_router.HBOND_DIST_S == 3.9
    assert interactions_router.HYDROPHOBIC_DIST == 4.5
    assert interactions_router.SALT_BRIDGE_DIST == 4.0

    assert len(filters_router._STRUCTURAL_ALERTS) == 16
    assert filters_router._COVALENT_WARHEAD_ALERTS == {
        "Michael_Acceptor",
        "Vinyl_Sulfone",
        "Vinyl_Nitrile",
        "Maleimide",
    }
    assert filters_router._COVALENT_WARHEAD_ALERTS <= set(filters_router._STRUCTURAL_ALERTS)

    assert admet_router.BBB_MW_MAX == 450.0
    assert admet_router.BBB_TPSA_MAX == 90.0
    assert admet_router.BBB_LOGP_MIN == 0.5
    assert admet_router.BBB_LOGP_MAX == 4.5

    values = {"mw": 449.9, "tpsa": 89.9, "logp": 0.5}
    monkeypatch.setattr(admet_router.Descriptors, "MolWt", lambda _mol: values["mw"])
    monkeypatch.setattr(admet_router.Descriptors, "TPSA", lambda _mol: values["tpsa"])
    monkeypatch.setattr(admet_router.Descriptors, "MolLogP", lambda _mol: values["logp"])

    assert admet_router._bbb_triage_flag(object()) is True
    values["logp"] = 4.5
    assert admet_router._bbb_triage_flag(object()) is True
    values["logp"] = 0.499
    assert admet_router._bbb_triage_flag(object()) is False
    values["logp"] = 4.501
    assert admet_router._bbb_triage_flag(object()) is False
    values.update({"mw": 450.0, "logp": 2.0})
    assert admet_router._bbb_triage_flag(object()) is False
    values.update({"mw": 449.9, "tpsa": 90.0})
    assert admet_router._bbb_triage_flag(object()) is False
    # The pre-relabel name is still callable and still agrees.
    assert admet_router._bbb_permeable(object()) is False


def test_bbb_contract_is_a_labelled_triage_flag_not_a_permeability_prediction(monkeypatch):
    """The API must show the thresholds and carry the caveat, per plan item 1.5."""
    values = {"mw": 449.9, "tpsa": 89.9, "logp": 0.4}
    monkeypatch.setattr(admet_router.Descriptors, "MolWt", lambda _mol: values["mw"])
    monkeypatch.setattr(admet_router.Descriptors, "TPSA", lambda _mol: values["tpsa"])
    monkeypatch.setattr(admet_router.Descriptors, "MolLogP", lambda _mol: values["logp"])

    triage = admet_router._bbb_triage(object())

    assert triage.flag is False
    assert [(c.name, c.value, c.threshold, c.passed) for c in triage.criteria] == [
        ("MW", 449.9, "450", True),
        ("TPSA", 89.9, "90", True),
        ("LogP", 0.4, "[0.5, 4.5]", False),
    ]
    assert triage.caveat == BBB_TRIAGE_CAVEAT
    assert "not a trained" in BBB_TRIAGE_CAVEAT

    schemas = app.openapi()["components"]["schemas"]
    profile_properties = schemas["ADMETProfile"]["properties"]
    assert "bbb_triage_flag" in profile_properties
    assert "bbb_triage" in profile_properties
    # The old name survives as an explicitly deprecated alias.
    assert profile_properties["bbb_permeable"].get("deprecated") is True
    assert set(schemas["BBBTriage"]["properties"]) >= {"flag", "criteria", "caveat"}


def test_health_probe_and_scientific_routes_are_open():
    """With no license gate, the health probe and scientific APIs are reachable."""
    with TestClient(app) as client:
        health = client.get("/api/health")
        protected = client.get("/api/system/stats")

    assert health.status_code == 200
    assert health.json() == {"status": "online", "version": "3.0.0"}
    assert protected.status_code != 403


def test_batch_generation_counts_double_embedding_failure(tmp_path, monkeypatch):
    """Two failed deterministic embedding attempts must be reported, not written as 3D."""
    smiles_file = tmp_path / "one.smi"
    smiles_file.write_text("CC ethane\n", encoding="utf-8")
    monkeypatch.setattr(batch_router.AllChem, "EmbedMolecule", lambda *args, **kwargs: -1)

    response = asyncio.run(batch_router.generate_batch(BatchRequest(smiles_file=str(smiles_file))))

    assert response.generated == 0
    assert response.failed == 1
    assert response.failures[0].item == "ethane"
    assert response.failures[0].reason == "embedding_failed"
    assert "Both deterministic" in (response.failures[0].detail or "")
    assert list((tmp_path / "Batch_3D").glob("*.pdb")) == []


def test_batch_pipeline_contract_separates_failed_and_successful_docking():
    response = BatchPipelineResponse(total_docked=3, failed_docked=2, message="bounded result")

    assert response.total_docked == 3
    assert response.failed_docked == 2
    assert response.model_dump()["failed_docked"] == 2
