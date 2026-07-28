"""
Molecule Resolver — Auto-detect and convert molecular identifiers to SMILES.

Supports:
  - SMILES (canonical or isomeric)
  - InChI / InChIKey
  - Compound names (aspirin, caffeine, etc.) via PubChem
  - CAS numbers (50-78-2) via PubChem
  - MOL block (V2000/V3000 pasted text)

All other routers can call resolve_to_smiles() directly.
"""

import re
import urllib.parse

import requests
from fastapi import APIRouter, HTTPException

from backend.models.schemas import ResolveRequest, ResolveResponse

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem.inchi import MolFromInchi
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# CAS number pattern: 1-7 digits, dash, 2 digits, dash, 1 digit
CAS_PATTERN = re.compile(r"^\d{1,7}-\d{2}-\d$")

# InChI pattern
INCHI_PATTERN = re.compile(r"^InChI=", re.IGNORECASE)

# InChIKey pattern: 14 uppercase chars, dash, 10 uppercase, dash, 1 uppercase char
INCHIKEY_PATTERN = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")


def detect_input_type(text: str) -> str:
    """Auto-detect the type of molecular identifier.

    Returns one of: 'smiles', 'inchi', 'inchikey', 'cas', 'mol_block', 'name'.
    """
    stripped = text.strip()

    if "\n" in stripped and ("V2000" in stripped or "V3000" in stripped or "M  END" in stripped):
        return "mol_block"

    if INCHI_PATTERN.match(stripped):
        return "inchi"

    if INCHIKEY_PATTERN.match(stripped):
        return "inchikey"

    if CAS_PATTERN.match(stripped):
        return "cas"

    # Try as SMILES — must contain typical SMILES characters and parse
    if RDKIT_AVAILABLE:
        mol = Chem.MolFromSmiles(stripped)
        if mol is not None:
            return "smiles"

    # Fallback: treat as compound name
    return "name"


def _resolve_from_pubchem(identifier: str, id_type: str = "name") -> str | None:
    """Look up a compound on PubChem and return canonical SMILES."""
    try:
        encoded = urllib.parse.quote(identifier)
        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
            f"{id_type}/{encoded}/property/CanonicalSMILES/JSON"
        )
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            props = data.get("PropertyTable", {}).get("Properties", [])
            if props:
                return props[0].get("CanonicalSMILES")
    except Exception:
        pass
    return None


def resolve_to_smiles(text: str) -> tuple[str, str, str | None]:
    """Resolve any molecular identifier to a canonical SMILES string.

    Returns: (smiles, detected_type, compound_name_or_none)
    Raises HTTPException if resolution fails.
    """
    stripped = text.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Empty input")

    input_type = detect_input_type(stripped)

    # ── SMILES (direct) ──
    if input_type == "smiles":
        if RDKIT_AVAILABLE:
            mol = Chem.MolFromSmiles(stripped)
            if mol:
                canonical = Chem.MolToSmiles(mol)
                return canonical, "smiles", None
        return stripped, "smiles", None

    # ── InChI ──
    if input_type == "inchi":
        if not RDKIT_AVAILABLE:
            raise HTTPException(status_code=500, detail="RDKit required for InChI conversion")
        mol = MolFromInchi(stripped)
        if mol is None:
            raise HTTPException(status_code=400, detail=f"Invalid InChI: {stripped[:80]}")
        return Chem.MolToSmiles(mol), "inchi", None

    # ── InChIKey → PubChem lookup ──
    if input_type == "inchikey":
        smiles = _resolve_from_pubchem(stripped, "inchikey")
        if smiles:
            return smiles, "inchikey", None
        raise HTTPException(
            status_code=400,
            detail=f"Could not resolve InChIKey: {stripped}"
        )

    # ── CAS Number → PubChem lookup ──
    if input_type == "cas":
        smiles = _resolve_from_pubchem(stripped, "name")
        if smiles:
            return smiles, "cas", stripped
        raise HTTPException(
            status_code=400,
            detail=f"Could not resolve CAS number: {stripped}"
        )

    # ── MOL Block (pasted V2000/V3000) ──
    if input_type == "mol_block":
        if not RDKIT_AVAILABLE:
            raise HTTPException(status_code=500, detail="RDKit required for MOL block parsing")
        mol = Chem.MolFromMolBlock(stripped)
        if mol is None:
            raise HTTPException(status_code=400, detail="Invalid MOL block — could not parse structure")
        name = mol.GetProp("_Name") if mol.HasProp("_Name") else None
        return Chem.MolToSmiles(mol), "mol_block", name

    # ── Compound Name → PubChem lookup ──
    if input_type == "name":
        smiles = _resolve_from_pubchem(stripped, "name")
        if smiles:
            return smiles, "name", stripped
        raise HTTPException(
            status_code=400,
            detail=f"Could not resolve compound name: '{stripped}'. Try using SMILES or InChI instead."
        )

    raise HTTPException(status_code=400, detail=f"Unrecognized input format")


@router.post("/molecule", response_model=ResolveResponse)
async def resolve_molecule(req: ResolveRequest):
    """Resolve a molecular identifier (SMILES, InChI, name, CAS, MOL block) to canonical SMILES."""
    smiles, detected_type, name = resolve_to_smiles(req.input)
    return ResolveResponse(
        smiles=smiles,
        input_type=detected_type,
        name=name,
        success=True,
    )


@router.post("/batch", response_model=dict)
async def resolve_batch(payload: dict):
    """Resolve multiple molecular identifiers in one call.

    Request body: { "inputs": ["aspirin", "InChI=1S/...", "CC(=O)O", "50-78-2"] }
    Returns: { "results": [...], "resolved": N, "failed": N }
    """
    inputs = payload.get("inputs", [])
    if not inputs:
        raise HTTPException(status_code=400, detail="No inputs provided")

    if len(inputs) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 inputs per batch")

    results = []
    resolved = 0
    failed = 0

    for inp in inputs:
        try:
            smiles, detected_type, name = resolve_to_smiles(str(inp))
            results.append({
                "input": inp,
                "smiles": smiles,
                "input_type": detected_type,
                "name": name,
                "success": True,
                "error": None,
            })
            resolved += 1
        except HTTPException as e:
            results.append({
                "input": inp,
                "smiles": None,
                "input_type": None,
                "name": None,
                "success": False,
                "error": e.detail,
            })
            failed += 1

    return {
        "results": results,
        "resolved": resolved,
        "failed": failed,
        "total": len(inputs),
    }
