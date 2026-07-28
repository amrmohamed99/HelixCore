"""
Pydantic models for request/response schemas.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ──── PDB Fetcher ────
class FetchPDBRequest(BaseModel):
    pdb_id: str = Field(..., min_length=4, max_length=4, description="4-character PDB accession code")
    output_dir: str


class FetchPDBResponse(BaseModel):
    pdb_path: str
    message: str


# ──── UniProt ────
class UniprotInfo(BaseModel):
    accession: str
    entry_name: str = "Unknown"
    gene: str
    organism: str
    function: str
    pathways: list[str] = []
    bio_processes: list[str] = []
    chembl_id: str | None = None
    network_image_url: str | None = None


class DrugInfo(BaseModel):
    name: str
    chembl_id: str
    smiles: str | None = None
    affinity_type: str | None = None
    affinity_value: str | None = None
    source: str  # "approved_drug" | "experimental_binder"


# ──── Lipinski Rule of Five (configurable thresholds) ────
class Ro5Thresholds(BaseModel):
    mw: float = 500
    logp: float = 5
    hbd: int = 5
    hba: int = 10
    max_violations: int = 1


# ──── Pocket Analyzer ────
class PocketAnalysisRequest(BaseModel):
    pdb_path: str
    ligand_name: str = ""
    ligand_chain: str = Field("", max_length=1, description="Optional exact ligand chain ID")
    ligand_resseq: int | None = Field(None, description="Optional exact ligand residue sequence number")
    ligand_icode: str = Field("", max_length=1, description="Optional ligand insertion code")
    padding: float = Field(8.0, ge=0.0, le=50.0)


class Residue(BaseModel):
    name: str
    seq: str


class PocketAnalysisResponse(BaseModel):
    residues: list[str] = []
    ligand_atom_count: int = 0
    contact_count: int = 0
    selected_ligand: dict | None = None


class GridBox(BaseModel):
    center_x: float
    center_y: float
    center_z: float
    size_x: float = Field(ge=1.0, le=126.0)
    size_y: float = Field(ge=1.0, le=126.0)
    size_z: float = Field(ge=1.0, le=126.0)


class GridBoxResponse(BaseModel):
    grid: GridBox
    output_path: str | None = None
    ligand_atom_count: int = 0
    selected_ligand: dict | None = None


# ──── Batch Generator ────
class BatchRequest(BaseModel):
    smiles_file: str


class ProcessingFailure(BaseModel):
    item: str
    reason: str
    detail: str | None = None


class BatchResponse(BaseModel):
    output_dir: str
    generated: int
    failed: int
    failures: list[ProcessingFailure] = Field(default_factory=list)


# ──── Minimization ────
class MinimizeRequest(BaseModel):
    directory: str
    force_field: str = "MMFF94"  # UFF | MMFF94 | MMFF94s


class MinimizeResponse(BaseModel):
    output_dir: str
    processed: int
    failed: int
    failures: list[ProcessingFailure] = Field(default_factory=list)


# ──── Converter ────
class ConvertRequest(BaseModel):
    directory: str


class ConvertResponse(BaseModel):
    output_dir: str
    converted: int
    failed: int = 0
    failures: list[ProcessingFailure] = Field(default_factory=list)


# ──── Receptor Preparation ────
class AnalyzePDBRequest(BaseModel):
    pdb_path: str = ""
    pdb_id: str = ""


class PrepareReceptorRequest(BaseModel):
    pdb_path: str
    keep_chain: str = ""     # empty = keep all chains
    remove_water: bool = True
    remove_ligands: bool = True
    remove_ions: bool = True
    add_hydrogens: bool = True


class PrepareReceptorResponse(BaseModel):
    output_path: str
    clean_pdb_path: str
    removed_waters: int = 0
    removed_ligands: int = 0
    removed_ions: int = 0
    message: str = ""
    integrity: dict | None = None
    prep_engine: str = "meeko"
    warnings: list[str] = []


# ──── Pipeline ────
class PipelineRequest(BaseModel):
    smiles: str
    name: str = "ligand"
    receptor: str
    config: str


class PipelineResponse(BaseModel):
    score: str | None = None
    output_path: str | None = None
    message: str


# ──── Similarity Search ────
class SimilarityRequest(BaseModel):
    query: str  # Ligand name or file path
    method: str = "Morgan"  # Morgan | MACCS | RDKit
    database: str = "PubChem"  # PubChem | ChEMBL | Local
    local_db_path: str | None = None


class SimilarityHit(BaseModel):
    name: str
    score: str
    smiles: str | None = None


class SimilarityResponse(BaseModel):
    hits: list[SimilarityHit] = []
    report_path: str | None = None


# ──── Docking ────
class DockingRequest(BaseModel):
    ligands_dir: str
    receptor: str
    config_path: str | None = None
    grid: GridBox | None = None
    exhaustiveness: int = 8  # Vina default; 8 for screening, 32+ for publication-quality
    seed: int = Field(42, ge=1, le=2_147_483_647, description="Deterministic AutoDock Vina random seed")


class DockingResult(BaseModel):
    ligand: str
    score: float | None = None
    output_path: str | None = None
    status: str  # "ok" | "error" | "skipped"
    error_detail: str | None = None


class DockingResponse(BaseModel):
    results: list[DockingResult] = []
    results_dir: str | None = None


class AutoGridRequest(BaseModel):
    receptor_path: str
    padding: float = 10.0


# ──── Oracle AI ────
class OracleRequest(BaseModel):
    dock_dir: str
    model_path: str | None = None


class OraclePrediction(BaseModel):
    ligand: str
    vina_score: float
    predicted_pKd: float
    confidence: str = "low"
    method: str


class OracleResponse(BaseModel):
    predictions: list[OraclePrediction] = []
    csv_path: str | None = None


# ──── Results Explorer ────
class Candidate(BaseModel):
    name: str
    score: float
    dir: str


class LoadResultsResponse(BaseModel):
    candidates: list[Candidate] = []


class ExportTopRequest(BaseModel):
    top_n: int = 10
    src_dir: str
    results_dir: str


class CSVReportRequest(BaseModel):
    res_dir: str
    src_dir: str = ""
    top_n: int = 10
    ro5: Ro5Thresholds = Ro5Thresholds()


class CSVRow(BaseModel):
    rank: int
    ligand: str
    score: float
    mw: float | None = None
    logp: float | None = None
    hbd: int | None = None
    hba: int | None = None
    tpsa: float | None = None
    rule_of_5: str = "Unknown"


class CSVReportResponse(BaseModel):
    rows: list[CSVRow] = []
    csv_path: str | None = None


# ──── Compound Filters (PAINS + Structural Alerts) ────
class FilterRequest(BaseModel):
    input_path: str
    covalent_mode: bool = False  # When True, suppress reactive-warhead alerts for covalent inhibitor programs


class FilteredCompound(BaseModel):
    name: str
    smiles: str
    pains_free: bool = True
    pains_matches: list[str] = []
    alert_free: bool = True
    alerts: list[str] = []
    passed: bool = True


class FilterResponse(BaseModel):
    compounds: list[FilteredCompound] = []
    total: int = 0
    passed: int = 0
    flagged: int = 0
    report_path: str | None = None


# ──── Extended ADMET ────
class ADMETRequest(BaseModel):
    smiles: str | None = None
    file_path: str | None = None
    ro5: Ro5Thresholds = Ro5Thresholds()


# The blood-brain-barrier field is a descriptor-threshold triage filter, not a
# trained permeability model.  The text below travels with every response so a
# consumer cannot mistake the flag for a validated prediction.
BBB_TRIAGE_CAVEAT = (
    "BBB triage flag — a three-threshold descriptor filter (MW, TPSA, LogP), not a "
    "trained blood-brain-barrier permeability model. It is a coarse triage aid with "
    "known false negatives: caffeine is CNS-active yet falls below the LogP floor and "
    "is flagged as non-permeant. Do not report it as a permeability prediction."
)


class BBBTriageCriterion(BaseModel):
    """One threshold of the BBB triage filter and the descriptor it was applied to."""

    name: str                       # descriptor name, e.g. "MW"
    value: float | None = None      # the computed descriptor value
    operator: str = "<"             # comparison applied, e.g. "<" or "0.5 <= x <= 4.5"
    threshold: str = ""             # human-readable bound, e.g. "450" or "[0.5, 4.5]"
    passed: bool = False


class BBBTriage(BaseModel):
    """Transparent result of the BBB triage filter: verdict plus the rules that produced it."""

    flag: bool = False
    criteria: list[BBBTriageCriterion] = Field(default_factory=list)
    caveat: str = BBB_TRIAGE_CAVEAT


class ADMETProfile(BaseModel):
    name: str
    smiles: str
    mw: float | None = None
    logp: float | None = None
    hbd: int | None = None
    hba: int | None = None
    tpsa: float | None = None
    rotatable_bonds: int | None = None
    qed: float | None = None
    sa_score: float | None = None
    bertz_ct: float | None = None
    esol_logS: float | None = None
    # Relabelled from "BBB permeable" — see BBB_TRIAGE_CAVEAT.
    bbb_triage_flag: bool | None = Field(
        None,
        description="Verdict of the three-threshold BBB triage filter. Not a trained model.",
    )
    bbb_triage: BBBTriage | None = Field(
        None,
        description="The thresholds, descriptor values and per-rule verdicts behind bbb_triage_flag.",
    )
    bbb_permeable: bool | None = Field(
        None,
        deprecated=True,
        description="Deprecated alias of bbb_triage_flag, kept for backward compatibility.",
    )
    rule_of_5: str = "Unknown"
    ro5_violations: int = 0


class ADMETResponse(BaseModel):
    profiles: list[ADMETProfile] = []
    csv_path: str | None = None


# ──── Protein-Ligand Interactions ────
class InteractionRequest(BaseModel):
    receptor_path: str
    ligand_path: str
    cutoff: float = 4.0


class Interaction(BaseModel):
    """A single interaction *label* on one receptor-atom/ligand-atom pair.

    Classification is multi-label: a charge-complementary pair that also sits
    inside the hydrogen-bond distance yields two entries with the same
    ``residue``/``receptor_atom``/``ligand_atom`` and different ``type``.
    """

    type: str
    residue: str
    distance: float
    ligand_atom: str | None = None
    receptor_atom: str | None = None


class InteractionResponse(BaseModel):
    """Interaction counts under multi-label classification.

    ``total`` remains ``len(interactions)`` as it always has, but the list is now
    multi-label, so ``total`` counts label assignments rather than atom pairs.
    ``total_single_label`` reproduces the pre-multi-label number (one label per
    atom pair, H-bond > hydrophobic > salt bridge) for continuity with figures
    published before this change.
    """

    interactions: list[Interaction] = []
    h_bonds: int = 0
    hydrophobic: int = 0
    # Exhaustive: includes charge-complementary pairs that are also H-bonded.
    salt_bridges: int = 0
    # Legacy count: salt bridges on pairs not already labelled as hydrogen bonds.
    salt_bridges_single_label: int = 0
    total: int = 0
    # Distinct atom pairs carrying at least one label (== the old ``total``).
    total_single_label: int = 0
    # Atom pairs carrying more than one label (currently only H-bond + salt bridge).
    dual_labeled_pairs: int = 0


# ──── Result Clustering ────
class ClusterRequest(BaseModel):
    results_dir: str
    src_dir: str = ""
    method: str = "Morgan"
    cutoff: float = 0.4


class ClusterMember(BaseModel):
    name: str
    score: float
    smiles: str | None = None
    is_centroid: bool = False


class Cluster(BaseModel):
    cluster_id: int
    size: int
    members: list[ClusterMember] = []


class ClusterResponse(BaseModel):
    clusters: list[Cluster] = []
    total_compounds: int = 0
    num_clusters: int = 0
    singletons: int = 0


# ──── Analog Generation ────
class AnalogRequest(BaseModel):
    smiles: str
    name: str = "parent"
    method: str = "fragment"
    max_analogs: int = 20


class AnalogCompound(BaseModel):
    name: str
    smiles: str
    similarity: float | None = None
    mw: float | None = None


class AnalogResponse(BaseModel):
    analogs: list[AnalogCompound] = []
    parent_smiles: str
    count: int = 0


# ──── Consensus Scoring ────
class ConsensusRequest(BaseModel):
    results_dir: str
    src_dir: str = ""


class ConsensusResult(BaseModel):
    ligand: str
    vina_score: float | None = None
    vina_rank: int | None = None
    mmff_energy: float | None = None
    energy_rank: int | None = None
    contact_score: float | None = None
    contact_rank: int | None = None
    consensus_rank: float | None = None


class ConsensusResponse(BaseModel):
    results: list[ConsensusResult] = []
    csv_path: str | None = None


# ──── Druggability Assessment ────
class DruggabilityRequest(BaseModel):
    pdb_path: str
    ligand_name: str = ""
    ligand_chain: str = Field("", max_length=1)
    ligand_resseq: int | None = None
    ligand_icode: str = Field("", max_length=1)


class DruggabilityResponse(BaseModel):
    volume: float | None = None
    hydrophobicity_ratio: float | None = None
    residue_count: int = 0
    druggable: bool = False
    confidence: str = "low"
    notes: list[str] = []


# ──── Pose Energy Decomposition ────
class PoseDecompRequest(BaseModel):
    log_path: str


class EnergyComponent(BaseModel):
    component: str
    value: float


class PoseDecompResponse(BaseModel):
    ligand: str
    total_score: float | None = None
    components: list[EnergyComponent] = []


# ──── Project Management ────
class Project(BaseModel):
    id: str = ""
    name: str
    target_name: str = ""
    pdb_id: str = ""
    receptor_path: str = ""
    grid_config: str = ""
    ligand_source: str = ""
    notes: str = ""
    created: str = ""
    updated: str = ""
    pipeline_state: dict = {}  # pipeline step statuses
    page_inputs: dict = {}    # saved form inputs per page
    session_data: dict = {}   # serialized session fields


class ProjectListResponse(BaseModel):
    projects: list[Project] = []


# ──── Watchlist ────
class WatchlistItem(BaseModel):
    id: str = ""
    name: str
    smiles: str | None = None
    score: float | None = None
    source: str = ""
    notes: str = ""
    added: str = ""


class WatchlistResponse(BaseModel):
    items: list[WatchlistItem] = []


# ──── Batch Pipeline ────
class BatchPipelineRequest(BaseModel):
    smiles_file: str
    receptor: str
    config: str
    force_field: str = "MMFF94"
    run_filters: bool = False
    run_admet: bool = False


class BatchPipelineStep(BaseModel):
    step: str
    status: str
    count: int = 0
    message: str = ""


class BatchPipelineResponse(BaseModel):
    steps: list[BatchPipelineStep] = []
    results_dir: str | None = None
    total_docked: int = 0
    failed_docked: int = 0
    best_score: float | None = None
    message: str = ""


# ──── SMILES to IUPAC ────
class IUPACResponse(BaseModel):
    smiles: str
    iupac_name: str | None = None
    common_name: str | None = None


# ──── Molecule Resolver ────
class ResolveRequest(BaseModel):
    input: str = Field(..., description="SMILES, InChI, compound name, CAS number, or MOL block")


class ResolveResponse(BaseModel):
    smiles: str
    input_type: str
    name: str | None = None
    success: bool = True


# ──── Global Job Progress ────
class JobSnapshot(BaseModel):
    id: str
    name: str
    status: str
    progress: int = 0
    message: str = ""
    current: int = 0
    total: int = 0
    started_at: float
    updated_at: float


class JobControlResponse(BaseModel):
    success: bool
    message: str
    job: JobSnapshot | None = None


# ──── Pharmacophore Modeling & Screening ────
class PharmacophoreFeature(BaseModel):
    """Single pharmacophore feature with type, position, and radius."""
    type: str = Field(..., description="HBD | HBA | Hydrophobic | Aromatic | PosIonizable | NegIonizable")
    atoms: list[int] = Field(default_factory=list, description="Atom indices involved")
    x: float | None = None
    y: float | None = None
    z: float | None = None
    radius: float = 1.0


class PharmGenerateRequest(BaseModel):
    smiles: str = Field(..., description="SMILES string of the reference molecule")
    include_3d: bool = Field(False, description="Generate 3D conformer and extract 3D features")


class PharmGenerateResponse(BaseModel):
    smiles: str
    features: list[PharmacophoreFeature] = []
    svg: str | None = Field(None, description="2D SVG with pharmacophore overlays")
    feature_counts: dict[str, int] = Field(default_factory=dict)
    message: str = ""


class PharmScreenRequest(BaseModel):
    reference_smiles: str = Field(..., description="SMILES of the reference compound")
    library_source: str = Field(..., description=".smi/.sdf file path or directory of .mol files")
    mode: str = Field("2d", description="'2d' (fingerprint) or '3d' (alignment)")
    threshold: float = Field(0.5, ge=0.0, le=1.0, description="Similarity threshold for hits")


class PharmScreenHit(BaseModel):
    name: str
    smiles: str
    score: float
    matched_features: int = 0


class PharmScreenResponse(BaseModel):
    hits: list[PharmScreenHit] = []
    total_screened: int = 0
    mode: str = "2d"
    warning: str | None = None
    message: str = ""


class PharmSaveRequest(BaseModel):
    name: str = Field(..., description="Pharmacophore model name")
    reference_smiles: str
    features: list[PharmacophoreFeature] = []
    output_dir: str


class PharmSaveResponse(BaseModel):
    path: str
    message: str = ""


class PharmLoadResponse(BaseModel):
    name: str
    reference_smiles: str
    features: list[PharmacophoreFeature] = []
    path: str


# ──── Report Generation ────
class ReportSection(BaseModel):
    """A single section in a generated report."""
    title: str
    type: str = Field("text", description="'text' | 'table' | 'stats'")
    data: dict | str | list = Field(default_factory=dict)


class ReportRequest(BaseModel):
    title: str | None = Field(None, description="Report title")
    format: str = Field("both", description="'pdf' | 'html' | 'both'")
    results_dir: str | None = Field(None, description="Auto-collect from docking results dir")
    sections: list[dict] | None = Field(None, description="Custom sections to include")
    output_dir: str | None = Field(None, description="Directory to save reports")
    project_name: str | None = None
    author: str | None = None
    custom_text: str | None = Field(None, description="Free-form notes to include")


class ReportResponse(BaseModel):
    paths: list[str] = Field(default_factory=list, description="Generated report file paths")
    message: str = ""


# ──── Fragment-Based Drug Design ────
class FragmentDecomposeRequest(BaseModel):
    smiles: str = Field(..., description="SMILES of molecule to decompose")
    method: str = Field("brics", description="'brics' | 'recap' | 'murcko'")


class FragmentDecomposeResponse(BaseModel):
    smiles: str
    fragments: list[str] = Field(default_factory=list)
    method: str = "brics"
    count: int = 0
    message: str = ""


class FragmentLinkRequest(BaseModel):
    fragments: list[str] = Field(..., min_length=2, description="SMILES of fragments to link")
    max_results: int = Field(50, ge=1, le=500)


class FragmentLinkResponse(BaseModel):
    products: list[str] = Field(default_factory=list)
    count: int = 0
    message: str = ""


class FragmentGrowRequest(BaseModel):
    core: str = Field(..., description="Core fragment SMILES")
    growth_vectors: int = Field(3, ge=1, le=10, description="Number of growth directions")
    max_results: int = Field(50, ge=1, le=500)


class FragmentGrowResponse(BaseModel):
    grown: list[str] = Field(default_factory=list)
    count: int = 0
    message: str = ""


class FragmentLibraryEntry(BaseModel):
    smiles: str
    name: str = ""
    category: str = ""
    mw: float = 0
    rule_of_3: bool = False


class FragmentLibraryResponse(BaseModel):
    fragments: list[FragmentLibraryEntry] = Field(default_factory=list)
    total: int = 0
    categories: list[str] = Field(default_factory=list)


# ──── Scaffold Hopping ────
class ScaffoldHopRequest(BaseModel):
    smiles: str = Field(..., description="SMILES of the reference compound")
    method: str = Field("murcko", description="'murcko' | 'mcs' | 'rgroup' | 'mmp'")
    library_path: str | None = Field(None, description="Path to library .smi/.sdf file")
    max_results: int = Field(50, ge=1, le=500)


class ScaffoldHopResult(BaseModel):
    smiles: str
    scaffold: str = ""
    similarity: float = 0.0
    name: str = ""


class ScaffoldHopResponse(BaseModel):
    reference: str
    method: str
    reference_scaffold: str = ""
    results: list[ScaffoldHopResult] = Field(default_factory=list)
    count: int = 0
    message: str = ""


# ──── Multi-Target Docking ────
class MultiTargetRequest(BaseModel):
    ligands_dir: str = Field(..., description="Directory of PDBQT ligand files")
    receptors: list[str] = Field(..., min_length=1, description="List of receptor file paths")
    config_paths: list[str] | None = Field(None, description="Config per receptor (or single shared)")
    grids: list[dict] | None = None
    exhaustiveness: int = 8
    seed: int = Field(42, ge=1, le=2_147_483_647, description="Deterministic AutoDock Vina random seed")
    mode: str = Field("sequential", description="'sequential' | 'parallel'")


class MultiTargetResult(BaseModel):
    receptor: str
    ligand: str
    score: float | None = None
    status: str = "ok"
    output_path: str | None = None


class MultiTargetResponse(BaseModel):
    results: list[MultiTargetResult] = Field(default_factory=list)
    selectivity_matrix: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    results_dir: str = ""
    message: str = ""
