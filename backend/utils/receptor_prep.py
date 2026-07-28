"""
Receptor preparation — convert a cleaned PDB to a Vina-ready PDBQT
using Meeko (the official AutoDock/Vina prep library).

Meeko uses RDKit + ProDy + its own AutoDock atom-type tables and PDBQT
writer. No external binary (OpenBabel, MGLTools) is required, and large
multi-chain proteins are handled correctly provided the input PDB has
been cleaned (see backend.utils.pdb_cleaning.clean_pdb_for_meeko).

If Meeko reports unknown residues on the first pass, we retry once with
those residues explicitly deleted before giving up.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


_UNKNOWN_RES_RE = re.compile(
    r"Template generation failed for unknown residues:\s*\{([^}]*)\}",
    re.IGNORECASE,
)


def _extract_unknown_residues(error_message: str) -> set[str]:
    """Pull residue names out of a Meeko PolymerCreationError message."""
    match = _UNKNOWN_RES_RE.search(error_message)
    if not match:
        return set()
    return {tok.strip().strip("'\"") for tok in match.group(1).split(",") if tok.strip()}


def _build_polymer(pdb_string: str, residues_to_delete: list[str] | None = None):
    """Run Meeko's Polymer.from_pdb_string with sensible defaults."""
    from meeko import (
        MoleculePreparation,
        Polymer,
        ResidueChemTemplates,
    )

    templates = ResidueChemTemplates.create_from_defaults()
    mk_prep = MoleculePreparation.from_config({})

    # allow_bad_res=True   — skip residues that don't match any template
    #                        instead of aborting the entire receptor.
    # default_altloc='A'   — pick the first conformer for residues with
    #                        alternate locations (very common in X-ray data).
    # residues_to_delete   — explicit list of residue *names* (e.g. ['NAG'])
    #                        to remove before parameterisation.
    return Polymer.from_pdb_string(
        pdb_string,
        templates,
        mk_prep,
        allow_bad_res=True,
        default_altloc="A",
        residues_to_delete=residues_to_delete,
    )


def prepare_receptor_pdbqt(clean_pdb: str, out_pdbqt: str) -> dict:
    """Convert a cleaned PDB into a rigid-receptor PDBQT using Meeko.

    Returns a small report dict with the engine name, atom count, and
    any residues that had to be skipped on the second pass.
    """
    from meeko import PDBQTWriterLegacy

    with open(clean_pdb, "r") as f:
        pdb_string = f.read()

    try:
        polymer = _build_polymer(pdb_string)
        skipped: list[str] = []
    except Exception as first_err:
        # Second chance: parse Meeko's complaint to find the unknown residue
        # names, delete them, and try again. Covers rare HETATM/cofactor
        # cases that survived the cleaning pass.
        unknown = _extract_unknown_residues(str(first_err))
        if not unknown:
            raise RuntimeError(f"Meeko receptor preparation failed: {first_err}") from first_err

        logger.warning(
            "Meeko could not template residues %s — retrying with them deleted",
            sorted(unknown),
        )
        try:
            polymer = _build_polymer(pdb_string, residues_to_delete=sorted(unknown))
            skipped = sorted(unknown)
        except Exception as second_err:
            raise RuntimeError(
                f"Meeko receptor preparation failed even after deleting {sorted(unknown)}: "
                f"{second_err}"
            ) from second_err

    rigid_pdbqt, _flex = PDBQTWriterLegacy.write_from_polymer(polymer)
    if not rigid_pdbqt or not rigid_pdbqt.strip():
        raise RuntimeError("Meeko produced an empty PDBQT output")

    with open(out_pdbqt, "w") as f:
        f.write(rigid_pdbqt)

    return {
        "engine": "meeko",
        "skipped_residues": skipped,
        "pdbqt_bytes": len(rigid_pdbqt),
    }
