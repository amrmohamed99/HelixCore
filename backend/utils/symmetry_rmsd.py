"""Calculate symmetry-aware, in-place heavy-atom RMSD for redocking evidence.

Both inputs must be sanitized SDF files in the same receptor coordinate frame.
Unlike an alignment RMSD, rdMolAlign.CalcRMS does not superimpose the pose onto
the reference before measuring displacement.

This module is the single implementation used by both the application contract
tests and the redocking evidence pipeline, so the published metric and the
tested metric cannot drift apart. It is also runnable directly:

    python -m backend.utils.symmetry_rmsd --reference ref.sdf --pose pose.sdf
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from rdkit import Chem, rdBase
from rdkit.Chem import rdMolAlign

SUCCESS_THRESHOLD_ANGSTROM = 2.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_heavy_molecule(path: Path) -> Chem.Mol:
    if path.suffix.lower() not in {".sdf", ".mol"}:
        raise ValueError(f"{path}: expected a sanitized SDF or MOL file")
    # Some legacy Open Babel builds preserve explicit proton coordinates in a
    # PDBQT-to-SDF conversion but assign an unsanitized valence to protonated
    # heteroatoms.  The locked metric is heavy-atom RMSD, so parse without
    # sanitizing, remove explicit H/D/T atoms, then sanitize the retained graph.
    supplier = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=False)
    molecule = next((mol for mol in supplier if mol is not None), None)
    if molecule is None:
        raise ValueError(f"{path}: RDKit could not parse and sanitize a molecule")
    if molecule.GetNumConformers() != 1:
        raise ValueError(f"{path}: expected exactly one coordinate conformer")
    try:
        heavy_molecule = Chem.RemoveHs(molecule, sanitize=False)
        Chem.SanitizeMol(heavy_molecule)
    except Exception as exc:
        raise ValueError(f"{path}: RDKit could not sanitize the heavy-atom graph") from exc
    return heavy_molecule


def heavy_elements(molecule: Chem.Mol) -> Counter[int]:
    return Counter(atom.GetAtomicNum() for atom in molecule.GetAtoms() if atom.GetAtomicNum() > 1)


def calculate(reference_path: Path, pose_path: Path, expected_heavy_atoms: int | None) -> dict[str, object]:
    reference = load_heavy_molecule(reference_path)
    pose = load_heavy_molecule(pose_path)

    reference_count = reference.GetNumHeavyAtoms()
    pose_count = pose.GetNumHeavyAtoms()
    if reference_count != pose_count:
        raise ValueError(
            f"heavy-atom count mismatch: reference={reference_count}, pose={pose_count}; "
            "silent truncation is forbidden"
        )
    if expected_heavy_atoms is not None and reference_count != expected_heavy_atoms:
        raise ValueError(
            f"manifest integrity failure: expected {expected_heavy_atoms} heavy atoms, "
            f"found {reference_count}"
        )
    if heavy_elements(reference) != heavy_elements(pose):
        raise ValueError("heavy-element composition mismatch between reference and pose")

    try:
        rmsd = float(
            rdMolAlign.CalcRMS(
                pose,
                reference,
                maxMatches=1_000_000,
                symmetrizeConjugatedTerminalGroups=True,
            )
        )
    except RuntimeError as exc:
        raise ValueError(
            "RDKit could not find a full symmetry-aware graph mapping; verify bond orders and sanitization"
        ) from exc

    return {
        "schema_version": "1.0",
        "method": "RDKit rdMolAlign.CalcRMS; symmetry-aware; in-place; heavy atoms",
        "rdkit_version": rdBase.rdkitVersion,
        "reference": {
            "path": str(reference_path.resolve()),
            "sha256": sha256(reference_path),
            "heavy_atoms": reference_count,
        },
        "pose": {
            "path": str(pose_path.resolve()),
            "sha256": sha256(pose_path),
            "heavy_atoms": pose_count,
        },
        "rmsd_angstrom": rmsd,
        "success_threshold_angstrom": SUCCESS_THRESHOLD_ANGSTROM,
        "status": "PASS" if rmsd < SUCCESS_THRESHOLD_ANGSTROM else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path, help="Crystal ligand SDF/MOL")
    parser.add_argument("--pose", required=True, type=Path, help="First docked pose SDF/MOL")
    parser.add_argument("--expected-heavy-atoms", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON evidence path")
    args = parser.parse_args()

    result = calculate(args.reference, args.pose, args.expected_heavy_atoms)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
