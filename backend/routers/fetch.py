"""
PDB Fetcher router — download PDB, UniProt info, drug control search.
Ported from drug_tool.py: _t_fetch, _t_fetch_uniprot, _t_fetch_control.
"""

import os
from urllib.request import urlretrieve

import requests
from fastapi import APIRouter, HTTPException

from backend.config import APP_VERSION
from backend.models.schemas import (
    FetchPDBRequest,
    FetchPDBResponse,
    UniprotInfo,
    DrugInfo,
)

router = APIRouter()
_USER_AGENT = f"HelixCore/{APP_VERSION}"


@router.post("/pdb", response_model=FetchPDBResponse)
async def fetch_pdb(req: FetchPDBRequest):
    """Download a PDB from RCSB and save the unmodified structure."""
    code = req.pdb_id.upper().strip()
    d = req.output_dir
    if len(code) != 4:
        raise HTTPException(status_code=400, detail="Invalid PDB Code (must be 4 chars)")
    os.makedirs(d, exist_ok=True)
    if not os.path.isdir(d):
        raise HTTPException(status_code=400, detail="Invalid output directory")

    url = f"https://files.rcsb.org/download/{code}.pdb"
    pdb_path = os.path.join(d, f"{code}.pdb")

    try:
        urlretrieve(url, pdb_path)
        return FetchPDBResponse(
            pdb_path=pdb_path,
            message=f"PDB saved: {pdb_path}",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/uniprot/{pdb_id}", response_model=UniprotInfo)
async def get_uniprot_info(pdb_id: str):
    """Fetch UniProt data for a PDB accession."""
    pdb_id = pdb_id.upper().strip()
    mapping_url = (
        f"https://rest.uniprot.org/uniprotkb/search?query=xref:pdb-{pdb_id}&format=json"
    )
    r = requests.get(mapping_url, timeout=15)
    data = r.json()
    if not data.get("results"):
        raise HTTPException(status_code=404, detail="No UniProt entry found")

    entry = data["results"][0]
    accession = entry["primaryAccession"]
    entry_name = entry.get("uniProtkbId", "Unknown")
    organism = entry.get("organism", {}).get("scientificName", "Unknown")
    genes = (
        entry.get("genes", [{}])[0].get("geneName", {}).get("value", "Unknown")
    )

    function_text = "N/A"
    pathways: list[str] = []
    bio_process: list[str] = []
    chembl_id: str | None = None

    for comment in entry.get("comments", []):
        ct = comment.get("commentType", "")
        if ct == "FUNCTION":
            function_text = comment["texts"][0]["value"]
        elif ct == "PATHWAY":
            pathways.append(comment["texts"][0]["value"])

    for db_ref in entry.get("uniProtKBCrossReferences", []):
        if db_ref["database"] == "GO":
            props = db_ref.get("properties", [])
            term = next((p["value"] for p in props if p["key"] == "GoTerm"), "")
            if term.startswith("P:"):
                bio_process.append(term[2:])
        elif db_ref["database"] == "ChEMBL":
            chembl_id = db_ref["id"]

    network_url = (
        f"https://string-db.org/api/image/network?"
        f"identifiers={accession}&network_flavor=confidence&p=0.5"
    )

    return UniprotInfo(
        accession=accession,
        entry_name=entry_name,
        gene=genes,
        organism=organism,
        function=function_text,
        pathways=pathways,
        bio_processes=bio_process[:10],
        chembl_id=chembl_id,
        network_image_url=network_url,
    )


@router.get("/controls/{pdb_id}", response_model=DrugInfo | None)
async def find_drug_controls(pdb_id: str):
    """Search ChEMBL for approved drugs or high-affinity binders."""
    pdb_id = pdb_id.upper().strip()

    # First get UniProt accession
    mapping_url = (
        f"https://rest.uniprot.org/uniprotkb/search?query=xref:pdb-{pdb_id}&format=json"
    )
    r = requests.get(mapping_url, timeout=15)
    data = r.json()
    if not data.get("results"):
        raise HTTPException(status_code=404, detail="No UniProt entry found")

    entry = data["results"][0]
    accession = entry["primaryAccession"]

    # Find ChEMBL target ID
    chembl_id = None
    for db_ref in entry.get("uniProtKBCrossReferences", []):
        if db_ref["database"] == "ChEMBL":
            chembl_id = db_ref["id"]
            break

    if not chembl_id:
        url_t = (
            f"https://www.ebi.ac.uk/chembl/api/data/target?"
            f"target_components.accession={accession}&format=json"
        )
        r = requests.get(url_t, headers={"User-Agent": _USER_AGENT}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            if d.get("targets"):
                chembl_id = d["targets"][0]["target_chembl_id"]

    if not chembl_id:
        return None

    # Search approved drugs
    url_mech = (
        f"https://www.ebi.ac.uk/chembl/api/data/drug_mechanism?"
        f"target_chembl_id={chembl_id}&format=json"
    )
    r2 = requests.get(url_mech, headers={"User-Agent": _USER_AGENT}, timeout=15)
    if r2.status_code == 200:
        d2 = r2.json()
        if d2.get("drug_mechanisms"):
            drug = d2["drug_mechanisms"][0]
            mol_chembl = drug["molecule_chembl_id"]
            drug_name = drug.get("molecule_name") or mol_chembl

            smiles = None
            url_mol = f"https://www.ebi.ac.uk/chembl/api/data/molecule/{mol_chembl}?format=json"
            r3 = requests.get(url_mol, headers={"User-Agent": _USER_AGENT}, timeout=10)
            if r3.status_code == 200:
                d3 = r3.json()
                structs = d3.get("molecule_structures", {})
                if structs:
                    smiles = structs.get("canonical_smiles")

            return DrugInfo(
                name=drug_name,
                chembl_id=mol_chembl,
                smiles=smiles,
                source="approved_drug",
            )

    # Fallback to high-affinity binder
    url_act = (
        f"https://www.ebi.ac.uk/chembl/api/data/activity?"
        f"target_chembl_id={chembl_id}&pchembl_value__gte=6&limit=1&format=json"
    )
    r4 = requests.get(url_act, headers={"User-Agent": _USER_AGENT}, timeout=15)
    if r4.status_code == 200:
        d4 = r4.json()
        if d4.get("activities"):
            act = d4["activities"][0]
            mol_id = act["molecule_chembl_id"]

            smiles = None
            url_mol = f"https://www.ebi.ac.uk/chembl/api/data/molecule/{mol_id}?format=json"
            r5 = requests.get(url_mol, headers={"User-Agent": _USER_AGENT}, timeout=10)
            if r5.status_code == 200:
                d5 = r5.json()
                structs = d5.get("molecule_structures", {})
                if structs:
                    smiles = structs.get("canonical_smiles")

            return DrugInfo(
                name=mol_id,
                chembl_id=mol_id,
                smiles=smiles,
                affinity_type=act.get("standard_type"),
                affinity_value=str(act.get("standard_value")),
                source="experimental_binder",
            )

    return None
