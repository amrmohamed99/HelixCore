"""
Chemical Clustering — Butina clustering with diversity-pick selection.
Groups compounds by Tanimoto similarity of Morgan fingerprints.
"""

import os
import csv
from fastapi import APIRouter, HTTPException

from backend.models.schemas import ClusterRequest, ClusterMember, Cluster, ClusterResponse

router = APIRouter()

try:
    from rdkit import Chem, DataStructs
    from rdkit.Chem import AllChem, Descriptors
    from rdkit.ML.Cluster import Butina
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


@router.post("/analyze", response_model=ClusterResponse)
async def cluster_compounds(req: ClusterRequest):
    """Cluster docking results by Tanimoto similarity and pick diverse representatives."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")

    res_dir = req.results_dir
    src_dir = req.src_dir or res_dir
    cutoff = req.cutoff if req.cutoff else 0.4

    if not os.path.isdir(res_dir):
        raise HTTPException(status_code=400, detail="Results directory not found")

    entries: list[tuple[str, str, float]] = []

    for fname in sorted(os.listdir(res_dir)):
        if fname.endswith("_out.pdbqt"):
            name = fname.replace("_out.pdbqt", "")
            score = 0.0
            log_path = os.path.join(res_dir, f"{name}_log.log")
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 2 and parts[0] == "1":
                            try:
                                score = float(parts[1])
                            except ValueError:
                                pass
                            break
            entries.append((name, fname, score))

    if len(entries) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 compounds to cluster")

    mols: list = []
    valid_entries: list[tuple[str, float, str | None]] = []

    for name, fname, score in entries:
        mol = None
        smi = None
        src_pdb = os.path.join(src_dir, f"{name}.pdb")
        src_sdf = os.path.join(src_dir, f"{name}.sdf")
        if os.path.exists(src_pdb):
            mol = Chem.MolFromPDBFile(src_pdb)
        elif os.path.exists(src_sdf):
            mol = Chem.MolFromMolFile(src_sdf)

        if mol:
            smi = Chem.MolToSmiles(mol)
            mols.append(mol)
            valid_entries.append((name, score, smi))

    if len(mols) < 2:
        raise HTTPException(status_code=400, detail="Fewer than 2 valid molecules for clustering")

    radius = 2
    n_bits = 2048
    fps = [AllChem.GetMorganFingerprintAsBitVect(m, radius, nBits=n_bits) for m in mols]

    n = len(fps)
    dists = []
    for i in range(1, n):
        for j in range(i):
            sim = DataStructs.TanimotoSimilarity(fps[i], fps[j])
            dists.append(1.0 - sim)

    butina_clusters = Butina.ClusterData(dists, n, cutoff, isDistData=True)

    clusters: list[Cluster] = []
    singletons = 0

    for cid, members in enumerate(butina_clusters):
        if len(members) == 1:
            singletons += 1
        centroid_idx = members[0]
        member_list: list[ClusterMember] = []
        for m_idx in members:
            name, score, smi = valid_entries[m_idx]
            mw = None
            try:
                mw = round(Descriptors.MolWt(mols[m_idx]), 2)
            except Exception:
                pass
            member_list.append(ClusterMember(
                name=name,
                score=score,
                smiles=smi,
                is_centroid=(m_idx == centroid_idx),
            ))
        clusters.append(Cluster(
            cluster_id=cid,
            size=len(members),
            members=member_list,
        ))

    return ClusterResponse(
        clusters=clusters,
        total_compounds=len(mols),
        num_clusters=len(clusters),
        singletons=singletons,
    )
