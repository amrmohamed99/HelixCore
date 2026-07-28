"""
Protein-Ligand Interaction Profiler — detects H-bonds, hydrophobic,
and salt-bridge contacts from a docked pose.

Classification is **multi-label**: one receptor-atom/ligand-atom pair may carry
more than one label.  In particular a charge-complementary pair that also sits
inside the hydrogen-bond distance is reported as *both* a hydrogen bond and a
salt bridge, so salt-bridge counts are an exhaustive enumeration rather than a
classification summary.  The pre-multi-label numbers remain available as the
``*_single_label`` fields of :class:`InteractionResponse`.
"""

import os
import math
from fastapi import APIRouter, HTTPException

from backend.models.schemas import InteractionRequest, Interaction, InteractionResponse

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdmolops
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


# Distance thresholds (heavy atom-heavy atom)
HBOND_DIST = 3.5       # Å — McDonald & Thornton 1994
HBOND_DIST_S = 3.9     # Å — sulfur H-bonds are longer due to larger vdW radius (Zhou et al. 2009)
HYDROPHOBIC_DIST = 4.5 # Å — standard van der Waals contact distance
SALT_BRIDGE_DIST = 4.0 # Å — Kumar & Nussinov 1999

# Interaction labels.  A pair may carry several of these simultaneously.
HBOND_LABEL = "H-bond"
HYDROPHOBIC_LABEL = "Hydrophobic"
SALT_BRIDGE_LABEL = "Salt bridge"
# Order in which labels were applied before multi-label reporting; the first
# match won and suppressed the rest.  Retained only to document how
# ``total_single_label`` and ``salt_bridges_single_label`` are defined.
LEGACY_LABEL_PRECEDENCE = (HBOND_LABEL, HYDROPHOBIC_LABEL, SALT_BRIDGE_LABEL)

HYDROPHOBIC_ATOMS = {"C"}
# Salt bridge detection by residue name (avoids protonation ambiguity)
SALT_BRIDGE_POS_RESIDUES = {
    "ARG": {"NH1", "NH2", "NE"},   # Guanidinium (always charged at pH 7.4)
    "LYS": {"NZ"},                  # Ammonium (pKa ~10.5)
}
SALT_BRIDGE_NEG_RESIDUES = {
    "ASP": {"OD1", "OD2"},         # Carboxylate (pKa ~3.7)
    "GLU": {"OE1", "OE2"},         # Carboxylate (pKa ~4.1)
}
# Protein atom names that are H-bond donors (have attached H)
HBOND_DONORS = {"N", "NE", "NH1", "NH2", "ND1", "ND2", "NE2", "NZ", "OG", "OG1", "OH", "NE1", "SG"}
# Protein atom names that are H-bond acceptors (have lone pairs)
HBOND_ACCEPTORS = {"O", "OD1", "OD2", "OE1", "OE2", "OG", "OG1", "OH", "ND1", "NE2", "SD", "SG"}


def _distance(c1, c2) -> float:
    """Euclidean distance between two (x, y, z) tuples."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _ad_type_to_element(ad_type: str) -> str:
    """Convert AutoDock PDBQT atom type to element symbol."""
    _MAP = {
        "A": "C", "OA": "O", "NA": "N", "NS": "N", "OS": "O",
        "SA": "S", "HD": "H", "HS": "H",
        "Cl": "Cl", "CL": "Cl", "Br": "Br", "BR": "Br",
        "Zn": "Zn", "ZN": "Zn", "Fe": "Fe", "FE": "Fe",
        "Mn": "Mn", "MN": "Mn", "Mg": "Mg", "MG": "Mg",
        "Ca": "Ca", "CA": "Ca",
    }
    return _MAP.get(ad_type, ad_type if len(ad_type) <= 2 else ad_type[0])

# AutoDock atom types that indicate H-bond acceptor capability (lone pairs)
_AD_ACCEPTOR_TYPES = {"OA", "OS", "NA", "NS", "SA"}


def _parse_pdbqt_atoms(path: str) -> list[dict]:
    """Extract atom records from a PDBQT file."""
    atoms = []
    with open(path, "r") as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                try:
                    raw_type = line[77:79].strip() if len(line) > 77 else line[12:16].strip()[0]
                    atoms.append({
                        "name": line[12:16].strip(),
                        "resname": line[17:20].strip(),
                        "chain": line[21].strip(),
                        "resseq": int(line[22:26]),
                        "x": float(line[30:38]),
                        "y": float(line[38:46]),
                        "z": float(line[46:54]),
                        "element": _ad_type_to_element(raw_type),
                        "ad_type": raw_type,
                        "charge": float(line[70:76]) if len(line) > 76 else 0.0,
                    })
                except (ValueError, IndexError):
                    continue
    return atoms


def _identify_ligand_donors(ligand_atoms: list[dict]) -> set[int]:
    """Identify ligand heavy atoms that are H-bond donors (have attached HD hydrogen)."""
    donors: set[int] = set()
    hd_indices = [i for i, a in enumerate(ligand_atoms) if a["ad_type"] in ("HD", "HS")]
    heavy_indices = [i for i, a in enumerate(ligand_atoms) if a["element"] in ("N", "O", "S")]
    for hi in hd_indices:
        h = ligand_atoms[hi]
        hcoord = (h["x"], h["y"], h["z"])
        for ji in heavy_indices:
            j = ligand_atoms[ji]
            d = _distance(hcoord, (j["x"], j["y"], j["z"]))
            if d <= 1.3:  # covalent bond distance
                donors.add(ji)
    return donors


def _classify_pair(pa: dict, la: dict, li: int, d: float, ligand_donors: set[int]) -> list[str]:
    """Return every interaction label a receptor/ligand atom pair satisfies.

    Multi-label by design: the hydrogen-bond and salt-bridge tests are evaluated
    independently, so a charge-complementary pair inside the hydrogen-bond
    distance returns both labels.  (Hydrophobic contacts are element-exclusive
    with the other two — carbon on both sides — so they can never co-occur.)
    """
    labels: list[str] = []

    p_elem = pa["element"].upper()
    l_elem = la["element"].upper()

    # ── Hydrogen bond ──
    # Use longer cutoff when sulfur is involved (larger vdW radius)
    hbond_cutoff = HBOND_DIST_S if (p_elem == "S" or l_elem == "S") else HBOND_DIST
    if d <= hbond_cutoff:
        # N, O are standard H-bond participants; S is a weak acceptor (Met SD, Cys SG)
        if p_elem in {"N", "O", "S"} and l_elem in {"N", "O", "S"}:
            # Require donor-acceptor complementarity:
            # protein donor + ligand acceptor OR protein acceptor + ligand donor
            p_is_donor = pa["name"] in HBOND_DONORS
            p_is_acceptor = pa["name"] in HBOND_ACCEPTORS
            # Ligand donor: has attached HD hydrogen (distance-based)
            l_is_donor = li in ligand_donors
            # Ligand acceptor: AutoDock type indicates lone pairs
            l_is_acceptor = la.get("ad_type", "") in _AD_ACCEPTOR_TYPES
            if (p_is_donor and l_is_acceptor) or (p_is_acceptor and l_is_donor):
                labels.append(HBOND_LABEL)

    # ── Hydrophobic contact ──
    if d <= HYDROPHOBIC_DIST and p_elem == "C" and l_elem == "C":
        labels.append(HYDROPHOBIC_LABEL)

    # ── Salt bridge ──
    if d <= SALT_BRIDGE_DIST:
        resname = pa["resname"]
        atom_name = pa["name"]
        # Validate by residue name to avoid false positives from ambiguous atom names
        is_pos_res = resname in SALT_BRIDGE_POS_RESIDUES and atom_name in SALT_BRIDGE_POS_RESIDUES[resname]
        is_neg_res = resname in SALT_BRIDGE_NEG_RESIDUES and atom_name in SALT_BRIDGE_NEG_RESIDUES[resname]
        if (is_pos_res and l_elem == "O" and la.get("charge", 0.0) < -0.5) or \
           (is_neg_res and l_elem == "N" and la.get("charge", 0.0) > 0.2):
            labels.append(SALT_BRIDGE_LABEL)

    return labels


def _detect_contacts(protein_atoms: list[dict], ligand_atoms: list[dict]) -> list[Interaction]:
    """Detect pairwise interactions between protein and ligand atoms.

    Returns one :class:`Interaction` per *(atom pair, label)*, so a pair that is
    simultaneously a hydrogen bond and a salt bridge appears twice.  Use
    :func:`summarize_contacts` to derive the per-class counts.
    """
    results: list[Interaction] = []
    seen: set[tuple] = set()

    # Pre-compute ligand donor set from HD hydrogen proximity
    ligand_donors = _identify_ligand_donors(ligand_atoms)

    for li, la in enumerate(ligand_atoms):
        lcoord = (la["x"], la["y"], la["z"])
        for pa in protein_atoms:
            pcoord = (pa["x"], pa["y"], pa["z"])
            d = _distance(lcoord, pcoord)
            key = (pa["resname"], pa["resseq"], pa["name"], la["name"])

            for label in _classify_pair(pa, la, li, d, ligand_donors):
                # One entry per (pair, label); repeats of the same pair from
                # e.g. a second chain do not duplicate an existing label.
                if (key, label) in seen:
                    continue
                seen.add((key, label))
                results.append(Interaction(
                    type=label,
                    residue=f"{pa['resname']}{pa['resseq']}",
                    receptor_atom=pa["name"],
                    ligand_atom=la["name"],
                    distance=round(d, 2),
                ))

    return results


def _pair_key(contact: Interaction) -> tuple:
    """Identity of the atom pair a label was assigned to."""
    return (contact.residue, contact.receptor_atom, contact.ligand_atom)


def summarize_contacts(contacts: list[Interaction]) -> dict[str, int]:
    """Count interactions per class, both multi-label and the legacy single-label way.

    ``h_bonds``/``hydrophobic``/``salt_bridges`` count *labels*, so a pair that is
    both a hydrogen bond and a salt bridge is counted in both.  The
    ``*_single_label`` entries reproduce the older one-label-per-pair numbers,
    which resolved overlaps by :data:`LEGACY_LABEL_PRECEDENCE`.
    """
    labels_by_pair: dict[tuple, set[str]] = {}
    for contact in contacts:
        labels_by_pair.setdefault(_pair_key(contact), set()).add(contact.type)

    def _legacy_label(labels: set[str]) -> str | None:
        for label in LEGACY_LABEL_PRECEDENCE:
            if label in labels:
                return label
        return next(iter(sorted(labels)), None)

    legacy_labels = [_legacy_label(labels) for labels in labels_by_pair.values()]

    return {
        "h_bonds": sum(1 for c in contacts if c.type == HBOND_LABEL),
        "hydrophobic": sum(1 for c in contacts if c.type == HYDROPHOBIC_LABEL),
        "salt_bridges": sum(1 for c in contacts if c.type == SALT_BRIDGE_LABEL),
        "salt_bridges_single_label": sum(1 for legacy in legacy_labels if legacy == SALT_BRIDGE_LABEL),
        "total": len(contacts),
        "total_single_label": len(labels_by_pair),
        "dual_labeled_pairs": sum(1 for labels in labels_by_pair.values() if len(labels) > 1),
    }


@router.post("/analyze", response_model=InteractionResponse)
async def analyze_interactions(req: InteractionRequest):
    """Detect protein-ligand interactions from PDBQT pose files."""
    if not os.path.exists(req.receptor_path):
        raise HTTPException(status_code=400, detail="Protein PDBQT not found")
    if not os.path.exists(req.ligand_path):
        raise HTTPException(status_code=400, detail="Ligand PDBQT not found")

    protein_atoms = _parse_pdbqt_atoms(req.receptor_path)
    ligand_atoms = _parse_pdbqt_atoms(req.ligand_path)

    if not protein_atoms:
        raise HTTPException(status_code=400, detail="No atoms parsed from protein file")
    if not ligand_atoms:
        raise HTTPException(status_code=400, detail="No atoms parsed from ligand file")

    contacts = _detect_contacts(protein_atoms, ligand_atoms)

    return InteractionResponse(interactions=contacts, **summarize_contacts(contacts))


@router.post("/network")
async def interaction_network(req: InteractionRequest):
    """Build a force-directed graph from protein-ligand interactions."""
    if not os.path.exists(req.receptor_path):
        raise HTTPException(status_code=400, detail="Protein PDBQT not found")
    if not os.path.exists(req.ligand_path):
        raise HTTPException(status_code=400, detail="Ligand PDBQT not found")

    protein_atoms = _parse_pdbqt_atoms(req.receptor_path)
    ligand_atoms = _parse_pdbqt_atoms(req.ligand_path)
    contacts = _detect_contacts(protein_atoms, ligand_atoms)

    # Build graph nodes and edges
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()

    # Add ligand as central node
    lig_name = os.path.basename(req.ligand_path).replace("_out.pdbqt", "").replace(".pdbqt", "")
    lig_id = f"ligand_{lig_name}"
    nodes.append({"id": lig_id, "label": lig_name, "type": "ligand"})
    seen_nodes.add(lig_id)

    # Type mapping for edges.  Multi-label pairs emit one edge per label, so a
    # residue that is both hydrogen-bonded and salt-bridged shows both.
    type_map = {
        HBOND_LABEL: "hbond",
        HYDROPHOBIC_LABEL: "hydrophobic",
        SALT_BRIDGE_LABEL: "ionic",
        "Pi-stack": "pi_stack",
    }

    for c in contacts:
        res_id = f"residue_{c.residue}"
        if res_id not in seen_nodes:
            nodes.append({"id": res_id, "label": c.residue, "type": "residue"})
            seen_nodes.add(res_id)

        edge_type = type_map.get(c.type, "vdw")
        strength = max(0.2, 1.0 - (c.distance / 5.0)) if c.distance else 0.5
        edges.append({
            "source": lig_id,
            "target": res_id,
            "type": edge_type,
            "strength": round(strength, 2),
            "label": f"{c.type} ({c.distance}Å)",
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "total_interactions": len(contacts),
        "counts": summarize_contacts(contacts),
    }
