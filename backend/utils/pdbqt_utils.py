"""
PDBQT file utilities — cleaning, parsing, fixing.
Ported from drug_tool.py fix_receptor_pdbqt().
"""

import os
import shutil

_LIGAND_TAGS = {"ROOT", "ENDROOT", "BRANCH", "ENDBRANCH", "TORSDOF"}


def fix_receptor_pdbqt(pdbqt_path: str) -> None:
    """Strip ROOT/BRANCH/TORSDOF tags from a receptor PDBQT.

    OpenBabel incorrectly adds flexible-ligand tags to proteins,
    which causes Vina to reject them.  Receptors must be rigid.
    Creates a .bak backup before modifying the file.
    """
    shutil.copy2(pdbqt_path, pdbqt_path + ".bak")
    with open(pdbqt_path, "r") as f:
        lines = f.readlines()

    clean: list[str] = []
    for line in lines:
        tag = line.split()[0] if line.strip() else ""
        if tag in ("ROOT", "ENDROOT", "BRANCH", "ENDBRANCH", "TORSDOF"):
            continue
        if tag == "REMARK" and "torsion" in line.lower():
            continue
        clean.append(line)

    if not any(l.startswith("END") for l in clean[-3:]):
        clean.append("END\n")

    with open(pdbqt_path, "w") as f:
        f.writelines(clean)


def validate_receptor_pdbqt(pdbqt_path: str) -> None:
    """Validate that a receptor PDBQT is rigid and contains atom records."""
    atom_count = 0
    ligand_tags: set[str] = set()

    with open(pdbqt_path, "r") as f:
        for line in f:
            tag = line.split()[0] if line.strip() else ""
            if line.startswith(("ATOM", "HETATM")):
                atom_count += 1
            if tag in _LIGAND_TAGS:
                ligand_tags.add(tag)

    if atom_count == 0:
        raise ValueError("Receptor PDBQT contains no ATOM/HETATM records")
    if ligand_tags:
        raise ValueError(
            "Receptor PDBQT contains ligand-format tag(s): " + ", ".join(sorted(ligand_tags))
        )


def validate_ligand_pdbqt(pdbqt_path: str) -> None:
    """Validate that a ligand PDBQT has atoms and ligand torsion metadata."""
    atom_count = 0
    tags: set[str] = set()

    with open(pdbqt_path, "r") as f:
        for line in f:
            tag = line.split()[0] if line.strip() else ""
            if line.startswith(("ATOM", "HETATM")):
                atom_count += 1
            if tag in _LIGAND_TAGS:
                tags.add(tag)

    if atom_count == 0:
        raise ValueError("Ligand PDBQT contains no ATOM/HETATM records")
    missing = {"ROOT", "ENDROOT", "TORSDOF"} - tags
    if missing:
        raise ValueError("Ligand PDBQT missing required ligand tag(s): " + ", ".join(sorted(missing)))


def parse_vina_score(pdbqt_path: str) -> float:
    """Extract best Vina score from a _out.pdbqt REMARK VINA RESULT line."""
    try:
        with open(pdbqt_path, "r") as f:
            for line in f:
                if line.startswith("REMARK VINA RESULT"):
                    return float(line.split()[3])
    except Exception:
        pass
    return 0.0


def parse_vina_log_score(log_path: str) -> float:
    """Extract best Vina score from a log file (mode 1 line)."""
    try:
        with open(log_path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] == "1":
                    return float(parts[1])
    except Exception:
        pass
    return 0.0


def parse_vina_process_score(
    stdout: str = "",
    stderr: str = "",
    output_path: str | None = None,
) -> float | None:
    """Extract a best Vina score from process output or an output PDBQT.

    Vina builds differ in whether the scoring table is written to stdout or
    stderr.  The output PDBQT REMARK is the final fallback because it is
    emitted with the docked pose itself.
    """
    for text in (stdout or "", stderr or ""):
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0] == "1":
                try:
                    return float(parts[1])
                except ValueError:
                    continue
    if output_path and os.path.isfile(output_path):
        try:
            with open(output_path, "r") as f:
                for line in f:
                    if line.startswith("REMARK VINA RESULT"):
                        return float(line.split()[3])
        except (OSError, ValueError, IndexError):
            pass
    return None


def parse_pdb_atoms(
    pdb_path: str,
    lig_res_name: str = "",
    *,
    lig_chain: str = "",
    lig_resseq: int | None = None,
    lig_icode: str = "",
):
    """Parse protein ATOM and HETATM records from a PDB file.

    Returns (protein_atoms, ligand_atoms) where each atom is
    a dict with 'res', 'seq', and 'coords' (x, y, z) keys.
    """
    protein_atoms: list[dict] = []
    ligand_atoms: list[tuple[float, float, float]] = []

    with open(pdb_path, "r") as f:
        for line in f:
            if line.startswith("ATOM"):
                res_name = line[17:20].strip()
                res_seq = line[22:27].strip()  # Columns 23-27 include insertion code
                try:
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                    protein_atoms.append(
                        {"res": f"{res_name} {res_seq}", "coords": (x, y, z)}
                    )
                except ValueError:
                    pass
            elif line.startswith("HETATM"):
                res = line[17:20].strip()
                # HOH/DOD = crystallographic; WAT/TP3 = AMBER; SOL = GROMACS; TIP3 = CHARMM
                if res in {"HOH", "WAT", "DOD", "SOL", "TIP3", "TP3"}:
                    continue
                if lig_res_name and res != lig_res_name:
                    continue
                chain = line[21].strip()
                icode = line[26].strip()
                try:
                    resseq = int(line[22:26].strip())
                except ValueError:
                    resseq = None
                if lig_chain and chain != lig_chain:
                    continue
                if lig_resseq is not None and resseq != lig_resseq:
                    continue
                if lig_icode and icode != lig_icode:
                    continue
                atom_name = line[12:16].strip()
                element = line[76:78].strip().upper() if len(line) >= 78 else ""
                if not element:
                    element = atom_name.lstrip("0123456789")[:1].upper()
                if element == "H":
                    continue
                try:
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                    ligand_atoms.append((x, y, z))
                except ValueError:
                    pass

    return protein_atoms, ligand_atoms


def parse_atom_coords(path: str) -> list[tuple[float, float, float]]:
    """Parse all ATOM/HETATM coordinates from a PDB/PDBQT file."""
    coords: list[tuple[float, float, float]] = []
    with open(path, "r") as f:
        for line in f:
            if line.startswith("ATOM") or line.startswith("HETATM"):
                try:
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                    coords.append((x, y, z))
                except ValueError:
                    pass
    return coords
