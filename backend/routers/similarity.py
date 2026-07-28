"""
Similarity Search router — PubChem, ChEMBL, and local fingerprint search.
Ported from drug_tool.py: _t_similarity.
"""

import os
import csv
import urllib.parse

import requests
from fastapi import APIRouter, HTTPException

from backend.models.schemas import SimilarityRequest, SimilarityHit, SimilarityResponse

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, DataStructs, MACCSkeys
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


# Method-dependent similarity thresholds for meaningful hit detection
_SIMILARITY_THRESHOLDS = {
    "Morgan": 0.5,    # ECFP-style (sparse, lower absolute values)
    "MACCS": 0.85,    # Dense key-based (higher baseline)
    "RDKit": 0.7,     # Topological path-based
}


def _resolve_query_mol(query: str):
    """Resolve a query string (file path or compound name) to an RDKit Mol."""
    if not RDKIT_AVAILABLE:
        return None

    # Try as file
    if os.path.exists(query):
        try:
            if query.endswith(".sdf"):
                return Chem.SDMolSupplier(query)[0]
            elif query.endswith(".pdb"):
                return Chem.MolFromPDBFile(query)
        except Exception:
            pass

    # Try as PubChem name lookup
    try:
        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            f"{urllib.parse.quote(query)}/property/CanonicalSMILES/JSON"
        )
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            props = data.get("PropertyTable", {}).get("Properties", [])
            if props:
                smi = props[0].get("CanonicalSMILES")
                if smi:
                    return Chem.MolFromSmiles(smi)
    except Exception:
        pass

    # Try as raw SMILES
    try:
        mol = Chem.MolFromSmiles(query)
        if mol:
            return mol
    except Exception:
        pass

    return None


@router.post("/search", response_model=SimilarityResponse)
async def similarity_search(req: SimilarityRequest):
    """Run similarity search against PubChem, ChEMBL, or local database."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")

    query_mol = _resolve_query_mol(req.query)
    if query_mol is None:
        raise HTTPException(
            status_code=400, detail="Could not parse query molecule"
        )

    hits: list[SimilarityHit] = []

    if req.database == "PubChem":
        hits = await _search_pubchem(query_mol)
    elif req.database == "ChEMBL":
        hits = await _search_chembl(query_mol)
    elif req.database == "Local":
        if not req.local_db_path or not os.path.exists(req.local_db_path):
            raise HTTPException(
                status_code=400, detail="Local database file not found"
            )
        hits = _search_local(query_mol, req.method, req.local_db_path)

    # Save report CSV
    report_path = None
    if hits:
        out_dir = os.path.join(os.getcwd(), "Similarity_Results")
        os.makedirs(out_dir, exist_ok=True)
        report_path = os.path.join(out_dir, "Similarity_Report.csv")
        with open(report_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Name/ID", "Score/Similarity", "SMILES"])
            for h in hits:
                w.writerow([h.name, h.score, h.smiles or ""])

    return SimilarityResponse(hits=hits, report_path=report_path)


async def _search_pubchem(query_mol) -> list[SimilarityHit]:
    """PubChem 2D fastsimilarity search."""
    hits: list[SimilarityHit] = []
    try:
        smi = Chem.MolToSmiles(query_mol)
        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
            f"fastsimilarity_2d/smiles/{urllib.parse.quote(smi)}/cids/JSON?Threshold=90"
        )
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            cids = data.get("IdentifierList", {}).get("CID", [])
            subset = cids[:20]
            if subset:
                cids_str = ",".join(map(str, subset))
                url_det = (
                    f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
                    f"cid/{cids_str}/property/Title,CanonicalSMILES/JSON"
                )
                r2 = requests.get(url_det, timeout=15)
                if r2.status_code == 200:
                    props = (
                        r2.json()
                        .get("PropertyTable", {})
                        .get("Properties", [])
                    )
                    for p in props:
                        title = p.get("Title", "Unknown")
                        smiles = p.get("CanonicalSMILES")
                        if smiles:
                            hits.append(
                                SimilarityHit(
                                    name=title, score="0.900", smiles=smiles
                                )
                            )
    except Exception:
        pass
    return hits


async def _search_chembl(query_mol) -> list[SimilarityHit]:
    """ChEMBL similarity search."""
    hits: list[SimilarityHit] = []
    try:
        smi = Chem.MolToSmiles(query_mol)
        url = (
            f"https://www.ebi.ac.uk/chembl/api/data/similarity/"
            f"{urllib.parse.quote(smi)}/40?format=json"
        )
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            for m in data.get("molecules", []):
                chembl_id = m.get("molecule_chembl_id", "Unknown")
                sim_score = m.get("similarity", "0")
                structs = m.get("molecule_structures", {})
                smiles = structs.get("canonical_smiles") if structs else None
                if smiles:
                    hits.append(
                        SimilarityHit(
                            name=chembl_id,
                            score=f"{float(sim_score) / 100:.3f}",
                            smiles=smiles,
                        )
                    )
    except Exception:
        pass
    return hits


def _search_local(query_mol, method: str, db_path: str) -> list[SimilarityHit]:
    """Local fingerprint-based similarity search."""
    hits: list[SimilarityHit] = []

    if "Morgan" in method:
        q_fp = AllChem.GetMorganFingerprintAsBitVect(query_mol, 2, nBits=2048)
    elif "MACCS" in method:
        q_fp = MACCSkeys.GenMACCSKeys(query_mol)
    else:
        q_fp = Chem.RDKFingerprint(query_mol)

    if db_path.endswith(".sdf"):
        suppl = Chem.SDMolSupplier(db_path)
    else:
        return hits

    count = 0
    for m in suppl:
        if m is None:
            continue
        try:
            if "Morgan" in method:
                t_fp = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
            elif "MACCS" in method:
                t_fp = MACCSkeys.GenMACCSKeys(m)
            else:
                t_fp = Chem.RDKFingerprint(m)

            score = DataStructs.TanimotoSimilarity(q_fp, t_fp)
            # Use method-dependent threshold for meaningful hits
            threshold = _SIMILARITY_THRESHOLDS.get(method.split()[0] if " " in method else method, 0.7)
            if score >= threshold:
                name = (
                    m.GetProp("_Name") if m.HasProp("_Name") else f"Mol_{count}"
                )
                hits.append(
                    SimilarityHit(
                        name=name,
                        score=f"{score:.3f}",
                        smiles=Chem.MolToSmiles(m),
                    )
                )
        except Exception:
            pass
        count += 1

    hits.sort(key=lambda x: float(x.score), reverse=True)
    return hits
