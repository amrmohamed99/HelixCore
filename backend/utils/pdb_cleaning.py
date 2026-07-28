"""
PDB cleaning helpers — produce a Meeko-friendly receptor PDB.

The default RCSB PDB often contains:
  * crystallographic waters       → strip (HOH/WAT/DOD/SOL/TIP3/TP3)
  * alternative atom locations    → handled later by Meeko's default_altloc
  * selenomethionine (MSE)        → convert to standard methionine (MET)
  * glycans (NAG, BMA, MAN, ...)  → strip (Meeko has no templates for them)
  * co-crystal ligands (HETATM)   → strip (we only want the receptor)
  * catalytic metals (ZN, MG, …)  → strip (require special docking handling)
  * non-standard residues         → strip (Meeko cannot template them)

After this pass the file contains only standard amino-acid ATOM records,
which Meeko parameterises reliably without falling back to a foreign engine.
"""

from __future__ import annotations

# Standard amino-acid residues + common protonation/disulfide variants.
# Anything outside this set is dropped from the cleaned PDB.
_STANDARD_AA = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLU", "GLN", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    # Protonation / disulfide variants used by AMBER/CHARMM force fields
    "HID", "HIE", "HIP", "CYX", "CYM", "ASH", "GLH", "LYN",
}

# Selenomethionine — chemically equivalent to methionine; the SE atom is
# the selenium analogue of the SD sulfur. Always safe to substitute.
_MSE_REMAP = {"MSE": ("MET", {"SE": " SD "})}


def clean_pdb_for_meeko(raw_pdb_path: str, clean_pdb_path: str) -> dict:
    """Strip a raw PDB down to standard-residue ATOM lines only.

    Returns a small report describing what was kept/removed (for logging/UI).
    """
    kept_atoms = 0
    dropped_residues: dict[str, int] = {}
    converted_mse = 0
    models_detected = 0
    first_model_complete = False
    processing_model = True

    with open(raw_pdb_path, "r") as f_in, open(clean_pdb_path, "w") as f_out:
        for line in f_in:
            tag = line[:6].strip()

            if tag == "MODEL":
                models_detected += 1
                processing_model = models_detected == 1
                continue

            if tag == "ENDMDL":
                if models_detected == 1 and processing_model:
                    first_model_complete = True
                    processing_model = False
                continue

            if first_model_complete and models_detected:
                if tag == "END":
                    f_out.write(line)
                continue

            if not processing_model:
                continue

            if tag == "ATOM":
                resname = line[17:20].strip()
                if resname in _STANDARD_AA:
                    f_out.write(line)
                    kept_atoms += 1
                else:
                    dropped_residues[resname] = dropped_residues.get(resname, 0) + 1
                continue

            if tag == "HETATM":
                resname = line[17:20].strip()

                # Convert MSE → MET so the residue is preserved as a normal AA
                if resname in _MSE_REMAP:
                    new_res, atom_remap = _MSE_REMAP[resname]
                    atom_field = line[12:16]
                    new_atom = atom_remap.get(atom_field.strip(), atom_field)
                    rebuilt = (
                        "ATOM  "
                        + line[6:12]
                        + new_atom
                        + line[16:17]
                        + f"{new_res:<3}"
                        + line[20:]
                    )
                    f_out.write(rebuilt)
                    converted_mse += 1
                    kept_atoms += 1
                else:
                    dropped_residues[resname] = dropped_residues.get(resname, 0) + 1
                continue

            if tag in ("TER", "END", "ENDMDL"):
                f_out.write(line)
                continue

            # Drop everything else (REMARK, HEADER, CONECT, ANISOU, ...)
            #   — they are either irrelevant for docking or actively confuse
            #   downstream tools.

    return {
        "kept_atoms": kept_atoms,
        "converted_mse": converted_mse,
        "dropped_residues": dropped_residues,
        "models_detected": models_detected,
    }
