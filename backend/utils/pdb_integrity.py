"""PDB integrity diagnostics for receptor preparation."""

from __future__ import annotations

from collections import defaultdict
from math import dist
from typing import Any

_BACKBONE = {"N", "CA", "C", "O"}


def _res_key(line: str) -> tuple[str, int, str, str]:
    chain = line[21].strip() or "_"
    try:
        resseq = int(line[22:26])
    except ValueError:
        resseq = 0
    icode = line[26].strip()
    resname = line[17:20].strip()
    return chain, resseq, icode, resname


def analyze_pdb_integrity(pdb_path: str) -> dict[str, Any]:
    """Return chain/residue counts and common break indicators for a PDB file."""
    residues: dict[tuple[str, int, str, str], set[str]] = defaultdict(set)
    chain_resseqs: dict[str, set[int]] = defaultdict(set)
    ca_coords: dict[str, list[tuple[int, tuple[float, float, float]]]] = defaultdict(list)
    atom_count = 0
    model_count = 0

    with open(pdb_path, "r") as f:
        for line in f:
            if line.startswith("MODEL "):
                model_count += 1
                continue
            if not line.startswith(("ATOM  ", "HETATM")):
                continue
            atom_count += 1
            if not line.startswith("ATOM  "):
                continue
            key = _res_key(line)
            chain, resseq, _, _ = key
            atom = line[12:16].strip()
            residues[key].add(atom)
            chain_resseqs[chain].add(resseq)
            if atom == "CA":
                try:
                    coord = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
                    ca_coords[chain].append((resseq, coord))
                except ValueError:
                    pass

    missing_backbone: list[dict[str, Any]] = []
    for (chain, resseq, icode, resname), atoms in residues.items():
        missing = sorted(_BACKBONE - atoms)
        if missing:
            missing_backbone.append({
                "chain": chain,
                "residue": resseq,
                "icode": icode,
                "resname": resname,
                "missing": missing,
            })

    sequence_gaps: list[dict[str, Any]] = []
    for chain, nums in chain_resseqs.items():
        ordered = sorted(nums)
        for prev, cur in zip(ordered, ordered[1:]):
            if cur - prev > 1:
                sequence_gaps.append({"chain": chain, "from": prev, "to": cur, "missing_count": cur - prev - 1})

    ca_breaks: list[dict[str, Any]] = []
    for chain, coords in ca_coords.items():
        ordered = sorted(coords, key=lambda item: item[0])
        for (prev_res, prev_xyz), (cur_res, cur_xyz) in zip(ordered, ordered[1:]):
            if cur_res - prev_res != 1:
                continue
            distance = dist(prev_xyz, cur_xyz)
            if distance > 4.5:
                ca_breaks.append({
                    "chain": chain,
                    "from": prev_res,
                    "to": cur_res,
                    "distance": round(distance, 2),
                })

    chains = sorted(chain_resseqs)
    status = "ok"
    warnings: list[str] = []
    if sequence_gaps:
        warnings.append(f"{len(sequence_gaps)} residue numbering gap(s)")
    if ca_breaks:
        warnings.append(f"{len(ca_breaks)} possible backbone break(s)")
    if missing_backbone:
        warnings.append(f"{len(missing_backbone)} residue(s) missing backbone atoms")
    if model_count > 1:
        warnings.append(f"{model_count} MODEL sections detected")
    if warnings:
        status = "warning"

    return {
        "status": status,
        "atom_count": atom_count,
        "model_count": model_count,
        "residue_count": len(residues),
        "chains": chains,
        "chain_residue_counts": {chain: len(nums) for chain, nums in sorted(chain_resseqs.items())},
        "sequence_gaps": sequence_gaps[:25],
        "ca_breaks": ca_breaks[:25],
        "missing_backbone": missing_backbone[:25],
        "warnings": warnings,
    }


def compare_integrity(before_path: str, after_path: str) -> dict[str, Any]:
    """Compare two PDB files before/after cleaning."""
    before = analyze_pdb_integrity(before_path)
    after = analyze_pdb_integrity(after_path)
    removed_chains = sorted(set(before["chains"]) - set(after["chains"]))
    atom_delta = before["atom_count"] - after["atom_count"]
    residue_delta = before["residue_count"] - after["residue_count"]
    warnings = list(after["warnings"])
    if removed_chains:
        warnings.append("removed chain(s): " + ", ".join(removed_chains))
    if residue_delta > 0:
        warnings.append(f"{residue_delta} residue(s) removed during cleaning")
    if before.get("model_count", 0) > 1:
        warnings.append(f"source had {before['model_count']} MODEL sections; cleaned output uses the first model")

    return {
        "before": before,
        "after": after,
        "atom_delta": atom_delta,
        "residue_delta": residue_delta,
        "removed_chains": removed_chains,
        "status": "warning" if warnings else "ok",
        "warnings": warnings,
    }
